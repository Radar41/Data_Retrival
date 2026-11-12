"""Stage 4b, fibers: series + states + steps -> fibers (the section of the bundle) + fiber_index.

The fiber over a base point (series, origin, ladder, h) is the collection of every
configuration's standardized residual at that point (spec, Residual fiber, Reading B):
    X_k = (y_t - yhat_k(iss, h)) / sigma_k(iss),   iss = o forward, o - H backward
in fiber_index order (admissible configurations in registry order). Each X_k is one
configuration's own residual on its own scale: X_k = -u_f of configuration k's steps row
and |X_k| = r, checked exactly.

The bundle is a collection of points and nothing more. Nothing here combines residuals
across configurations: no fused coordinate, no axes, norms, scores or shares. Every later
step acts on each retained residual individually; any decomposition across configurations
belongs to the analyses that run on the finished archive.

step numbers the path through the origin (h - H backward, h forward), and issuance_switch
marks the backward step 0 -> forward step 1 move, where the issuance changes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError
from .forecast import series_floor

SIGMA_RTOL = 1e-9  # stored sigma vs sigma recomputed from states


def fiber_index(registry: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The fiber coordinates: admissible configurations in registry order (register refuses none)."""
    order = list(registry.loc[registry["admissible"], "config_id"])
    return contracts.from_columns({"k": np.arange(len(order)), "config_id": np.array(order, dtype=object)}, "fiber_index")


def _pivot(frame: pd.DataFrame, index, value: str, coords: list[str]) -> pd.DataFrame:
    p = frame.pivot(index=index, columns="config_id", values=value)
    missing = sorted(set(coords) - set(p.columns))
    if missing:
        raise AcceptanceError("fibers", f"no {value} rows for fiber coordinates {missing[:5]}")
    return p.sort_index()[coords]


def _has_next(origin: np.ndarray) -> np.ndarray:
    """True where the next row is a later step of the same origin (rows sorted by origin, ladder, h)."""
    nxt = np.zeros(origin.size, dtype=bool)
    nxt[:-1] = origin[1:] == origin[:-1]
    return nxt


