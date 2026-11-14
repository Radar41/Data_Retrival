"""Stage coherence (track A3): rdiag's s3.coherence under input contract v2, every pair of series inside one configuration.

Reads the grid, the wavelet stage's scales and transform, and the spectral stage's bands. A pair (i_a, i_b),
i_a < i_b, is two rows of the same configuration k; no value here is computed from two configurations.
With W_a, W_b the transforms of the two centred rows, s_j the scale and S the smoothing of common.wavelets
(Gaussian in time with sd s_j, boxcar of coherence.scale_smoothing_width octaves in scale):

    cross = S(W_a conj(W_b) / s)          r2 = |cross|^2 / (S(|W_a|^2 / s) x S(|W_b|^2 / s)),  in [0, 1]
    phase = arg cross, in (-pi, pi]       positive: i_a leads i_b. Taking the two rows the other way round leaves
                                          r2 as it is and negates the phase, bit for bit.
    lag in months = phase x period / (2 pi), positive: i_a leads i_b. A phase gives the lag only modulo the
                    period: a lag of L months at period p is reported inside (-p / 2, p / 2].

Null (rdiag common/surrogates): the higher-indexed row i_b is replaced by its circular shifts, x_b[(t + o) mod P],
and everything is recomputed, transform included. Offsets come from common.surrogates. When
surrogates.n_coherence is at least the number of offsets that exist (P - 2 x min_offset + 1; 75 on spec 0)
every offset is used once: the whole null distribution, exact, and cheaper than drawing. Otherwise
n_coherence offsets are drawn by surrogates.offsets(cfg, "coherence", P, n, k, i_a, i_b). With n surrogates:

    r2_q        the r-th largest surrogate r2 at the cell, r = floor((1 - coherence.quantile)(n + 1)). Were the
                n + 1 alignments (the observed one and the n shifts) exchangeable, an unrelated cell would exceed
                it with probability r / (n + 1) <= 1 - quantile (3 / 76 = 3.9% at n = 75). With r = 0 no level is
                that strict; r2_q is 1 and no cell is significant.
    significant in_coi and r2 > r2_q, where values within TIE = 1e-12 are ties: a shift that maps a row onto itself
                is a surrogate as coherent as the observed alignment, even when rounding makes it a hair smaller

    coherence_cells   (k, i_a, i_b, j, t): r2, phase, r2_q, in_coi, significant. Every cell is kept.
    coherence_scope   (k, i_a, i_b, band_a, band_b): one row for the scope "all" (band_a = band_b = -1, every
                      scale) and one for every overlap of a band of row (k, i_a) with a band of row (k, i_b)
                      (scales max(j_lo) .. min(j_hi)). Over the scope's in-cone cells: n_cells, n_significant,
                      r2_mean, and p_value = (1 + #{surrogates whose r2_mean >= the observed}) / (1 + n), the
                      raw p-value of the (k, pair, scope) test. Over its significant cells: phase (their circular
                      mean), period (their geometric mean period) and lag_months = phase x period / (2 pi).

What the null does on unrelated rows (measured on independent AR(1) rows, 14 series, P = 98; tests pin both cases):
the alignments are exchangeable only when every nonzero shift is a surrogate (min offset 1); then 4.2% of in-cone
cells are significant against the rule's 4 / 98 = 4.1%, and the smallest p-value turns up for 1.1% of pairs against
1 / 98. With rdiag's min offset of 12 the observed alignment has no neighbour in the null while the shifts
neighbour each other, and the same rows give 5% at the shortest periods, 12 to 15% at the longest, 7.7% over all
in-cone cells, and the smallest p-value (1 / 76) for 7% of pairs. Nothing here corrects for that.

rdiag sources: s3_cooccurrence/coherence.py, common/surrogates.py, schemas/30_stage3.yaml (s3.coherence),
params coherence and surrogates.n_coherence.
Departures and choices where rdiag is silent:
  - every configuration's pairs are analysed; k joins every key (the archive rule).
  - rdiag registers a test per (pair, band) but names no statistic and does not let coherence read the bands.
    Here the stage reads spectral_bands, the statistic is the scope's mean coherence over its in-cone cells,
    and the p-value is stored with its keys. A band belongs to one row, so a pair's band scopes are overlaps.
  - r2_q is an order statistic, not an interpolated quantile: under exchangeability numpy's 0.95 quantile of
    75 values is exceeded 6.2% of the time, the order statistic 3.9%.
  - all offsets are enumerated when the requested draws would cover them anyway (see above). p-values then
    move in steps of 1 / (n + 1): the smallest on spec 0 is 1 / 76 = 0.013.
  - in_coi is repeated per cell so adjacency needs this table alone; the phase is defined at every cell,
    and the lag in months is stored per scope, where one period can be named.
  - rdiag's recipe table s3.surrogate_index is not written (common.surrogates explains why).
  - a deterministic cycle shared by two rows stays coherent under every shift, so it is not significant
    here: the null keeps each row's own spectrum, and a common period is a property of the rows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from ..common import surrogates, wavelets
from . import AcceptanceError
from .wavelet import dense, field, keys, moments, polar

R2_SLACK = 1e-9   # r2 is in [0, 1] by Cauchy-Schwarz; a larger excess than this is not rounding and stops the build
ALL = -1          # band_a = band_b = -1 marks the scope over every scale
TIE = 1e-12       # values of r2 this close are ties: a surrogate the same as the observed field up to rounding is not beaten


def pairs(N: int) -> tuple[np.ndarray, np.ndarray]:
    """(i_a, i_b) of every pair with i_a < i_b, in lexicographic order."""
    ia, ib = np.triu_indices(N, 1)
    return ia.astype(np.int64), ib.astype(np.int64)


def pair_position(ia: np.ndarray, ib: np.ndarray, N: int) -> np.ndarray:
    """The position of pair (i_a, i_b) in pairs(N)."""
    ia, ib = np.asarray(ia, dtype=np.int64), np.asarray(ib, dtype=np.int64)
    return ia * N - ia * (ia + 1) // 2 + (ib - ia - 1)


def rank_level(n: int, q: float) -> int:
    """r = floor((1 - q)(n + 1)): an unrelated observation is among the r largest of n + 1 with probability r / (n + 1) <= 1 - q."""
    return int(np.floor((1.0 - q) * (n + 1) + 1e-9))


def cell_level(surr: np.ndarray, q: float) -> np.ndarray:
    """r2_q at every cell from surr[draw, ...]: the r-th largest value over the draws; 1 where r = 0."""
    n = surr.shape[0]
    r = rank_level(n, q)
    return np.partition(surr, n - r, axis=0)[n - r] if r >= 1 else np.ones(surr.shape[1:])


def plan(cfg: dict, P: int) -> dict:
    """How the null of one pair is built for rows of P months."""
    distinct = surrogates.n_distinct(cfg, P)
    if distinct < 1:
        raise AcceptanceError("coherence", f"no circular shift exists: P = {P} is shorter than twice surrogates.circular_shift_min_offset = {cfg['surrogates.circular_shift_min_offset']}")
    enumerated = cfg["surrogates.n_coherence"] >= distinct
    n = distinct if enumerated else cfg["surrogates.n_coherence"]
    return {"mode": "enumerated" if enumerated else "drawn", "n": int(n), "requested": cfg["surrogates.n_coherence"], "distinct_offsets": int(distinct),
            "rank": rank_level(n, cfg["coherence.quantile"]), "smallest_p_value": 1.0 / (n + 1)}


def pair_offsets(cfg: dict, P: int, k: int, i_a: int, i_b: int) -> np.ndarray:
    """The offsets row i_b is shifted by against row i_a in configuration k: every one that exists, or the pair's own draws."""
    pl = plan(cfg, P)
    if pl["mode"] == "enumerated":
        m = cfg["surrogates.circular_shift_min_offset"]
        return np.arange(m, m + pl["n"], dtype=np.int64)
    return surrogates.offsets(cfg, "coherence", P, pl["n"], k, i_a, i_b)


