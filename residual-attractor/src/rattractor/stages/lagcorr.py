"""Stage 6, lag correlation: states + series -> lagcorr.

One row per (series, configuration, base position t, lag k), with t over the base the
steps share (forecast.origins) and k in -K..K. Each row is one configuration's own
one-step residuals e1; nothing is standardized or pooled across configurations.

    rho(c, t, k = -m) = corr(e_s, e_{s-m}), s in (t - W_rho, t]
    rho(c, t, k = +m) = corr(e_s, e_{s+m}), s in [t, t + W_rho)
A pair is kept only when both indices lie in 1..N-1 and both values are finite; the
window is never shifted or padded. n_pairs counts the kept pairs. Pearson correlation,
each member centred on its own mean over the kept pairs (two-pass), clipped to [-1, 1].
rho and theta are null (n_pairs kept) where n_pairs < lagcorr.min_pairs or either member's
sd over the kept pairs is at or below the series' sigma floor (a flat window). At k = 0,
rho = 1 and theta = 0 are assigned.

theta = arccos of the smoothed rho (lagcorr.smoothing, "applied to rho before arccos"):
a 3-point mean along the base at fixed (configuration, k), never across lags, over the
non-null values among the three base positions. trailing3 uses t and the two before it,
so every past-lag field at t uses data at or before t; centred3 uses t - 1, t, t + 1;
none leaves rho as it is. A null rho stays null; the rho column keeps the raw estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError
from .forecast import origins, series_floor

TOL = 1e-7        # k = 0: rho = 1 and theta = 0 are assigned; checked to this tolerance (spec: stated tolerances)
THETA_TOL = 1e-6  # theta reproduced from the stored rho


def twist(rho: np.ndarray, how: str) -> np.ndarray:
    """theta along one base-ordered rho path (float32 in, float32 out)."""
    r = np.asarray(rho, dtype=np.float64)
    if how == "none":
        S = r
    else:
        offsets = {"trailing3": (-2, -1, 0), "centred3": (-1, 0, 1)}[how]
        n = r.size
        valid = ~np.isnan(r)
        num, cnt = np.zeros(n), np.zeros(n)
        for d in offsets:
            idx = np.arange(n) + d
            inside = (idx >= 0) & (idx < n)
            src = np.where(inside, idx, 0)
            use = inside & valid[src]
            num += np.where(use, r[src], 0.0)
            cnt += use
        S = np.where(valid, num / np.maximum(cnt, 1.0), np.nan)
    with np.errstate(invalid="ignore"):
        return np.arccos(np.clip(S, -1.0, 1.0)).astype(np.float32)


def correlations(e: np.ndarray, O: np.ndarray, k: int, cfg: dict, floor: float) -> tuple[np.ndarray, np.ndarray]:
    """(rho float64 with NaN for null rows, n_pairs) at every base position for one lag k != 0."""
    N, W, m = e.size, cfg["lagcorr.window"], abs(k)
    S = O[:, None] + (np.arange(-W + 1, 1) if k < 0 else np.arange(W))[None, :]
    P = S - m if k < 0 else S + m
    ok = (S >= 1) & (S <= N - 1) & (P >= 1) & (P <= N - 1)
    X, Y = e[np.clip(S, 0, N - 1)], e[np.clip(P, 0, N - 1)]
    ok &= np.isfinite(X) & np.isfinite(Y)
    n = ok.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = np.where(ok, X, 0.0).sum(axis=1) / n
        my = np.where(ok, Y, 0.0).sum(axis=1) / n
        dx = np.where(ok, X - mx[:, None], 0.0)
        dy = np.where(ok, Y - my[:, None], 0.0)
        sxx, syy, sxy = (dx * dx).sum(axis=1), (dy * dy).sum(axis=1), (dx * dy).sum(axis=1)
        rho = np.clip(sxy / np.sqrt(sxx * syy), -1.0, 1.0)
        dof = n - cfg["sigma.ddof"]
        sdx, sdy = np.sqrt(sxx / dof), np.sqrt(syy / dof)
    null = (n < cfg["lagcorr.min_pairs"]) | ~(sdx > floor) | ~(sdy > floor)
    rho[null] = np.nan
    return rho, n


def run_series(sid: str, g: pd.DataFrame, states: pd.DataFrame, registry: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    y = g["y"].to_numpy()
    N = y.size
    ts = int(np.argmax((g["split"] == "test").to_numpy()))
    O = origins(N, ts, cfg)
    if O.size == 0:
        raise AcceptanceError("lagcorr", f"{sid}: no base positions")
    floor = series_floor(y[:ts], cfg)
    K, W = cfg["lagcorr.K"], cfg["lagcorr.window"]
    lags = np.arange(-K, K + 1)
    coords = list(registry.loc[registry["admissible"], "config_id"])
    st = states[(states["series_id"] == sid) & states["config_id"].isin(coords)]
    E = st.pivot(index="t", columns="config_id", values="e1").sort_index()
    if not np.array_equal(E.index.to_numpy(), np.arange(N)) or set(E.columns) != set(coords):
        raise AcceptanceError("lagcorr", f"{sid}: states do not cover t = 0..{N - 1} for every configuration")

    out = {k: [] for k in ("config_id", "t", "k", "rho", "theta", "n_pairs")}
    win0 = O[:, None] + np.arange(-W + 1, 1)[None, :]
    for cid in coords:
        e = E[cid].to_numpy(np.float64)
        rho = np.empty((O.size, lags.size), dtype=np.float32)
        npairs = np.empty((O.size, lags.size), dtype=np.int64)
        for j, k in enumerate(lags):
            if k == 0:
                inside = (win0 >= 1) & (win0 <= N - 1)
                npairs[:, j] = (inside & np.isfinite(e[np.clip(win0, 0, N - 1)])).sum(axis=1)
                rho[:, j] = 1.0
            else:
                r, n = correlations(e, O, int(k), cfg, floor)
                rho[:, j], npairs[:, j] = r.astype(np.float32), n
        theta = np.column_stack([twist(rho[:, j], cfg["lagcorr.smoothing"]) for j in range(lags.size)])
        out["config_id"].append(np.full(rho.size, cid, dtype=object))
        out["t"].append(np.repeat(O, lags.size))
        out["k"].append(np.tile(lags, O.size))
        out["rho"].append(rho.reshape(-1))
        out["theta"].append(theta.reshape(-1))
        out["n_pairs"].append(npairs.reshape(-1))
    data = {k: np.concatenate(v) for k, v in out.items()}
    rows = data["rho"].size
    data.update({"series_id": np.full(rows, sid, dtype=object), "cell_id": [pd.NA] * rows})
    lc = contracts.from_columns(data, "lagcorr")
    check(sid, lc, coords, O, cfg)
    return lc


def check(sid: str, lc: pd.DataFrame, coords: list[str], O: np.ndarray, cfg: dict) -> None:
    """Stage 6 acceptance; a failure carries the failing rows and the rule each broke."""
    K, W = cfg["lagcorr.K"], cfg["lagcorr.window"]
    problems, frames = [], []
    want = len(coords) * O.size * (2 * K + 1)
    grid_ok = (len(lc) == want and set(lc["config_id"]) == set(coords) and set(lc["t"]) == set(O.tolist())
               and set(lc["k"]) == set(range(-K, K + 1)))
    if not grid_ok:
        problems.append(f"{len(lc)} rows, expected {want} = configurations x base positions x (2K + 1)")
    k = lc["k"].to_numpy()
    rho, theta, n = lc["rho"].to_numpy(np.float64), lc["theta"].to_numpy(np.float64), lc["n_pairs"].to_numpy()
    zero = k == 0
    with np.errstate(invalid="ignore"):
        rules = [
            (zero & ~((np.abs(rho - 1.0) <= TOL) & (np.abs(theta) <= TOL)), "rho = 1 and theta = 0 at k = 0"),
            (~zero & (n < cfg["lagcorr.min_pairs"]) & ~(np.isnan(rho) & np.isnan(theta)), "rows under the pair minimum are null"),
            (np.isnan(theta) != np.isnan(rho), "theta is null exactly where rho is"),
            (~np.isnan(rho) & ((rho < -1.0) | (rho > 1.0)), "rho in [-1, 1]"),
            (~np.isnan(theta) & ((theta < 0.0) | (theta > np.float32(np.pi))), "theta in [0, pi]"),
            ((n < 0) | (n > W), "0 <= n_pairs <= W_rho"),
        ]
    # theta reproduces from the stored rho along each (configuration, k) base path.
    s = lc.sort_values(["config_id", "k", "t"])
    th = np.concatenate([twist(gr["rho"].to_numpy(), cfg["lagcorr.smoothing"]) for _, gr in s.groupby(["config_id", "k"], sort=False, observed=True)])
    bad_theta = np.zeros(len(lc), dtype=bool)
    diff = np.abs(th.astype(np.float64) - s["theta"].to_numpy(np.float64))
    bad_theta[s.index.to_numpy()] = ~((diff <= THETA_TOL) | (np.isnan(th) & np.isnan(s["theta"].to_numpy())))
    rules.append((bad_theta, "theta = arccos of the declared smoothing of rho"))
    for mask, rule in rules:
        if mask.any():
            problems.append(f"{rule}: {int(mask.sum())} rows")
            frames.append(lc.loc[mask, ["series_id", "config_id", "t", "k"]].assign(problem=rule))
    if problems:
        raise AcceptanceError("lagcorr", f"{sid}: " + "; ".join(problems), pd.concat(frames, ignore_index=True) if frames else None)
