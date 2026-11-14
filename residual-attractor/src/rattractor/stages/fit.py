"""Stage 3, fit: series + registry -> states artifact.

Every admissible configuration runs once over each whole series; the recursion
makes the state at t a function of y_0..y_t only. Acceptance: perturbing y
after a cut leaves every state at or before the cut unchanged, and SES matches
an independent ARIMA(0,1,1) recursion.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import contracts
from ..methods import Fitted, get_method
from . import AcceptanceError


def configs(registry: pd.DataFrame) -> list[tuple[str, str, dict]]:
    """[(config_id, method, theta)] for the admissible rows, in registry order."""
    adm = registry[registry["admissible"]]
    return [(str(c), str(m), json.loads(p)) for c, m, p in zip(adm["config_id"], adm["method"], adm["params"])]


def fit_series(y: np.ndarray, registry: pd.DataFrame, cfg: dict) -> dict[str, Fitted]:
    return {cid: get_method(m, cfg).fit(y, theta) for cid, m, theta in configs(registry)}


def run(series: pd.DataFrame, registry: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict[str, dict[str, Fitted]]]:
    """(states artifact, {series_id: {config_id: Fitted}}); the second is an in-process cache for stage 4."""
    cols = {k: [] for k in ("series_id", "config_id", "t", "yhat1", "e1", "s1", "s2")}
    fitted: dict[str, dict[str, Fitted]] = {}
    for sid, g in series.groupby("series_id", sort=False, observed=True):
        y = g["y"].to_numpy()
        fitted[str(sid)] = fs = fit_series(y, registry, cfg)
        for cid, f in fs.items():
            n = y.size
            cols["series_id"].append(np.full(n, str(sid), dtype=object))
            cols["config_id"].append(np.full(n, cid, dtype=object))
            cols["t"].append(np.arange(n))
            cols["yhat1"].append(f.yhat1)
            cols["e1"].append(f.e1)
            cols["s1"].append(f.s1)
            cols["s2"].append(f.s2)
        check(str(sid), y, registry, cfg, fs)
    states = contracts.from_columns({k: np.concatenate(v) for k, v in cols.items()}, "states")
    return states, fitted


def check(sid: str, y: np.ndarray, registry: pd.DataFrame, cfg: dict, fs: dict[str, Fitted]) -> None:
    cut = y.size // 2
    rng = np.random.default_rng(cfg["seed"])
    y2 = y.copy()
    y2[cut + 1 :] += rng.normal(0.0, 10.0 * (np.std(y) + 1.0), y.size - cut - 1)
    bad = []
    for cid, m, theta in configs(registry):
        if get_method(m, cfg).precomputed:
            continue  # leakage of the GDSS cube: fit_through <= issuance on read (gdss.load) and MATLAB's own cut test
        a, b = fs[cid], get_method(m, cfg).fit(y2, theta)
        for name in ("s1", "s2", "yhat1"):
            if not np.array_equal(getattr(a, name)[: cut + 1], getattr(b, name)[: cut + 1], equal_nan=True):
                bad.append((sid, cid, name, "changed when y after the cut changed"))
        if m == "ses":
            mcoef, e, ref = theta["alpha"] - 1.0, 0.0, np.full(y.size, np.nan)
            for t in range(y.size - 1):
                ref[t + 1] = y[t] + mcoef * e
                e = y[t + 1] - ref[t + 1]
            scale = max(1.0, float(np.max(np.abs(y))))
            if not np.allclose(a.yhat1[1:], ref[1:], rtol=0.0, atol=1e-10 * scale):
                bad.append((sid, cid, "yhat1", "SES differs from ARIMA(0,1,1)"))
    if bad:
        raise AcceptanceError("fit", f"{len(bad)} failures", pd.DataFrame(bad, columns=["series_id", "config_id", "field", "problem"]))