def compute_series(sid: str, g: pd.DataFrame, states: pd.DataFrame, steps: pd.DataFrame, cfg: dict,
                   index: pd.DataFrame) -> dict[str, np.ndarray]:
    """The fibers columns for one series, before the acceptance check."""
    coords = index["config_id"].tolist()
    H, W, ddof = cfg["horizon.H"], cfg["sigma.window"], cfg["sigma.ddof"]
    y = g["y"].to_numpy()
    n = y.size
    ts = int(np.argmax((g["split"] == "test").to_numpy()))
    floor = series_floor(y[:ts], cfg)

    st = states[(states["series_id"] == sid) & states["config_id"].isin(coords)]
    Ef = _pivot(st, "t", "e1", coords)
    if not np.array_equal(Ef.index.to_numpy(), np.arange(n)):
        raise AcceptanceError("fibers", f"{sid}: states do not cover t = 0..{n - 1} for every coordinate")
    E = Ef.to_numpy()

    sp = steps[(steps["series_id"] == sid) & steps["config_id"].isin(coords)]
    key = ["origin", "ladder", "h"]
    piv = {v: _pivot(sp, key, v, coords) for v in ("e", "sigma", "u_f", "r", "issuance", "t_target")}
    if any(p.isna().to_numpy().any() for p in piv.values()):
        raise AcceptanceError("fibers", f"{sid}: some (origin, ladder, h) lack a steps row for some coordinate")
    keys = piv["e"].index
    R = len(keys)
    iss_all, tt_all = piv["issuance"].to_numpy(), piv["t_target"].to_numpy()
    if (iss_all != iss_all[:, :1]).any() or (tt_all != tt_all[:, :1]).any():
        raise AcceptanceError("fibers", f"{sid}: coordinates disagree on issuance or t_target at one (origin, ladder, h)")
    iss = iss_all[:, 0].astype(np.int64)
    origin = keys.get_level_values("origin").to_numpy().astype(np.int64)
    ladder = np.asarray(keys.get_level_values("ladder").astype(str))
    h = keys.get_level_values("h").to_numpy().astype(np.int64)

    # The node-table invariant: X_k = -u_f and |X_k| = r, exactly in storage precision.
    e, sig = piv["e"].to_numpy(), piv["sigma"].to_numpy()
    x32 = (e / sig).astype(np.float32)
    uf, r = piv["u_f"].to_numpy(np.float32), piv["r"].to_numpy(np.float32)
    bad = (x32 != -uf) | (np.abs(x32) != r)
    if bad.any():
        rr, kk = np.nonzero(bad)
        rows = pd.DataFrame({"series_id": sid, "origin": origin[rr], "ladder": ladder[rr], "h": h[rr],
                             "config_id": np.array(coords, dtype=object)[kk], "x": x32[rr, kk], "u_f": uf[rr, kk], "r": r[rr, kk]})
        raise AcceptanceError("fibers", f"{sid}: {int(bad.sum())} coordinates break X = -u_f or |X| = r", rows)

    # Each configuration's sigma in steps must be its own one-step residual sd at that issuance.
    first = {int(i): int(np.argmax(iss == i)) for i in np.unique(iss)}
    sig_bad = []
    for i, row in first.items():
        lo = i - W + 1
        if lo < 1:
            raise AcceptanceError("fibers", f"{sid}: issuance {i} has fewer than W_sigma one-step residuals")
        s_states = np.maximum(E[lo : i + 1].std(axis=0, ddof=ddof), floor)
        for k in np.flatnonzero(~np.isclose(s_states, sig[row], rtol=SIGMA_RTOL, atol=0.0)):
            sig_bad.append((sid, i, coords[k], float(sig[row][k]), float(s_states[k])))
    if sig_bad:
        raise AcceptanceError("fibers", f"{sid}: sigma in steps disagrees with the one-step residuals in states at {len(sig_bad)} (issuance, configuration) pairs",
                              pd.DataFrame(sig_bad, columns=["series_id", "issuance", "config_id", "sigma_steps", "sigma_states"]))

    nxt = _has_next(origin)
    switch = np.zeros(R, dtype=bool)
    switch[:-1] = nxt[:-1] & (ladder[:-1] == "backward") & (h[:-1] == H) & (ladder[1:] == "forward") & (h[1:] == 1)
    return {
        "series_id": np.full(R, sid, dtype=object),
        "origin": origin, "ladder": ladder, "h": h,
        "step": np.where(ladder == "backward", h - H, h),
        "issuance": iss,
        "x": x32,
        "issuance_switch": switch,
    }


def run_series(sid: str, g: pd.DataFrame, states: pd.DataFrame, steps: pd.DataFrame, cfg: dict,
               index: pd.DataFrame) -> pd.DataFrame:
    cols = compute_series(sid, g, states, steps, cfg, index)
    check(sid, len(g), cfg["horizon.H"], len(index), cols)
    return contracts.from_columns(cols, "fibers")


def check(sid: str, n: int, H: int, K: int, cols: dict) -> None:
    """Row-level rules of the fiber; a failure carries the failing rows and the rule each broke."""
    origin, ladder, h, iss = cols["origin"], cols["ladder"], cols["h"], cols["issuance"]
    switch = cols["issuance_switch"]
    fwd = ladder == "forward"
    step0 = (ladder == "backward") & (h == H)
    has_fwd = np.isin(origin, origin[fwd])
    rules = [
        (np.where(fwd, iss != origin, iss != origin - H), "issuance is not o forward and o - H backward"),
        (step0 & (switch != has_fwd), "issuance_switch missing, or set where no forward step follows"),
        (switch & ~step0, "issuance_switch on a row other than backward step 0"),
    ]
    failed = [(mask, rule) for mask, rule in rules if mask.any()]
    expected = int(sum(H + min(H, n - 1 - o) for o in np.unique(origin)))
    msgs = [rule for _, rule in failed]
    if origin.size != expected:
        msgs.append(f"row count {origin.size} != {expected} (2H per origin less truncation)")
    if np.asarray(cols["x"]).shape[1] != K:
        msgs.append(f"x has length {np.asarray(cols['x']).shape[1]}, the fiber has {K} coordinates")
    if msgs:
        rows = pd.concat([
            pd.DataFrame({"series_id": sid, "origin": origin[m], "ladder": ladder[m], "h": h[m], "problem": rule})
            for m, rule in failed
        ], ignore_index=True) if failed else None
        raise AcceptanceError("fibers", f"{sid}: " + "; ".join(msgs), rows)
