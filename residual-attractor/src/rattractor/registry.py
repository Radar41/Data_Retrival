"""Expand registry grids into the registry artifact (spec stage 2, register).

config_id = hash(method, theta_spec, params, exog_set_id)
core_spec_id = hash(method, theta_spec, params)
Grid placement is for display only; no stage reads it as adjacency.
A fusion rule (a grid file with `members`) adds one fused configuration over the
admissible parameter configurations; it has its own core_spec_id and no ell.
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


FUSION_RULES = ("all_admissible",)


def build_registry(grids: list[dict], cfg: dict) -> pd.DataFrame:
    """Parameter grids in file order, then fusion rules (so fused rows come last, as the fiber needs)."""
    rows = []
    for grid in grids:
        if "members" in grid:
            continue
        method = get_method(grid["method"], cfg)
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

    plain = list(rows)
    for grid in (g for g in grids if "members" in g):
        method = get_method(grid["method"], cfg)
        if not method.is_fusion:
            raise ValueError(f"grid with members names {method.name}, which is not a fusion method")
        if grid["members"] not in FUSION_RULES:
            raise ValueError(f"fusion members rule {grid['members']!r} not in {FUSION_RULES}")
        members = [{"method": r["method"], "params": json.loads(r["params"])} for r in plain if r["admissible"]]
        # Members are a set: store them sorted by their own config_id, so the fused identity does not
        # depend on the order of registry.files or of the grid values.
        members.sort(key=lambda m: config_id(m["method"], "fixed", m["params"]))
        theta = {"members": members}
        rows.append({
            "config_id": config_id(method.name, "fixed", theta),
            "core_spec_id": core_spec_id(method.name, "fixed", theta),
            "exog_set_id": "",
            "method": method.name,
            "theta_spec": "fixed",
            "params": _canonical(theta),
            "ell": np.nan,
            "ell_status": "not_applicable",
            "s1_name": method.state_names[0],
            "s2_name": method.state_names[1],
            "grid_axes": _canonical([]),
            "grid_i": 0,
            "grid_j": 0,
            "admissible": method.admissible(theta),
        })

    cols = {k: [row[k] for row in rows] for k in rows[0]}
    return contracts.from_columns(cols, "registry")


def fused_member_ids(params_json: str) -> list[str]:
    """config_ids of a fused configuration's members, in stored order (sorted by config_id)."""
    return [config_id(m["method"], "fixed", m["params"]) for m in json.loads(params_json)["members"]]
