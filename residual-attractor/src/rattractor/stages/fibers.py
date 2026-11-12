"""Stage 4b, fibers: series + states + steps -> fibers (the section of the bundle) + fiber_index.

Over each base point (series, origin, ladder, h) the fiber is every coordinate's
standardized residual at once (spec, Residual fiber, Reading B):
    X_k = (y_t - yhat_k(iss, h)) / sigma_k(iss),   iss = o forward, o - H backward
in fiber_index order: admissible configurations in registry order, the fused one
last and flagged (decision 16). X_k equals -u_f of configuration k's steps row and
|X_k| equals r; the stage checks both exactly.

Axes at issuance (decision 17: the W_sigma window, as in the forecast view):
    Z   one-step residuals e1_k(t), t in (iss - W_sigma, iss], centered over the window and
        divided by sigma_k(iss), so Z'Z / (W_sigma - ddof) is their correlation matrix
        (exactly, wherever the sigma floor does not bind)
    u   its leading eigenvector, sign fixed so the loadings sum positive
    w   the leading eigenvector after removing u, sign fixed so its largest |loading| is positive
    lam1, lam2  their eigenvalues
Ties are broken by coordinate order, never by rounding: "largest |loading|" means the first
coordinate within a relative 1e-9 of the largest, and a loading sum within 1e-12 of zero
hands u to that same rule. An axis whose eigenvalue is <= eig_tol x |C| is not determined by
the window: u then falls back to the uniform vector, and w to the first basis vector e_j with
|u_j| <= 1/sqrt(2), made orthogonal to u (two Gram-Schmidt passes); lam records why.
Both use one-step residuals at or before issuance only.

Per step: norm |X|, rms |X| / sqrt|C|, c = X.u, s = X.w, share = c^2 / |X|^2 (NaN where X = 0).
Transport along each origin's path, backward h = 1..H then forward h = 1..H:
    dlog_out = log(|X_next| / |X|), rot_out = arccos of their cosine in degrees,
    NaN at the last step and where either |X| is 0.
issuance_switch marks the backward step 0 -> forward step 1 move, where issuance changes;
it is never pooled with within-ladder moves.
The change in common score and in specific remainder |X - c u| = |X| sqrt(1 - share)
between steps on one ladder follow from c, norm and share, so they are not stored twice.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from ..methods import get_method
from . import AcceptanceError
from .forecast import series_floor

UNIT_TOL = 1e-9    # |u|, |w| = 1 and u.w = 0, in float64 before storage
SIGMA_RTOL = 1e-9  # stored sigma vs sigma recomputed from states
TIE_RTOL = 1e-9    # loadings within this relative distance of the largest count as tied
SUM_TOL = 1e-12    # a loading sum this close to zero cannot fix u's sign


def fiber_index(registry: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The fiber coordinates: admissible configurations in registry order, fused last."""
    adm = registry[registry["admissible"]]
    fused = np.array([get_method(str(m), cfg).is_fusion for m in adm["method"]], dtype=bool)
    order = list(adm["config_id"][~fused])
    flags = [False] * len(order)
    if cfg["fibers.include_fused"]:
        fused_ids = list(adm["config_id"][fused])
        if not fused_ids:
            raise AcceptanceError("fibers", "fibers.include_fused is true but the registry has no admissible fused configuration")
        order += fused_ids
        flags += [True] * len(fused_ids)
    if len(order) < 2:
        raise AcceptanceError("fibers", f"a fiber needs at least 2 coordinates; the registry gives {len(order)}")
    return contracts.from_columns(
        {"k": np.arange(len(order)), "config_id": np.array(order, dtype=object), "is_fused": np.array(flags)},
        "fiber_index",
    )


def lead(v: np.ndarray) -> np.ndarray | int:
    """Index of the largest |loading|, ties within TIE_RTOL going to the first coordinate.

    Works on one vector (returns an int) or row-wise on a matrix (returns an index per row).
    """
    a = np.abs(v)
    top = a.max(axis=-1, keepdims=True)
    idx = np.argmax(a >= top * (1.0 - TIE_RTOL), axis=-1)
    return int(idx) if np.ndim(idx) == 0 else idx


def _sign_max_positive(v: np.ndarray) -> np.ndarray:
    return v if v[lead(v)] > 0 else -v


def _sign_sum_positive(v: np.ndarray) -> np.ndarray:
    total = float(v.sum())
    if abs(total) <= SUM_TOL:  # the loadings cancel: the largest-loading rule decides
        return _sign_max_positive(v)
    return v if total > 0 else -v


def _orthogonal_fallback(u: np.ndarray) -> np.ndarray:
    """e_j for the first j with |u_j| <= 1/sqrt(2), made orthogonal to u and unit length.

    Such a j exists for any unit u with |C| >= 2, and |e_j - u_j u|^2 = 1 - u_j^2 >= 1/2,
    so nothing cancels; the second Gram-Schmidt pass removes what rounding leaves along u.
    """
    j = int(np.flatnonzero(np.abs(u) <= np.sqrt(0.5) + TIE_RTOL)[0])
    v = -u[j] * u
    v[j] += 1.0
    v -= (u @ v) * u
    return v / np.linalg.norm(v)


