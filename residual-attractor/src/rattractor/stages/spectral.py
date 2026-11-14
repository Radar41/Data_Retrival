"""Stage spectral (track A2): rdiag's s2b spectral summary under input contract v2, one configuration's row at a time.

Reads the wavelet stage's tables. Every quantity below belongs to one (k, i) row; nothing meets another
configuration or another series. n_a(j) is the number of in-cone months at scale j, s_j the scale, dj = 1 /
voices_per_octave, level(k, i, j) = variance x P_ar1(period_j) the row's own AR(1) reference (Torrence and
Compo 1998, section 5), q = wavelet.significance.

    spectral_global      (k, i, j): gws = mean of power over the in-cone months (null when a scale has none);
                         dof = 2 sqrt(1 + (n_a / (gamma_decorrelation s_j))^2); threshold = level x chi2_dof(q) / dof;
                         above = gws > threshold; p_value = P(chi2_dof > dof x gws / level), the raw p-value of
                         the (k, i, j) test, in (0, 1]
    spectral_bands       (k, i, band): the maximal runs of scales with above = true that are at least
                         min_band_scales long, numbered from 0 by ascending period. j_center is the scale of
                         largest gws in the run. sap_threshold is the level of the band's scale-averaged power:
                         (dj variance / c_delta) x sum_j P_ar1(period_j) / s_j x chi2_nu(q) / nu,
                         nu = 2 n S_avg / S_mid x sqrt(1 + (n dj / dj0_decorrelation)^2), n scales in the band,
                         S_avg = 1 / sum_j (1 / s_j), S_mid = sqrt(s_lo s_hi)   (their eqs. 25 to 28)
    spectral_band_count  (k, i): how many bands the row has; zero is an answer, not a gap
    spectral_band_power  (k, i, band, t): sap = (dj / c_delta) x sum over the band's scales of power / s_j, for
                         every month; in_coi is true where every scale of the band is in the cone
    spectral_dominant    (k, i, t): the scale of largest power among the in-cone scales at t and its period;
                         null where no scale is in the cone

Bands come only from the threshold rule: there are no preset period ranges anywhere.

rdiag sources: s2_transforms/spectral_summary.py, schemas/20_stage2.yaml (s2b.*), params spectral_summary.
Departures and choices where rdiag is silent:
  - every configuration's row gets its own spectrum and its own bands; k joins every key (the archive rule).
  - p_value is stored with its keys. rdiag registers the (i, j) tests in a registry; here the later
    false-discovery stage reads this table.
  - band_count is a table (rdiag derives it in a view), and sap_threshold is a column of spectral_bands.
  - dj0_decorrelation (Torrence and Compo's delta-j0 = 0.6 for the Morlet) is a config key; rdiag cites
    their eq. 26 and leaves the factor implicit.
  - spectral_band_power carries in_coi, so the months near the ends stay flagged; spectral_dominant
    carries the scale index beside the period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .. import contracts
from . import AcceptanceError
from .wavelet import dense, keys, red_noise_level

TINY = np.finfo(np.float64).tiny  # p-values are reported in (0, 1]


def global_dof(n_a: np.ndarray, scales: np.ndarray, cfg: dict) -> np.ndarray:
    """Degrees of freedom of the time-averaged power at each scale (Torrence and Compo, eq. 23)."""
    return 2.0 * np.sqrt(1.0 + (n_a / (cfg["spectral_summary.gamma_decorrelation"] * scales)) ** 2)


def runs(above: np.ndarray, min_length: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(row, band, j_lo, j_hi) of every maximal run of True along the last axis of above[row, j] that is
    at least min_length long; band counts the kept runs of a row from 0, in ascending j."""
    pad = np.zeros((above.shape[0], 1), dtype=np.int8)
    d = np.diff(np.concatenate([pad, above.astype(np.int8), pad], axis=1), axis=1)
    row, lo = np.nonzero(d == 1)
    hi = np.nonzero(d == -1)[1] - 1
    keep = hi - lo + 1 >= min_length
    row, lo, hi = row[keep], lo[keep], hi[keep]
    first = np.r_[True, row[1:] != row[:-1]] if row.size else np.zeros(0, dtype=bool)
    start = np.maximum.accumulate(np.where(first, np.arange(row.size), 0)) if row.size else np.zeros(0, dtype=np.int64)
    return row, np.arange(row.size) - start, lo, hi


