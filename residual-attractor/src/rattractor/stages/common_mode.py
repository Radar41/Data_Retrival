"""Common mode: rdiag's Stage 3 common_mode under input contract v2, inside each configuration.

Is there a direction the series are being pulled toward, how hard, and which series are in it.
Reads the grid (stage 9) and nothing else. Every value below comes from one configuration k's
own rows resid[k, :, :]; no value is computed from two configurations (the archive rule).

For configuration k and month t, over the trailing window of common_mode.window months ending at t:

    C(k, t)           the N x N Pearson correlation across series of resid[k, i, t - w + 1 .. t]
    eigenvalue        the eigenvalues of C, descending (rank r = 0 is the leading one); they sum to N
    lambda1           the leading eigenvalue
    loading           the unit leading eigenvector, signed so that its sum is >= 0 (common.linalg)
    absorption_ratio  the top ceil(N x common_mode.absorption_top_fraction) eigenvalues over N
    vector_turnover   the angle between the loadings at t and at t - 1, radians in [0, pi]. Above pi / 2
                      the sign rule has turned the vector over between the two months (its loadings
                      nearly cancel): the axis itself moved by pi minus the value.
    lambda1_q        the common_mode.quantile quantile (numpy.quantile, linear) of the leading
                      eigenvalue over surrogates.n_common_mode circular-shift surrogates of the
                      configuration's rows, every row shifted by its own offset in each draw
                      (common.surrogates, purpose "common_mode", unit (i,)); the same window at t
    p_value           (1 + #{surrogate lambda1 >= lambda1}) / (1 + n_surrogates), one-sided
    mp_edge           (1 + sqrt(N / w))^2, the Marchenko-Pastur edge: a reference line only. It assumes
                      rows with no autocorrelation; the surrogate band is the test, because a shift
                      keeps each row's autocorrelation and breaks only its alignment with the others.

Writes common_mode_month (k, t), common_mode_eigen (k, t, r) and common_mode_vector (k, t, i), every
month of the grid in each. A value is null where it is undefined: before the first full window; with
fewer than two series; where a row is flat over the window (max == min, no correlation exists); and
for vector_turnover also at the first month after any of these. A surrogate draw in which a shifted
row's window is flat is left out, and n_surrogates counts the draws that entered the band and the
p-value (0, and both null, where lambda1 is null or no draw is left).

Departures from rdiag (s3_cooccurrence/common_mode.py, schemas/30_stage3.yaml):
- "fused rows" are each configuration's own rows, and k is in every key.
- lambda1, p_value and n_surrogates are stored beside lambda1_q, so the per-month test rdiag registers
  in its inference registry sits in this table with the keys of the unit it tests (k, t). No registry
  is written here; the false-discovery stage reads the table.
- mp_edge is a column of common_mode_month, not a one-row attributes table.
- the surrogate recipes are not stored (common.surrogates gives them back from the seed).
- rdiag does not say what a flat row or a single series gives; both give nulls here.
- the top count ceil(N x fraction) reads the fraction as the decimal the config states (0.2 is 1/5),
  so a product that is a whole number is never rounded up by binary floating point.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .. import contracts
from ..common import linalg, surrogates
from . import AcceptanceError

PURPOSE = "common_mode"   # the surrogate purpose: every row its own offset per draw
EIG_TOL = 1e-10           # rdiag: eigenvalues sum to N to 1e-10; the leading vector has unit length to 1e-10
VEC_TOL = 1e-8            # C v = lambda1 v, checked on every build
_CHUNK = 1 << 22          # window values gathered at once for the surrogates; memory only, no effect on any value


def top_count(N: int, fraction: float) -> int:
    """ceil(N x fraction), the fraction read as the decimal the config states."""
    f = Fraction(str(fraction))
    return int(-(-N * f.numerator // f.denominator))


def unit_windows(X: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """(Z, flat) for rows X (N, P), P >= w.

    Z[i, s] is row i's circular window of w months ending at month s, centred and scaled to unit
    length, so the correlation of rows i and j over windows ending at s_i and s_j is Z[i, s_i] . Z[j, s_j].
    The windows ending at s >= w - 1 do not wrap: they are the trailing windows of the row itself.
    flat[i, s] marks a window with no spread (max == min); its Z is zero and it has no correlation.
    """
    P = X.shape[1]
    W = sliding_window_view(np.concatenate([X[:, P - (w - 1):], X], axis=1), w, axis=1)   # (N, P, w)
    c = W - W.mean(axis=2, keepdims=True)
    ss = (c * c).sum(axis=2)
    flat = (W.max(axis=2) == W.min(axis=2)) | (ss == 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        Z = np.where(flat[..., None], 0.0, c / np.sqrt(ss)[..., None])
    return Z, flat


def _gram(Z: np.ndarray) -> np.ndarray:
    """Z Z' for unit windows Z (..., N, w): the correlation matrices across the N rows."""
    return Z @ np.swapaxes(Z, -1, -2)