def axes(z: np.ndarray, ddof: int, tol: float) -> tuple[np.ndarray, np.ndarray, float, float]:
    """(u, w, lam1, lam2) from a W x K window of centered, sigma-scaled one-step residuals."""
    W, K = z.shape
    _, sv, vt = np.linalg.svd(z, full_matrices=False)
    lam = sv * sv / (W - ddof)
    lam1 = float(lam[0]) if lam.size > 0 else 0.0
    lam2 = float(lam[1]) if lam.size > 1 else 0.0
    thr = tol * K
    u = vt[0].copy() if lam1 > thr else np.full(K, 1.0 / np.sqrt(K))
    u = _sign_sum_positive(u)
    w = vt[1].copy() if (lam1 > thr and lam2 > thr) else _orthogonal_fallback(u)
    return u, _sign_max_positive(w), lam1, lam2


def _pivot(frame: pd.DataFrame, index, value: str, coords: list[str]) -> pd.DataFrame:
    p = frame.pivot(index=index, columns="config_id", values=value)
    missing = sorted(set(coords) - set(p.columns))
    if missing:
        raise AcceptanceError("fibers", f"no {value} rows for fiber coordinates {missing[:5]}")
    return p.sort_index()[coords]


def compute_series(sid: str, g: pd.DataFrame, states: pd.DataFrame, steps: pd.DataFrame, cfg: dict,
                   index: pd.DataFrame) -> dict[str, np.ndarray]:
    """The fibers columns for one series, before the acceptance check (x float32, the rest float64)."""
    coords = index["config_id"].tolist()
    K = len(coords)
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

    # The fiber and the node-table invariant: X_k = -u_f and |X_k| = r, exactly in storage precision.
    e, sig = piv["e"].to_numpy(), piv["sigma"].to_numpy()
    X = e / sig
    x32 = X.astype(np.float32)
    uf, r = piv["u_f"].to_numpy(np.float32), piv["r"].to_numpy(np.float32)
    bad = (x32 != -uf) | (np.abs(x32) != r)
    if bad.any():
        rr, kk = np.nonzero(bad)
        rows = pd.DataFrame({"series_id": sid, "origin": origin[rr], "ladder": ladder[rr], "h": h[rr],
                             "config_id": np.array(coords, dtype=object)[kk], "x": x32[rr, kk], "u_f": uf[rr, kk], "r": r[rr, kk]})
        raise AcceptanceError("fibers", f"{sid}: {int(bad.sum())} coordinates break X = -u_f or |X| = r", rows)

    # Axes at each issuance from the W_sigma one-step residuals ending there.
    uniq = np.unique(iss)
    first = {int(i): int(np.argmax(iss == i)) for i in uniq}
    U, Wv, lam = np.empty((uniq.size, K)), np.empty((uniq.size, K)), np.empty((uniq.size, 2))
    sig_bad = []
    for j, i in enumerate(uniq):
        lo = int(i) - W + 1
        if lo < 1:
            raise AcceptanceError("fibers", f"{sid}: issuance {i} has fewer than W_sigma one-step residuals")
        win = E[lo : i + 1]
        s_steps = sig[first[int(i)]]
        s_states = np.maximum(win.std(axis=0, ddof=ddof), floor)
        for k in np.flatnonzero(~np.isclose(s_states, s_steps, rtol=SIGMA_RTOL, atol=0.0)):
            sig_bad.append((sid, int(i), coords[k], float(s_steps[k]), float(s_states[k])))
        z = (win - win.mean(axis=0)) / s_steps
        U[j], Wv[j], lam[j, 0], lam[j, 1] = axes(z, ddof, cfg["fibers.eig_tol"])
    if sig_bad:
        raise AcceptanceError("fibers", f"{sid}: sigma in steps disagrees with the one-step residuals in states at {len(sig_bad)} (issuance, configuration) pairs",
                              pd.DataFrame(sig_bad, columns=["series_id", "issuance", "config_id", "sigma_steps", "sigma_states"]))
    pos = np.searchsorted(uniq, iss)
    u_rows, w_rows, lam_rows = U[pos], Wv[pos], lam[pos]

    # Per-step quantities.
    norm = np.sqrt((X * X).sum(axis=1))
    c = (X * u_rows).sum(axis=1)
    s = (X * w_rows).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(norm > 0, c * c / (norm * norm), np.nan)

    # Transport to the next step on the same origin's path.
    nxt = _has_next(origin)
    rot, dlog = np.full(R, np.nan), np.full(R, np.nan)
    j = np.flatnonzero(nxt)
    j = j[(norm[j] > 0) & (norm[j + 1] > 0)]
    cos = np.clip((X[j] * X[j + 1]).sum(axis=1) / (norm[j] * norm[j + 1]), -1.0, 1.0)
    rot[j] = np.degrees(np.arccos(cos))
    dlog[j] = np.log(norm[j + 1] / norm[j])
    switch = np.zeros(R, dtype=bool)
    switch[:-1] = nxt[:-1] & (ladder[:-1] == "backward") & (h[:-1] == H) & (ladder[1:] == "forward") & (h[1:] == 1)

    if x32.shape[1] != K or u_rows.shape[1] != K or w_rows.shape[1] != K:
        raise AcceptanceError("fibers", f"{sid}: x, u, w lengths differ from |C| = {K}")
    return {
        "series_id": np.full(R, sid, dtype=object),
        "origin": origin, "ladder": ladder, "h": h,
        "step": np.where(ladder == "backward", h - H, h),
        "issuance": iss,
        "x": x32, "u": u_rows, "w": w_rows,
        "lam1": lam_rows[:, 0], "lam2": lam_rows[:, 1],
        "norm": norm, "rms": norm / np.sqrt(K), "c": c, "s": s, "share": share,
        "rot_out": rot, "dlog_out": dlog, "issuance_switch": switch,
    }