def scale_average(power: np.ndarray, scales: np.ndarray, lo: int, hi: int, cfg: dict) -> np.ndarray:
    """Scale-averaged power over the scales lo..hi of power[..., j, t] (Torrence and Compo, eq. 24)."""
    dj = 1.0 / cfg["wavelet.voices_per_octave"]
    return (dj / cfg["spectral_summary.c_delta"]) * (power[..., lo : hi + 1, :] / scales[lo : hi + 1, None]).sum(axis=-2)


def scale_average_threshold(level: np.ndarray, scales: np.ndarray, lo: int, hi: int, cfg: dict) -> np.ndarray:
    """The level a red-noise row's scale-averaged power over lo..hi exceeds with probability 1 - q; level[..., j]."""
    dj, n = 1.0 / cfg["wavelet.voices_per_octave"], hi - lo + 1
    s = scales[lo : hi + 1]
    s_avg, s_mid = 1.0 / (1.0 / s).sum(), np.sqrt(s[0] * s[-1])
    nu = 2.0 * n * s_avg / s_mid * np.sqrt(1.0 + (n * dj / cfg["spectral_summary.dj0_decorrelation"]) ** 2)
    return (dj / cfg["spectral_summary.c_delta"]) * (level[..., lo : hi + 1] / s).sum(axis=-1) * stats.chi2.ppf(cfg["wavelet.significance"], nu) / nu


