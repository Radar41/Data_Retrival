"""Stage 4, forecast: series + registry + states -> steps (the node table).

For every admissible configuration c and base origin o in the test split:
  forward ladder  (c, o, h = 1..H):      issued at o, landing on o + h (rows past N - 1 truncated)
  backward ladder (c, o - H, h = 1..H):  issued H steps earlier, the last step landing on o
Each row is scaled by sigma at its issuance, so it uses data at or before issuance only:
  sigma(c, iss)  sd of the one-step residuals e1 over the W_sigma steps ending at iss, floored
  sigma_h        sigma x sqrt(sum psi_j^2, j < h): model-implied h-step sd (decision 1, stored beside)
  u_f = (yhat - y)/sigma, r = |u_f|, r_h = |e|/sigma_h, u_s = (s1 - y)/sigma, v_s = s2/sigma2(M)
  sigma2(M)      RMS of in-sample s2 over every configuration of method M on the training span of this
                 series (decision 13: per series), floored like sigma.
Origins run from o_min = test start + max(W_sigma, W_rho, H) (decision 14) to N - 1, every origins.stride.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from ..methods import Fitted, get_method
from . import AcceptanceError
from .fit import configs, fit_series


def origins(n: int, test_start: int, cfg: dict) -> np.ndarray:
    o_min = test_start + max(cfg["sigma.window"], cfg["lagcorr.window"], cfg["horizon.H"])
    return np.arange(o_min, n, cfg["origins.stride"])


def series_floor(y_train: np.ndarray, cfg: dict) -> float:
    """sigma.floor = floor_factor x training-span sd; a flat training span uses its level (or 1) instead."""
    scale = float(np.std(y_train, ddof=cfg["sigma.ddof"])) if y_train.size > cfg["sigma.ddof"] else 0.0
    if scale == 0.0:
        scale = max(abs(float(np.mean(y_train))), 1.0)
    return cfg["sigma.floor_factor"] * scale


def rolling_sigma(e1: np.ndarray, cfg: dict, floor: float) -> np.ndarray:
    """sigma at each t over e1[t - W + 1 .. t]; NaN where the window reaches t = 0 (e1 undefined there).

    Two-pass per window (mean, then deviations), so a large residual mean costs no digits.
    """
    W = cfg["sigma.window"]
    out = np.full(e1.size, np.nan)
    if e1.size >= W:
        out[W - 1 :] = np.lib.stride_tricks.sliding_window_view(e1, W).std(axis=1, ddof=cfg["sigma.ddof"])
    return np.maximum(out, floor)  # NaN stays NaN


def _verify_states(sid: str, fs: dict[str, Fitted], states: pd.DataFrame) -> None:
    st = states[states["series_id"] == sid]
    bad = []
    for cid, f in fs.items():
        rows = st[st["config_id"] == cid]
        if len(rows) != f.y.size:
            bad.append((sid, cid, "row count"))
            continue
        for name in ("yhat1", "s1", "s2"):
            if not np.array_equal(rows[name].to_numpy(), getattr(f, name), equal_nan=True):
                bad.append((sid, cid, name))
    if bad:
        raise AcceptanceError("forecast", "states artifact disagrees with the fit", pd.DataFrame(bad, columns=["series_id", "config_id", "field"]))


def run_series(sid: str, g: pd.DataFrame, registry: pd.DataFrame, states: pd.DataFrame, cfg: dict,
               fitted: dict[str, Fitted] | None = None) -> pd.DataFrame:
    y = g["y"].to_numpy()
    n, H = y.size, cfg["horizon.H"]
    test = (g["split"] == "test").to_numpy()
    ts = int(np.argmax(test))
    O = origins(n, ts, cfg)
    if O.size == 0:
        raise AcceptanceError("forecast", f"{sid}: no origins; N = {n}, test starts at {ts}, o_min = {ts + max(cfg['sigma.window'], cfg['lagcorr.window'], H)}")
    if O[0] - H - cfg["sigma.window"] + 1 < 1:
        raise AcceptanceError("forecast", f"{sid}: the first backward issuance {O[0] - H} has fewer than W_sigma one-step residuals before it")

    fs = fitted if fitted is not None else fit_series(y, registry, cfg)
    _verify_states(sid, fs, states)
    cl = configs(registry)
    floor = series_floor(y[:ts], cfg)
    sigma2 = {}
    for m in {m for _, m, _ in cl}:
        s2 = np.concatenate([fs[c].s2[:ts] for c, mm, _ in cl if mm == m])
        sigma2[m] = max(float(np.sqrt(np.mean(s2 * s2))), floor)

    # Row layout, shared by every configuration: forward then backward per origin.
    h = np.arange(1, H + 1)
    o_f, h_f = np.repeat(O, H), np.tile(h, O.size)
    keep = o_f + h_f <= n - 1
    o_f, h_f = o_f[keep], h_f[keep]
    o_b, h_b = np.repeat(O, H), np.tile(h, O.size)
    origin = np.concatenate([o_f, o_b])
    hh = np.concatenate([h_f, h_b])
    issuance = np.concatenate([o_f, o_b - H])
    ladder = np.array(["forward"] * o_f.size + ["backward"] * o_b.size, dtype=object)
    t_target = issuance + hh
    tau = np.concatenate([h_f / H, (h_b - H) / H])
    iss_all = np.unique(issuance)
    pos = np.searchsorted(iss_all, issuance)
    yt = y[t_target]
    rows_per = origin.size

    out = {k: [] for k in ("config_id", "yhat", "e", "sigma", "sigma_h", "u_f", "r", "r_h", "u_s", "v_s", "s1", "s2")}
    for cid, m, theta in cl:
        meth, f = get_method(m, cfg), fs[cid]
        S1 = np.empty((iss_all.size, H))
        S2 = np.empty((iss_all.size, H))
        for i, o in enumerate(iss_all):
            S1[i], S2[i] = meth.state_forward(f, int(o), H)
        Y = meth.forecast_from_state(S1, S2)
        yhat, s1, s2 = Y[pos, hh - 1], S1[pos, hh - 1], S2[pos, hh - 1]
        sig = rolling_sigma(f.e1, cfg, floor)[issuance]
        sig_h = sig * meth.sigma_h_factor(theta, H)[hh - 1]
        e = yt - yhat
        out["config_id"].append(np.full(rows_per, cid, dtype=object))
        for k, v in (("yhat", yhat), ("e", e), ("sigma", sig), ("sigma_h", sig_h), ("u_f", -e / sig), ("r", np.abs(e) / sig),
                     ("r_h", np.abs(e) / sig_h), ("u_s", (s1 - yt) / sig), ("v_s", s2 / sigma2[m]), ("s1", s1), ("s2", s2)):
            out[k].append(v)

    k = len(cl)
    data = {key: np.concatenate(v) for key, v in out.items()}
    data["u_f"] = data["u_f"].astype(np.float32)
    data["r"] = np.abs(data["u_f"])  # r = |u_f| exactly, in the stored precision
    data.update({
        "series_id": np.full(rows_per * k, sid, dtype=object),
        "origin": np.tile(origin, k), "ladder": np.tile(ladder, k), "h": np.tile(hh, k),
        "issuance": np.tile(issuance, k), "t_target": np.tile(t_target, k), "y": np.tile(yt, k),
        "tau": np.tile(tau, k),
        "window_spans_break": [pd.NA] * (rows_per * k), "cell_id": [pd.NA] * (rows_per * k),
    })
    steps = contracts.from_columns(data, "steps")
    check(steps, n, O, k, H)
    return steps


def check(steps: pd.DataFrame, n: int, O: np.ndarray, k: int, H: int) -> None:
    expected = k * int(sum(H + min(H, n - 1 - o) for o in O))
    if len(steps) != expected:
        raise AcceptanceError("forecast", f"row count {len(steps)} != |C| x sum over origins of 2H less truncation = {expected}")
    uf = steps["u_f"].to_numpy(np.float64)
    bad = np.abs(steps["r"].to_numpy(np.float64) - np.abs(uf)) > 1e-9
    e = steps["y"].to_numpy() - steps["yhat"].to_numpy()
    bad |= np.abs(e - steps["e"].to_numpy()) > 1e-9 * np.maximum(1.0, np.abs(steps["y"].to_numpy()))
    bad |= ~(steps["sigma"].to_numpy() > 0)
    if bad.any():
        raise AcceptanceError("forecast", f"{int(bad.sum())} rows break the circle invariant r = |u_f| or e = y - yhat", steps[bad])


def run(series: pd.DataFrame, registry: pd.DataFrame, states: pd.DataFrame, cfg: dict,
        fitted: dict[str, dict[str, Fitted]] | None = None) -> dict[str, pd.DataFrame]:
    """{series_id: steps frame}; one frame per series so a build writes and reads them one at a time."""
    return {
        str(sid): run_series(str(sid), g, registry, states, cfg, None if fitted is None else fitted[str(sid)])
        for sid, g in series.groupby("series_id", sort=False, observed=True)
    }
