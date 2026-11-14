"""Expand registry grids into the registry artifact (spec stage 2, register).

config_id = hash(method, theta_spec, params, exog_set_id)
core_spec_id = hash(method, theta_spec, params)
Grid placement is for display only; no stage reads it as adjacency.
Every configuration produces its own residuals; nothing combines configurations
before the residual archive is complete.
"""

from __future__ import annotations

import hashlib
import itertools
import json

import numpy as np
import pandas as pd

from . import contracts
from .methods import get_method


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _hash(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode()).hexdigest()[:16]


def core_spec_id(method: str, theta_spec: str, params: dict) -> str:
    return _hash({"method": method, "theta_spec": theta_spec, "params": params})


def config_id(method: str, theta_spec: str, params: dict, exog_set_id: str = "") -> str:
    return _hash({"method": method, "theta_spec": theta_spec, "params": params, "exog_set_id": exog_set_id})


def _estimated_rows(grid: dict, method) -> list[dict]:
    """One row per grid point of a family estimated at the origin (methods.precomputed).

    theta = the grid point (adapter fields, e.g. arima_p) plus the estimation policy (refit_every, window,
    min_train), so the policy is part of config_id; values keep their YAML types. Points matching an
    `exclude` entry are not registered. ell is not defined (the parameters move with the origin).
    """
    names = list(grid["params"])
    axes = grid["grid_axes"]
    policy = dict(grid["policy"])
    excludes = grid.get("exclude", [])
    rows = []
    for combo in itertools.product(*(grid["params"][n] for n in names)):
        point = dict(zip(names, combo))
        if any(all(point.get(k) == v for k, v in ex.items()) for ex in excludes):
            continue
        theta = {**point, **policy}
        gi = grid["params"][axes[0]].index(point[axes[0]]) if axes else 0
        gj = grid["params"][axes[1]].index(point[axes[1]]) if len(axes) > 1 else 0
        rows.append({
            "config_id": config_id(method.name, "estimated", theta),
            "core_spec_id": core_spec_id(method.name, "estimated", theta),
            "exog_set_id": "",
            "method": method.name,
            "theta_spec": "estimated",
            "params": _canonical(theta),
            "ell": np.nan,
            "ell_status": "estimated",
            "s1_name": method.state_names[0],
            "s2_name": method.state_names[1],
            "grid_axes": _canonical(axes),
            "grid_i": gi,
            "grid_j": gj,
            "admissible": True,
        })
    return rows


def build_registry(grids: list[dict], cfg: dict) -> pd.DataFrame:
    """Parameter grids in file order; one row per grid point."""
    rows = []
    for grid in grids:
        method = get_method(grid["method"], cfg)
        if method.theta_spec == "estimated":
            rows.extend(_estimated_rows(grid, method))
            continue
        names = list(grid["params"])
        if set(names) != set(method.param_names):
            raise ValueError(f"grid for {method.name}: params {names} != {list(method.param_names)}")
        axes = grid["grid_axes"]
        axis_values = {a: list(grid["params"][a]) for a in axes}

        # F range over admissible configurations of each stratum, for ell.
        candidates = []
        for combo in itertools.product(*(grid["params"][n] for n in method.param_names)):
            theta = {n: float(v) for n, v in zip(method.param_names, combo)}
            ok = method.admissible(theta)
            F = method.fisher(theta)[1] if ok else None
            candidates.append((theta, ok, F, method.stratum(theta)))
        ranges: dict[str, tuple[float, float]] = {}
        for _, ok, F, s in candidates:
            if ok and F is not None:
                lo, hi = ranges.get(s, (F, F))
                ranges[s] = (min(lo, F), max(hi, F))

        for theta, ok, F, s in candidates:
            if not ok:
                ell, status = np.nan, "not_admissible"
            elif F is None:
                ell, status = np.nan, "not_defined_multiparameter"
            else:
                lo, hi = ranges[s]
                ell, status = (0.0 if hi == lo else (F - lo) / (hi - lo)), "closed_form"
            gi = axis_values[axes[0]].index(theta[axes[0]])
            gj = axis_values[axes[1]].index(theta[axes[1]]) if len(axes) > 1 else 0
            rows.append({
                "config_id": config_id(method.name, "fixed", theta),
                "core_spec_id": core_spec_id(method.name, "fixed", theta),
                "exog_set_id": "",
                "method": method.name,
                "theta_spec": "fixed",
                "params": _canonical(theta),
                "ell": ell,
                "ell_status": status,
                "s1_name": method.state_names[0],
                "s2_name": method.state_names[1],
                "grid_axes": _canonical(axes),
                "grid_i": gi,
                "grid_j": gj,
                "admissible": ok,
            })

    cols = {k: [row[k] for row in rows] for k in rows[0]}
    return contracts.from_columns(cols, "registry")


def twin_groups(registry: pd.DataFrame, cfg: dict) -> list[list[str]]:
    """Groups of admissible configurations that forecast identically (method faces), each sorted, singletons left out."""
    adm = registry[registry["admissible"]]
    ids = set(adm["config_id"])
    parent = {c: c for c in ids}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    for cid, m, p, ts in zip(adm["config_id"], adm["method"], adm["params"], adm["theta_spec"]):
        if ts != "fixed":
            continue  # estimated families have no closed-form twins
        eq = get_method(str(m), cfg).equivalent(json.loads(p))
        if eq is not None:
            other = config_id(eq[0], "fixed", eq[1])
            if other in ids:
                a, b = find(cid), find(other)
                parent[max(a, b)] = min(a, b)
    groups: dict[str, list[str]] = {}
    for c in ids:
        groups.setdefault(find(c), []).append(c)
    return sorted(sorted(g) for g in groups.values() if len(g) > 1)