def run(frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), months.size
    sc = wav["wavelet_scale"].sort_values("j")
    periods, scales = sc["period"].to_numpy(), sc["scale"].to_numpy()
    J = periods.size
    power = dense(wav["wavelet_cwt"], "power", (K, N, J, P), months)
    coi = dense(wav["wavelet_cwt"], "in_coi", (K, N, J, P), months)
    if not (coi == coi[0, 0]).all():
        raise AcceptanceError("spectral", "in_coi differs between rows; it must depend on the scale and the month only")
    coi = coi[0, 0] if K * N else np.zeros((J, P), dtype=bool)
    variance, ar1 = dense(wav["wavelet_series"], "variance", (K, N)), dense(wav["wavelet_series"], "ar1", (K, N))
    level = red_noise_level(variance, ar1, periods)                       # (K, N, J)
    q = cfg["wavelet.significance"]

    n_a = coi.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        gws = np.where(n_a > 0, (power * coi).sum(axis=-1) / n_a, np.nan)
    dof = global_dof(n_a, scales, cfg)
    threshold = level * stats.chi2.ppf(q, dof) / dof
    above = gws > threshold                                               # false where gws is null
    with np.errstate(invalid="ignore"):
        p_value = np.where(n_a > 0, np.clip(stats.chi2.sf(dof * gws / level, dof), TINY, 1.0), np.nan)

    row, band, lo, hi = runs(above.reshape(K * N, J), cfg["spectral_summary.min_band_scales"])
    kb, ib = row // N if N else row, row % N if N else row
    B = row.size
    center = np.array([l + int(np.argmax(gws[k, i, l : h + 1])) for k, i, l, h in zip(kb, ib, lo, hi)], dtype=np.int64)
    sap = np.array([scale_average(power[k, i], scales, l, h, cfg) for k, i, l, h in zip(kb, ib, lo, hi)]).reshape(B, P)
    sap_thr = np.array([scale_average_threshold(level[k, i], scales, l, h, cfg) for k, i, l, h in zip(kb, ib, lo, hi)], dtype=np.float64)
    count = np.bincount(row, minlength=K * N)

    in_cone = coi.any(axis=0)                                             # months with at least one scale in the cone
    j_dom = np.where(coi, power, -np.inf).argmax(axis=2) if J else np.zeros((K, N, P), dtype=np.int64)
    k3, i3, j3 = keys((K, N, J))
    k2, i2 = keys((K, N))
    kd, id_, td = keys((K, N, P))
    bb, tb = keys((B, P))
    dom_j = pd.array(np.where(in_cone[td], j_dom.reshape(-1), -1), dtype="Int16")
    dom_j[~in_cone[td]] = pd.NA
    built = {
        "spectral_global": contracts.from_columns({
            "k": k3, "i": i3, "j": j3, "gws": gws.reshape(-1), "dof": np.broadcast_to(dof, (K, N, J)).reshape(-1),
            "threshold": threshold.reshape(-1), "above": above.reshape(-1), "p_value": p_value.reshape(-1)}, "spectral_global"),
        "spectral_bands": contracts.from_columns({
            "k": kb, "i": ib, "band": band, "j_lo": lo, "j_hi": hi, "period_lo": periods[lo], "period_hi": periods[hi],
            "j_center": center, "sap_threshold": sap_thr}, "spectral_bands"),
        "spectral_band_count": contracts.from_columns({"k": k2, "i": i2, "band_count": count}, "spectral_band_count"),
        "spectral_band_power": contracts.from_columns({
            "k": kb[bb], "i": ib[bb], "band": band[bb], "t": months[tb], "sap": sap.reshape(-1), "in_coi": coi[hi[bb], tb]}, "spectral_band_power"),
        "spectral_dominant": contracts.from_columns({
            "k": kd, "i": id_, "t": months[td], "j": dom_j,
            "period": np.where(in_cone[td], periods[j_dom.reshape(-1)] if J else np.nan, np.nan)}, "spectral_dominant"),
    }
    check(built, frames, wav, cfg)
    info = {
        "band_rule": cfg["spectral_summary.band_rule"], "min_band_scales": cfg["spectral_summary.min_band_scales"],
        "significance": q, "global_spectrum": "mean power over the in-cone months; dof = 2 sqrt(1 + (n_a / (gamma s))^2)",
        "gamma_decorrelation": cfg["spectral_summary.gamma_decorrelation"], "c_delta": cfg["spectral_summary.c_delta"],
        "dj0_decorrelation": cfg["spectral_summary.dj0_decorrelation"],
        "bands": "per (k, i) row, from that row's own spectrum and its own AR(1) reference; no preset period ranges",
        "p_values": "spectral_global.p_value, one per (k, i, j), raw",
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Acceptance: rdiag's s2b invariants with k in the key; a failure carries the failing rows."""
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    gl, bd, bc, bp, dm = (b[x] for x in ("spectral_global", "spectral_bands", "spectral_band_count", "spectral_band_power", "spectral_dominant"))
    sc, cw = wav["wavelet_scale"], wav["wavelet_cwt"]
    J = len(sc)
    problems, rows = [], []
    for name, want in {"spectral_global": K * N * J, "spectral_band_count": K * N, "spectral_dominant": K * N * P, "spectral_band_power": len(bd) * P}.items():
        if len(b[name]) != want:
            problems.append(f"{name} has {len(b[name])} rows, expected {want}")
    n_a = cw.groupby("j")["in_coi"].sum().reindex(sc["j"]).to_numpy() // max(K * N, 1)       # in-cone months of each scale
    scale = sc.set_index("j")["scale"].reindex(gl["j"]).to_numpy()
    gws, thr, above, p = (gl[c].to_numpy() for c in ("gws", "threshold", "above", "p_value"))
    has = n_a[gl["j"].to_numpy()] > 0
    rules = [
        ("spectral_global", gl, np.isnan(gws) == has, "gws is null exactly where the scale has no in-cone month"),
        ("spectral_global", gl, above != (np.nan_to_num(gws, nan=-np.inf) > thr), "above equals gws > threshold"),
        ("spectral_global", gl, ~(np.abs(gl["dof"].to_numpy() - global_dof(n_a[gl["j"].to_numpy()], scale, cfg)) <= 1e-12 * gl["dof"].to_numpy()) | ~(thr > 0),
         "dof equals 2 sqrt(1 + (n_a / (gamma s))^2) and the threshold is positive"),
        ("spectral_global", gl, (np.isnan(p) == has) | (has & ~((p > 0) & (p <= 1))), "p_value in (0, 1], null exactly where gws is null"),
    ]
    # bands_from_threshold: the maximal runs of above, found here by run ids instead of differences
    g = gl.sort_values(["k", "i", "j"])
    run_id = (g["above"] != g.groupby(["k", "i"])["above"].shift()).cumsum()
    r = g[g["above"]].groupby(["k", "i", run_id[g["above"]]])["j"].agg(j_lo="min", j_hi="max", n="size").reset_index()
    r = r[r["n"] >= cfg["spectral_summary.min_band_scales"]]
    r = r.assign(band=r.groupby(["k", "i"]).cumcount())[["k", "i", "band", "j_lo", "j_hi"]]
    m = bd[["k", "i", "band", "j_lo", "j_hi"]].astype(np.int64).merge(r.astype(np.int64), how="outer", on=["k", "i", "band", "j_lo", "j_hi"], indicator=True)
    wrong = m[m["_merge"] != "both"]
    if len(wrong):
        problems.append(f"spectral_bands: bands are the maximal runs of above that are at least min_band_scales long, numbered by ascending period ({len(wrong)} rows)")
        rows.append(wrong[["k", "i", "band"]].assign(artifact="spectral_bands", problem="bands are the maximal runs of above that are at least min_band_scales long, numbered by ascending period"))
    period = sc.set_index("j")["period"]
    inside = bd.merge(gl[["k", "i", "j", "gws"]], on=["k", "i"])
    inside = inside[(inside["j"] >= inside["j_lo"]) & (inside["j"] <= inside["j_hi"])]
    best = inside.loc[inside.groupby(["k", "i", "band"])["gws"].idxmax(), ["k", "i", "band", "j"]] if len(inside) else inside[["k", "i", "band", "j"]]
    centre = bd.merge(best, on=["k", "i", "band"], how="left")["j"].to_numpy()
    counted = bc.merge(bd.groupby(["k", "i"]).size().rename("n").reset_index(), on=["k", "i"], how="left")["n"].fillna(0).to_numpy()
    months_per_band = bd.merge(bp.groupby(["k", "i", "band"]).size().rename("n").reset_index(), on=["k", "i", "band"], how="left")["n"].fillna(0).to_numpy()
    top = bp.merge(bd[["k", "i", "band", "j_hi"]], on=["k", "i", "band"], how="left").rename(columns={"j_hi": "j"})
    top_coi = top.merge(cw[["k", "i", "j", "t", "in_coi"]], on=["k", "i", "j", "t"], how="left", suffixes=("", "_cwt"))["in_coi_cwt"].to_numpy()
    cone_months = set(cw.loc[cw["in_coi"], "t"].unique())
    in_cone = dm["t"].isin(cone_months).to_numpy()
    dj, dper = dm["j"].to_numpy(dtype=np.float64, na_value=np.nan), dm["period"].to_numpy()
    rules += [
        ("spectral_bands", bd, ~((bd["j_center"].to_numpy() == centre) & (bd["period_lo"].to_numpy() == period.reindex(bd["j_lo"]).to_numpy())
                                 & (bd["period_hi"].to_numpy() == period.reindex(bd["j_hi"]).to_numpy())), "j_center is the scale of largest gws in the band, and the periods are those of j_lo and j_hi"),
        ("spectral_bands", bd, ~(bd["sap_threshold"].to_numpy() > 0), "sap_threshold is positive"),
        ("spectral_band_count", bc, bc["band_count"].to_numpy() != counted, "band_count equals the row's number of bands"),
        ("spectral_bands", bd, months_per_band != P, "every band has a scale-averaged power for every month"),
        ("spectral_band_power", bp, ~(bp["sap"].to_numpy() >= 0) | (bp["in_coi"].to_numpy() != top_coi), "sap is non-negative and in_coi is the cone at the band's longest scale"),
        ("spectral_dominant", dm, (np.isnan(dper) == in_cone) | (np.isnan(dj) == in_cone) | (in_cone & (dper != period.reindex(np.nan_to_num(dj, nan=0).astype(np.int64)).to_numpy())),
         "period is null exactly where no scale is in the cone, and is the period of j elsewhere"),
    ]
    for artifact, frame, mask, rule in rules:
        if mask.any():
            problems.append(f"{artifact}: {rule} ({int(mask.sum())} rows)")
            cols = [c for c in ("k", "i", "band", "j", "t") if c in frame.columns]
            rows.append(frame.loc[mask, cols].assign(artifact=artifact, problem=rule))
    if problems:
        raise AcceptanceError("spectral", "; ".join(problems), pd.concat(rows, ignore_index=True) if rows else None)