def _has_next(origin: np.ndarray) -> np.ndarray:
    """True where the next row is a later step of the same origin (rows sorted by origin, ladder, h)."""
    nxt = np.zeros(origin.size, dtype=bool)
    nxt[:-1] = origin[1:] == origin[:-1]
    return nxt


def run_series(sid: str, g: pd.DataFrame, states: pd.DataFrame, steps: pd.DataFrame, cfg: dict,
               index: pd.DataFrame) -> pd.DataFrame:
    cols = compute_series(sid, g, states, steps, cfg, index)
    check(sid, len(g), cfg["horizon.H"], cols)
    return contracts.from_columns(cols, "fibers")


def check(sid: str, n: int, H: int, cols: dict) -> None:
    """Every row-level rule of the fiber; a failure carries the failing rows and the rule each broke."""
    origin, ladder, h, iss = cols["origin"], cols["ladder"], cols["h"], cols["issuance"]
    U, Wv = np.asarray(cols["u"], dtype=np.float64), np.asarray(cols["w"], dtype=np.float64)
    norm, c, s, share = cols["norm"], cols["c"], cols["s"], cols["share"]
    rot, dlog, switch = cols["rot_out"], cols["dlog_out"], cols["issuance_switch"]
    nxt = _has_next(origin)
    fwd = ladder == "forward"
    step0 = (ladder == "backward") & (h == H)
    has_fwd = np.isin(origin, origin[fwd])
    share_ok = ~np.isnan(share)
    rot_ok = ~np.isnan(rot)
    rules = [
        (np.where(fwd, iss != origin, iss != origin - H), "issuance is not o forward and o - H backward"),
        (np.abs(np.linalg.norm(U, axis=1) - 1.0) > UNIT_TOL, "u is not unit length"),
        (np.abs(np.linalg.norm(Wv, axis=1) - 1.0) > UNIT_TOL, "w is not unit length"),
        (np.abs((U * Wv).sum(axis=1)) > UNIT_TOL, "u and w are not orthogonal"),
        (U.sum(axis=1) < -SUM_TOL, "u loadings sum negative"),
        (Wv[np.arange(Wv.shape[0]), lead(Wv)] <= 0, "w's largest loading is not positive"),
        (share_ok & ((share < 0) | (share > 1 + 1e-12)), "share outside [0, 1]"),
        (c * c + s * s > norm * norm * (1 + 1e-9) + 1e-12, "c^2 + s^2 exceeds |X|^2 although u and w are orthonormal"),
        (share_ok == (norm == 0), "share is null somewhere other than X = 0"),
        (rot_ok & ((rot < 0) | (rot > 180)), "rot_out outside [0, 180] degrees"),
        (~nxt & (rot_ok | ~np.isnan(dlog)), "rot_out or dlog_out set at the last step of an origin"),
        (step0 & (switch != has_fwd), "issuance_switch missing, or set where no forward step follows"),
        (switch & ~step0, "issuance_switch on a row other than backward step 0"),
    ]
    failed = [(mask, rule) for mask, rule in rules if mask.any()]
    expected = int(sum(H + min(H, n - 1 - o) for o in np.unique(origin)))
    count_ok = origin.size == expected
    if failed or not count_ok:
        rows = pd.concat([
            pd.DataFrame({"series_id": sid, "origin": origin[m], "ladder": ladder[m], "h": h[m], "problem": rule})
            for m, rule in failed
        ], ignore_index=True) if failed else None
        msgs = [rule for _, rule in failed] + ([] if count_ok else [f"row count {origin.size} != {expected} (2H per origin less truncation)"])
        raise AcceptanceError("fibers", f"{sid}: " + "; ".join(msgs), rows)