def configuration(X: np.ndarray, offsets: np.ndarray, w: int, q: float, n_top: int) -> dict[str, np.ndarray]:
    """Every per-month value of one configuration, from its own rows X (N, P) and its rows' offsets (N, B).

    Returns arrays over the T = P - w + 1 months that have a full window, NaN where undefined.
    """
    N, P = X.shape
    tt = np.arange(w - 1, P)
    T, B = tt.size, offsets.shape[1]
    Z, flat = unit_windows(X, w)
    any_flat = bool(flat.any())

    # the configuration as it is: the trailing windows of its own rows. The eigenvalues come from the
    # routine the surrogates use (eigvalsh on the same product), so a draw that reproduces these
    # windows ties with them exactly; eigh gives the vector.
    seen = ~flat[:, tt].any(axis=0)
    C = _gram(Z[:, tt].transpose(1, 0, 2))                             # (T, N, N)
    C[~seen] = np.eye(N)
    vals = np.linalg.eigvalsh(C)[:, ::-1].copy()
    lead = linalg.eigh_desc(C)[1][:, :, 0].copy()
    vals[~seen], lead[~seen] = np.nan, np.nan
    lam1 = vals[:, 0]
    turnover = np.full(T, np.nan)
    turnover[1:] = linalg.angle(lead[1:], lead[:-1])                   # NaN where either month is undefined

    # the same windows on the surrogates: row i reads its own circular window ending at t + offset_i
    rows = np.arange(N)[:, None, None]
    lam = np.empty((B, T))
    step = max(1, _CHUNK // (T * N * w))
    for b0 in range(0, B, step):
        src = (tt[None, None, :] + offsets[:, b0:b0 + step, None]) % P  # (N, b, T)
        G = _gram(Z[rows, src].transpose(1, 2, 0, 3))                   # (b, T, N, N)
        if any_flat:
            dropped = flat[rows, src].any(axis=0)                       # (b, T): a shifted row's window is flat
            G[dropped] = np.eye(N)
        top = np.linalg.eigvalsh(G)[..., -1]
        if any_flat:
            top[dropped] = np.nan
        lam[b0:b0 + step] = top
    lam[:, ~seen] = np.nan                                              # no test where the month itself is undefined
    counted = ~np.isnan(lam)
    n = counted.sum(axis=0)
    with np.errstate(invalid="ignore"):
        p = (1 + (lam >= lam1[None, :]).sum(axis=0)) / (1 + n)
    if (n == B).all():
        band = np.quantile(lam, q, axis=0)
    else:
        band = np.array([np.quantile(lam[counted[:, j], j], q) if n[j] else np.nan for j in range(T)])
    return {"eigenvalue": vals, "loading": lead, "lambda1": lam1, "lambda1_q": band, "p_value": np.where(n > 0, p, np.nan),
            "n_surrogates": n, "absorption_ratio": vals[:, :n_top].sum(axis=1) / N, "vector_turnover": turnover,
            "flat_months": int((~seen).sum()), "draws_dropped": int(B * int(seen.sum()) - int(n.sum()))}


def _field(frames: dict[str, pd.DataFrame]) -> tuple[np.ndarray, np.ndarray]:
    """(resid as (K, N, P), months ascending)."""
    r, months = frames["grid_resid"], np.sort(frames["grid_month"]["t"].to_numpy())
    R = np.empty((len(frames["grid_config"]), len(frames["grid_series"]), months.size))
    R[r["k"].to_numpy(), r["i"].to_numpy(), np.searchsorted(months, r["t"].to_numpy())] = r["resid"].to_numpy()
    return R, months


def run(frames: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    R, months = _field(frames)
    K, N, P = R.shape
    w, B, q = cfg["common_mode.window"], cfg["surrogates.n_common_mode"], cfg["common_mode.quantile"]
    n_top, edge = top_count(N, cfg["common_mode.absorption_top_fraction"]), linalg.mp_edge(N, w)
    per_month = {c: np.full((K, P), np.nan) for c in ("lambda1", "lambda1_q", "p_value", "absorption_ratio", "vector_turnover")}
    n_sur = np.zeros((K, P), dtype=np.int64)
    eig, vec = np.full((K, P, N), np.nan), np.full((K, P, N), np.nan)
    flat_months = draws_dropped = 0
    defined = N >= 2 and P >= w   # a correlation across series needs two series and one full window
    if defined:
        for k in range(K):  # one configuration at a time, from its own rows and its own draws
            off = np.stack([surrogates.offsets(cfg, PURPOSE, P, B, k, i) for i in range(N)])
            out = configuration(R[k], off, w, q, n_top)
            for c in per_month:
                per_month[c][k, w - 1:] = out[c]
            n_sur[k, w - 1:], eig[k, w - 1:], vec[k, w - 1:] = out["n_surrogates"], out["eigenvalue"], out["loading"]
            flat_months += out["flat_months"]
            draws_dropped += out["draws_dropped"]

    kk, tt = np.repeat(np.arange(K), P), np.tile(months, K)
    ke, te, je = np.repeat(kk, N), np.repeat(tt, N), np.tile(np.arange(N), K * P)   # (k, t, rank or series)
    built = {
        "common_mode_month": contracts.from_columns({
            "k": kk, "t": tt, "lambda1": per_month["lambda1"].reshape(-1), "lambda1_q": per_month["lambda1_q"].reshape(-1),
            "p_value": per_month["p_value"].reshape(-1), "n_surrogates": n_sur.reshape(-1), "mp_edge": np.full(K * P, edge),
            "absorption_ratio": per_month["absorption_ratio"].reshape(-1), "vector_turnover": per_month["vector_turnover"].reshape(-1),
        }, "common_mode_month"),
        "common_mode_eigen": contracts.from_columns({"k": ke, "t": te, "r": je, "eigenvalue": eig.reshape(-1)}, "common_mode_eigen"),
        "common_mode_vector": contracts.from_columns({"k": ke, "t": te, "i": je, "loading": vec.reshape(-1)}, "common_mode_vector"),
    }
    check(built, frames, cfg)
    info = {
        "window": w, "series": N, "months_with_a_full_window": max(P - w + 1, 0),
        "absorption": {"top_fraction": cfg["common_mode.absorption_top_fraction"], "top_count": n_top},
        "band": {"quantile": q, "method": "numpy.quantile, linear", "role": "the test"},
        "mp_edge": {"value": edge, "role": "reference only; it assumes rows with no autocorrelation"},
        "surrogates": {"purpose": PURPOSE, "unit": "(i,): every row its own circular shift per draw", "n_draws": B,
                       "scope": cfg["surrogates.scope"], "offsets_per_row": max(surrogates.n_distinct(cfg, P), 0),
                       "smallest_p_value": 1.0 / (1 + B)},
        "p_value": "(1 + #{surrogate lambda1 >= lambda1}) / (1 + n_surrogates), one-sided; raw, per (k, t)",
        "turnover": "angle between the sign-fixed leading vectors at t and t - 1, radians in [0, pi]",
        "undefined": {"fewer_than_two_series": N < 2, "no_full_window": P < w,
                      "months_with_a_flat_row": flat_months, "surrogate_draws_left_out_for_a_flat_row": draws_dropped},
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Acceptance: rdiag's Stage 3 common-mode invariants with k in every key; a failure carries the failing rows.

    lambda1 and the leading vector are checked against the correlation recomputed here another way
    (linalg.corr on each configuration's trailing windows), so they are tied to the grid on every build.
    """
    R, months = _field(frames)
    K, N, P = R.shape
    w, B = cfg["common_mode.window"], cfg["surrogates.n_common_mode"]
    mo, ei, ve = b["common_mode_month"], b["common_mode_eigen"], b["common_mode_vector"]
    problems, failing = [], []
    for name, frame, want in (("common_mode_month", mo, K * P), ("common_mode_eigen", ei, K * P * N), ("common_mode_vector", ve, K * P * N)):
        if len(frame) != want:
            problems.append(f"{name} has {len(frame)} rows, expected {want}")
    if problems:
        raise AcceptanceError("common_mode", "; ".join(problems))

    pos = lambda f: (f["k"].to_numpy(), np.searchsorted(months, f["t"].to_numpy()))
    def per_month(col):
        a = np.full((K, P), np.nan)
        a[pos(mo)] = mo[col].to_numpy()
        return a
    lam1, band, p, absorb, turn, edge = (per_month(c) for c in ("lambda1", "lambda1_q", "p_value", "absorption_ratio", "vector_turnover", "mp_edge"))
    n_sur = per_month("n_surrogates")
    E, V = np.full((K, P, N), np.nan), np.full((K, P, N), np.nan)
    E[(*pos(ei), ei["r"].to_numpy())] = ei["eigenvalue"].to_numpy()
    V[(*pos(ve), ve["i"].to_numpy())] = ve["loading"].to_numpy()

    # each configuration's own trailing windows, recomputed: where a value must exist, what lambda1 must be,
    # and how far the stored vector is from an eigenvector of it
    want_lam, off_axis = np.full((K, P), np.nan), np.zeros((K, P))
    if N >= 2 and P >= w:
        for k in range(K):
            C = linalg.corr(sliding_window_view(R[k], w, axis=1).transpose(1, 2, 0))   # (T, w, N) -> (T, N, N)
            ok = ~np.isnan(C).any(axis=(1, 2))
            want_lam[k, w - 1:][ok] = np.linalg.eigvalsh(C[ok])[:, -1]
            v = np.nan_to_num(V[k, w - 1:])
            off_axis[k, w - 1:] = np.abs(np.einsum("tij,tj->ti", np.nan_to_num(C), v) - np.nan_to_num(lam1[k, w - 1:])[:, None] * v).max(axis=1)
    exists = ~np.isnan(want_lam)
    before = np.broadcast_to(np.arange(P) < w - 1, (K, P))
    prev = np.zeros((K, P), dtype=bool)
    prev[:, 1:] = exists[:, :-1]
    n_top = top_count(N, cfg["common_mode.absorption_top_fraction"])
    with np.errstate(invalid="ignore"):
        steps = p * (1 + n_sur)
        month_rules = [
            (before & ~(np.isnan(lam1) & np.isnan(band) & np.isnan(p) & np.isnan(absorb) & np.isnan(turn)),
             "every per-month value is null before the first full window"),
            ((np.isnan(lam1) != ~exists) | (exists & ~(np.abs(lam1 - want_lam) <= EIG_TOL)),
             "lambda1 is the leading eigenvalue of the configuration's own trailing-window correlation, null exactly where none exists"),
            (exists & ~((lam1 >= 1 - EIG_TOL) & (lam1 <= N + EIG_TOL)), "1 <= lambda1 <= N"),
            ((n_sur < 0) | (n_sur > B) | (~exists & (n_sur != 0)), "0 <= n_surrogates <= surrogates.n_common_mode, 0 where lambda1 is null"),
            ((np.isnan(p) != (n_sur == 0)) | (np.isnan(band) != (n_sur == 0)), "lambda1_q and p_value are null exactly where no surrogate was counted"),
            (~np.isnan(p) & ~((p > 0) & (p <= 1) & (np.abs(steps - np.round(steps)) <= 1e-9) & (np.round(steps) >= 1)),
             "p_value is a count from 1 to 1 + n_surrogates over 1 + n_surrogates"),
            (~np.isnan(band) & ~((band >= 1 - EIG_TOL) & (band <= N + EIG_TOL)), "1 <= lambda1_q <= N"),
            (~(np.abs(edge - linalg.mp_edge(N, w)) <= 1e-12), "mp_edge equals (1 + sqrt(N / window))^2"),
            ((np.isnan(absorb) != ~exists) | (exists & ~(np.abs(absorb - E[:, :, :n_top].sum(axis=2) / N) <= 1e-12)),
             "absorption_ratio is the top ceil(N x fraction) eigenvalues over N"),
            ((np.isnan(turn) != ~(exists & prev)) | (exists & prev & ~(np.abs(turn - _turnover(V)) <= 1e-9))
             | (~np.isnan(turn) & ((turn < 0) | (turn > np.pi))),
             "vector_turnover is the angle in [0, pi] between the leading vectors at t and t - 1, null where either is"),
        ]
        eigen_rules = [
            ((np.isnan(E) != ~exists[..., None]) | (exists & ~(np.abs(E.sum(axis=2) - N) <= EIG_TOL))[..., None],
             "N eigenvalues per month, summing to N where defined"),
            (np.concatenate([np.zeros((K, P, 1), bool), np.diff(E, axis=2) > 0], axis=2), "eigenvalues descend with the rank r"),
            ((exists & (E[:, :, 0] != lam1))[..., None] & (np.arange(N) == 0), "the eigenvalue at r = 0 is lambda1"),
        ]
        vector_rules = [
            ((np.isnan(V) != ~exists[..., None]) | (exists & ~((np.abs((V * V).sum(axis=2) - 1) <= EIG_TOL) & (V.sum(axis=2) >= -linalg.SIGN_TOL)))[..., None],
             "the leading vector has unit length and a sum >= 0, null exactly where lambda1 is"),
            ((exists & ~(off_axis <= VEC_TOL))[..., None] & np.ones(N, bool), "the leading vector is an eigenvector of lambda1 (C v = lambda1 v)"),
        ]
    kk, pp = np.meshgrid(np.arange(K), np.arange(P), indexing="ij")
    for artifact, rules, col in (("common_mode_month", month_rules, None), ("common_mode_eigen", eigen_rules, "r"), ("common_mode_vector", vector_rules, "i")):
        for mask, rule in rules:
            if mask.any():
                problems.append(f"{artifact}: {rule} ({int(mask.sum())} rows)")
                if col is None:
                    keys = {"k": kk[mask], "t": months[pp[mask]]}
                else:
                    a, t, c = np.nonzero(mask)
                    keys = {"k": a, "t": months[t], col: c}
                failing.append(pd.DataFrame(keys).assign(artifact=artifact, problem=rule))
    if problems:
        raise AcceptanceError("common_mode", "; ".join(problems), pd.concat(failing, ignore_index=True))


def _turnover(V: np.ndarray) -> np.ndarray:
    """The angle between the stored vectors at t and t - 1, (K, P); NaN at the first month and where either is null."""
    out = np.full(V.shape[:2], np.nan)
    out[:, 1:] = linalg.angle(V[:, 1:], V[:, :-1])
    return out