def scopes(bands_a: list, bands_b: list, J: int) -> list[tuple[int, int, int, int]]:
    """(band_a, band_b, j_lo, j_hi): every scale first, then each overlap of a band (band, j_lo, j_hi) of the two rows. None without a scale."""
    if not J:
        return []
    out = [(ALL, ALL, 0, J - 1)]
    for ba, lo_a, hi_a in bands_a:
        for bb, lo_b, hi_b in bands_b:
            lo, hi = max(lo_a, lo_b), min(hi_a, hi_b)
            if lo <= hi:
                out.append((ba, bb, lo, hi))
    return out


def exceedance_p(stat: float, null: np.ndarray) -> float:
    """(1 + #{null values >= stat, ties within TIE included}) / (1 + n): the surrogate p-value of one statistic."""
    return (1 + int((np.asarray(null) >= stat - TIE).sum())) / (1 + np.asarray(null).size)


def cross_spectrum(wa: np.ndarray, wb: np.ndarray) -> np.ndarray:
    """W_a conj(W_b). Each part comes from its own two products, so the pair taken the other way round gives the exact conjugate."""
    out = np.empty(np.broadcast_shapes(wa.shape, wb.shape), dtype=np.complex128)
    out.real = wa.real * wb.real + wa.imag * wb.imag
    out.imag = wa.imag * wb.real - wa.real * wb.imag
    return out


def _ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """num / den, 0 where den is 0, checked against [0, 1] and clipped to it."""
    out = np.zeros_like(num)
    np.divide(num, den, out=out, where=den > 0)
    if out.size and out.max() > 1.0 + R2_SLACK:
        raise AcceptanceError("coherence", f"r2 reaches {out.max()}, beyond rounding above 1")
    return np.clip(out, 0.0, 1.0, out=out)


def run(frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], spec: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    R, months = field(frames)
    K, N, P = R.shape
    sc = wav["wavelet_scale"].sort_values("j")
    periods, scales = sc["period"].to_numpy(), sc["scale"].to_numpy()
    J = periods.size
    coi = wavelets.coi_mask(scales, P)
    n_a, logp = coi.sum(axis=1), np.log(periods)
    ia, ib = pairs(N)
    NP = ia.size
    q = cfg["coherence.quantile"]
    bands: dict[tuple[int, int], list] = {}
    for k, i, band, lo, hi in spec["spectral_bands"].sort_values(["k", "i", "band"])[["k", "i", "band", "j_lo", "j_hi"]].itertuples(index=False):
        bands.setdefault((int(k), int(i)), []).append((int(band), int(lo), int(hi)))
    r2 = np.zeros((K, NP, J, P))
    phase, r2_q, sig = np.zeros((K, NP, J, P)), np.ones((K, NP, J, P)), np.zeros((K, NP, J, P), dtype=bool)
    rows = []
    pl = plan(cfg, P) if NP else None
    if NP:
        kernels = wavelets.smoother(scales, P, cfg)
        inv_s = 1.0 / scales[:, None]
        xc = moments(R)[0]
        W = wavelets.transform(xc, scales, cfg)
        if not (np.array_equal(W.real, dense(wav["wavelet_cwt"], "w_re", (K, N, J, P), months)) and np.array_equal(W.imag, dense(wav["wavelet_cwt"], "w_im", (K, N, J, P), months))):
            raise AcceptanceError("coherence", "the transform of the grid rows is not the one in wavelet_cwt")
        n = pl["n"]
        for k in range(K):
            # every observed field is smoothed in a call of its own, so no observed value depends on the surrogate settings
            auto = [wavelets.smooth((W[k, i].real ** 2 + W[k, i].imag ** 2) * inv_s, kernels) for i in range(N)]
            for b in range(1, N):
                side = None
                for a in range(b):
                    offs = pair_offsets(cfg, P, k, a, b)
                    uniq, inv = np.unique(offs, return_inverse=True)
                    if side is None or pl["mode"] == "drawn":
                        Ws = wavelets.transform(np.stack([surrogates.shift(xc[k, b], o) for o in uniq]), scales, cfg)
                        side = (Ws, wavelets.smooth((Ws.real ** 2 + Ws.imag ** 2) * inv_s, kernels))
                    Ws, auto_s = side
                    cross = wavelets.smooth(cross_spectrum(W[k, a], W[k, b]) * inv_s, kernels)
                    cross_s = wavelets.smooth(cross_spectrum(W[k, a][None], Ws) * inv_s, kernels)
                    obs = _ratio(cross.real ** 2 + cross.imag ** 2, auto[a] * auto[b])
                    null = _ratio(cross_s.real ** 2 + cross_s.imag ** 2, auto[a][None] * auto_s)[inv]      # one field per draw
                    level = cell_level(null, q)
                    ph = polar(cross.real, cross.imag)
                    sg = coi & (obs > level + TIE)
                    p = int(pair_position(a, b, N))
                    r2[k, p], phase[k, p], r2_q[k, p], sig[k, p] = obs, ph, level, sg
                    in_obs, in_null = (obs * coi).sum(axis=1), (null * coi).sum(axis=2)                     # per scale, in-cone months only
                    sig_j, z_j = sg.sum(axis=1), (np.exp(1j * ph) * sg).sum(axis=1)
                    for band_a, band_b, lo, hi in scopes(bands.get((k, a), []), bands.get((k, b), []), J):
                        nc, ns = int(n_a[lo : hi + 1].sum()), int(sig_j[lo : hi + 1].sum())
                        stat = pv = mean_phase = period = lag = np.nan
                        if nc:
                            stat = in_obs[lo : hi + 1].sum() / nc
                            pv = exceedance_p(stat, in_null[:, lo : hi + 1].sum(axis=1) / nc)
                        if ns:
                            z = z_j[lo : hi + 1].sum()
                            mean_phase = float(polar(z.real, z.imag))
                            period = float(np.exp((sig_j[lo : hi + 1] * logp[lo : hi + 1]).sum() / ns))
                            lag = mean_phase * period / (2.0 * np.pi)
                        rows.append((k, a, b, band_a, band_b, lo, hi, nc, ns, stat, n, pv, mean_phase, period, lag))
    kc, pc, jc, tc = keys((K, NP, J, P))
    cols = list(zip(*sorted(rows))) if rows else [[] for _ in range(15)]
    names = ("k", "i_a", "i_b", "band_a", "band_b", "j_lo", "j_hi", "n_cells", "n_significant", "r2_mean", "n_surrogates", "p_value", "phase", "period", "lag_months")
    built = {
        "coherence_cells": contracts.from_columns({
            "k": kc, "i_a": ia[pc], "i_b": ib[pc], "j": jc, "t": months[tc], "r2": r2.reshape(-1), "phase": phase.reshape(-1),
            "r2_q": r2_q.reshape(-1), "in_coi": np.broadcast_to(coi, (K, NP, J, P)).reshape(-1), "significant": sig.reshape(-1)}, "coherence_cells"),
        "coherence_scope": contracts.from_columns({name: np.asarray(col) for name, col in zip(names, cols)}, "coherence_scope"),
    }
    check(built, frames, wav, spec, cfg)
    info = {
        "pairs_per_configuration": int(NP), "pairs": "i_a < i_b, both rows from the same configuration",
        "phase": "arg of the smoothed cross-spectrum W_a conj(W_b); positive: i_a leads i_b",
        "lag_months": "phase x period / (2 pi); positive: i_a leads i_b; defined modulo the period",
        "smoothing": {"time": cfg["coherence.time_smoothing"], "scale_width_octaves": cfg["coherence.scale_smoothing_width"],
                      "scale_weights": [float(x) for x in wavelets.scale_weights(cfg)]},
        "surrogates": None if pl is None else {
            "purpose": "coherence", "shifted_row": "i_b, the higher-indexed row of the pair", "scope": cfg["surrogates.scope"],
            "min_offset": cfg["surrogates.circular_shift_min_offset"], **pl,
            "cell_rule": f"significant = in_coi and r2 > the {pl['rank']}-th largest of {pl['n']} surrogate values (level {pl['rank']}/{pl['n'] + 1})"},
        "quantile": q, "p_values": "coherence_scope.p_value, one per (k, i_a, i_b, scope), raw",
        "cells": {"all": int(sig.size), "in_cone": int(K * NP * n_a.sum()), "significant": int(sig.sum())},
        "scopes": "all scales (band_a = band_b = -1) and every overlap of the two rows' own bands",
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], spec: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Acceptance: rdiag's s3.coherence invariants with k in the key; a failure carries the failing rows."""
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), months.size
    ce, sp = b["coherence_cells"], b["coherence_scope"]
    sc = wav["wavelet_scale"].sort_values("j")
    scales, periods = sc["scale"].to_numpy(), sc["period"].to_numpy()
    J, NP = len(sc), N * (N - 1) // 2
    problems, out = [], []
    if len(ce) != K * NP * J * P:
        problems.append(f"coherence_cells has {len(ce)} rows, expected {K * NP * J * P}")
    if not NP:
        if len(sp):
            problems.append(f"coherence_scope has {len(sp)} rows for a field with no pair")
        if problems:
            raise AcceptanceError("coherence", "; ".join(problems))
        return
    pl = plan(cfg, P)
    coi = wavelets.coi_mask(scales, P)
    n_a = coi.sum(axis=1)
    ka, a, bb, j = (ce[c].to_numpy() for c in ("k", "i_a", "i_b", "j"))
    tidx = np.searchsorted(months, ce["t"].to_numpy())
    r2, r2q, ph, inc, sg = (ce[c].to_numpy() for c in ("r2", "r2_q", "phase", "in_coi", "significant"))
    rules = [
        ("coherence_cells", ce, ~(a < bb), "pairs have i_a < i_b"),
        ("coherence_cells", ce, ~((r2 >= 0) & (r2 <= 1) & (r2q >= 0) & (r2q <= 1) & (ph > -np.pi) & (ph <= np.pi)), "r2 and r2_q lie in [0, 1] and phase in (-pi, pi]"),
        ("coherence_cells", ce, inc != coi[j, np.minimum(tidx, P - 1)], "in_coi is the wavelet stage's cone"),
        ("coherence_cells", ce, sg != (inc & (r2 > r2q + TIE)), "significant equals in_coi and r2 > r2_q"),
    ]
    # the scopes every pair must have: all scales, and each overlap of the two rows' bands
    bd = spec["spectral_bands"][["k", "i", "band", "j_lo", "j_hi"]].astype(np.int64)
    ov = bd.rename(columns={"i": "i_a", "band": "band_a", "j_lo": "lo_a", "j_hi": "hi_a"}).merge(
        bd.rename(columns={"i": "i_b", "band": "band_b", "j_lo": "lo_b", "j_hi": "hi_b"}), on="k")
    ov = ov[ov["i_a"] < ov["i_b"]].assign(j_lo=lambda d: np.maximum(d["lo_a"], d["lo_b"]), j_hi=lambda d: np.minimum(d["hi_a"], d["hi_b"]))
    ov = ov[ov["j_lo"] <= ov["j_hi"]][["k", "i_a", "i_b", "band_a", "band_b", "j_lo", "j_hi"]]
    ia, ib = np.triu_indices(N, 1)
    every = pd.DataFrame({"k": np.repeat(np.arange(K), NP), "i_a": np.tile(ia, K), "i_b": np.tile(ib, K), "band_a": ALL, "band_b": ALL, "j_lo": 0, "j_hi": J - 1})
    every = every if J else every.iloc[:0]
    want = pd.concat([every, ov], ignore_index=True).astype(np.int64)
    m = sp[["k", "i_a", "i_b", "band_a", "band_b", "j_lo", "j_hi"]].astype(np.int64).merge(want, how="outer", indicator=True)
    wrong = m[m["_merge"] != "both"]
    rule = "the scopes of a pair are all scales and every overlap of its two rows' bands"
    if len(wrong):
        problems.append(f"coherence_scope: {rule} ({len(wrong)} rows)")
        out.append(wrong[["k", "i_a", "i_b", "band_a", "band_b"]].assign(artifact="coherence_scope", problem=rule))
    if len(ce) == K * NP * J * P and not any(mask.any() for _, _, mask, _ in rules[:1]):
        # what each scope row says about its cells, recomputed from the cells
        pos = (ka, pair_position(a, bb, N), j, tidx)
        cube_r2, cube_sig = np.zeros((K, NP, J, P)), np.zeros((K, NP, J, P), dtype=bool)
        cube_r2[pos], cube_sig[pos] = r2, sg
        zero = np.zeros((K, NP, 1))
        cum_r2 = np.concatenate([zero, np.cumsum((cube_r2 * coi).sum(axis=-1), axis=2)], axis=2)
        cum_sig = np.concatenate([zero, np.cumsum(cube_sig.sum(axis=-1), axis=2)], axis=2)
        cum_n = np.concatenate([[0], np.cumsum(n_a)])
        sk, spp = sp["k"].to_numpy(), pair_position(sp["i_a"].to_numpy(), sp["i_b"].to_numpy(), N)
        lo, hi = sp["j_lo"].to_numpy().astype(np.int64), sp["j_hi"].to_numpy().astype(np.int64)
        ok_range = (lo >= 0) & (hi < J) & (lo <= hi) & (sk >= 0) & (sk < K) & (spp >= 0) & (spp < NP)
        lo_, hi_, sk_, sp_ = (np.where(ok_range, x, 0) for x in (lo, hi, sk, spp))
        nc = cum_n[hi_ + 1] - cum_n[lo_]
        ns = cum_sig[sk_, sp_, hi_ + 1] - cum_sig[sk_, sp_, lo_]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = (cum_r2[sk_, sp_, hi_ + 1] - cum_r2[sk_, sp_, lo_]) / nc
        got_mean, pv, nsur = sp["r2_mean"].to_numpy(), sp["p_value"].to_numpy(), sp["n_surrogates"].to_numpy()
        phs, per, lag = sp["phase"].to_numpy(), sp["period"].to_numpy(), sp["lag_months"].to_numpy()
        steps = pv * (nsur + 1)
        has, any_sig = sp["n_cells"].to_numpy() > 0, sp["n_significant"].to_numpy() > 0
        rules += [
            ("coherence_scope", sp, ~ok_range | (sp["n_cells"].to_numpy() != nc) | (sp["n_significant"].to_numpy() != ns), "n_cells and n_significant count the scope's in-cone and significant cells"),
            ("coherence_scope", sp, (np.isnan(got_mean) == has) | (has & ~(np.abs(got_mean - mean) <= 1e-9)), "r2_mean is the mean r2 over the scope's in-cone cells, null where it has none"),
            ("coherence_scope", sp, (nsur != pl["n"]) | (np.isnan(pv) == has) | (has & ~((steps >= 1 - 1e-9) & (steps <= nsur + 1 + 1e-9) & (np.abs(steps - np.round(steps)) <= 1e-9))),
             "p_value is (1 + a count) / (1 + n_surrogates), in (0, 1], null where the scope has no in-cone cell"),
            ("coherence_scope", sp, (np.isnan(phs) == any_sig) | (np.isnan(per) == any_sig) | (np.isnan(lag) == any_sig)
             | (any_sig & ~((phs > -np.pi) & (phs <= np.pi) & (np.abs(lag - phs * per / (2 * np.pi)) <= 1e-9 * np.maximum(1.0, np.abs(lag))) & (per >= periods[lo_] * (1 - 1e-12)) & (per <= periods[hi_] * (1 + 1e-12)))),
             "phase, period and lag_months exist exactly where the scope has significant cells, and lag_months = phase x period / (2 pi)"),
        ]
    for artifact, frame, mask, rule in rules:
        if mask.any():
            problems.append(f"{artifact}: {rule} ({int(mask.sum())} rows)")
            cols = [c for c in ("k", "i_a", "i_b", "band_a", "band_b", "j", "t") if c in frame.columns]
            out.append(frame.loc[mask, cols].assign(artifact=artifact, problem=rule))
    if problems:
        raise AcceptanceError("coherence", "; ".join(problems), pd.concat(out, ignore_index=True) if out else None)
