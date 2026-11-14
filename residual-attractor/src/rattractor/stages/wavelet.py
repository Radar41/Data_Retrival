"""Stage wavelet (track A1): rdiag's s2a.cwt under input contract v2, the Morlet transform of every configuration's own row.

Reads the grid (stage 9). Each analysis runs on one row x = resid[k, i, :] alone; nothing meets another
configuration or another series here. Writes, with k in every key:

    wavelet_scale      j -> period and scale. The grid depends on P and the config only, so it has no k
                       (a dimension table, as grid_month is).
    wavelet_series     (k, i): the row's mean, variance (about the mean, divisor P) and lag-1 autocorrelation
                       ar1 = sum_t xc[t] xc[t + 1] / sum_t xc[t]^2, xc = x - mean
    wavelet_red_noise  (k, i, j): threshold = variance x P_ar1(period_j) x chi2_2(wavelet.significance) / 2, the
                       pointwise level of an AR(1) row with the same variance and ar1 (Torrence and Compo, eq. 18)
    wavelet_cwt        (k, i, j, t): W = w_re + i w_im of the centred row (common.wavelets.transform),
                       power = w_re^2 + w_im^2, amplitude = sqrt(power), phase = arg W in (-pi, pi],
                       in_coi, and significant = in_coi and power > threshold

in_coi follows rdiag's naming: true where the cell is at least sqrt(2) x scale months from both ends of the
row. Cells where it is false are kept and flagged, never dropped or zeroed, and never counted as significant.

rdiag sources: s2_transforms/cwt.py, common/wavelets.py, schemas/20_stage2.yaml (s2a.cwt), params wavelet.
Departures and choices where rdiag is silent:
  - every configuration's row is transformed, not one fused row; k joins every key (the archive rule).
  - the row is centred on its own mean before the transform, as Torrence and Compo do. With zero padding an
    uncentred row puts the step from its mean to zero into every scale at both ends.
  - variance uses the divisor P, the same sums ar1 uses.
  - unit energy is exact on the discrete grid, so white noise has mean power 1 x variance at every scale,
    the Nyquist scales included (see common.wavelets).
  - amplitude, phase, in_coi and significant are stored per cell beside rdiag's W_re, W_im and power; rdiag
    keeps in_coi in its own table and leaves the comparison with the threshold to the reader.
  - a constant row has no transform to test (variance 0); rdiag's schema refuses it and so does the check here.
  - rdiag's s2a.complex is the cell complex of the holonomy stage, built from adjacency edges; it is not
    written here. The complex coefficients are (w_re, w_im), with amplitude and phase beside them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .. import contracts
from ..common import wavelets
from . import AcceptanceError

RTOL = 1e-12  # identities recomputed in the check from the stored columns


def field(frames: dict[str, pd.DataFrame]) -> tuple[np.ndarray, np.ndarray]:
    """(resid[k, i, t], the months in order) from the grid frames; every cell must be there."""
    r, months = frames["grid_resid"], np.sort(frames["grid_month"]["t"].to_numpy())
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), months.size
    R = np.full((K, N, P), np.nan)
    R[r["k"].to_numpy(), r["i"].to_numpy(), np.searchsorted(months, r["t"].to_numpy())] = r["resid"].to_numpy()
    if not np.isfinite(R).all():
        raise AcceptanceError("wavelet", "the grid is not a dense finite field")
    return R, months


def keys(shape: tuple[int, ...]) -> list[np.ndarray]:
    """One flat index column per axis of a dense array of this shape, in C order."""
    return [np.broadcast_to(np.arange(n).reshape([-1 if a == ax else 1 for a in range(len(shape))]), shape).reshape(-1)
            for ax, n in enumerate(shape)]


def dense(frame: pd.DataFrame, column: str, shape: tuple[int, ...], months: np.ndarray | None = None) -> np.ndarray:
    """One column of a long table as an array over its integer key columns (those among k, i, j, in that order)
    and, when months are given, t. Every cell of the shape must have exactly one row."""
    idx = [frame[c].to_numpy() for c in ("k", "i", "j") if c in frame.columns]
    if months is not None:
        idx.append(np.searchsorted(months, frame["t"].to_numpy()))
    if len(frame) != int(np.prod(shape)) or len(idx) != len(shape):
        raise AcceptanceError("wavelet", f"a table of {len(frame)} rows is not a dense field of shape {shape}")
    seen = np.zeros(shape, dtype=bool)
    seen[tuple(idx)] = True
    if not seen.all():
        raise AcceptanceError("wavelet", f"a table of {len(frame)} rows does not cover every cell of shape {shape}")
    out = np.empty(shape, dtype=frame[column].to_numpy().dtype)
    out[tuple(idx)] = frame[column].to_numpy()
    return out


def moments(R: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(centred rows, mean, variance, ar1) along the last axis; ar1 is NaN where the row is constant."""
    mean = R.mean(axis=-1)
    xc = R - mean[..., None]
    ss = (xc * xc).sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ar1 = (xc[..., 1:] * xc[..., :-1]).sum(axis=-1) / ss
    return xc, mean, ss / R.shape[-1], ar1


def red_noise_level(variance: np.ndarray, ar1: np.ndarray, periods: np.ndarray) -> np.ndarray:
    """variance x P_ar1(period): the expected power of the AR(1) reference at every scale, [..., j]."""
    return variance[..., None] * wavelets.ar1_spectrum(ar1[..., None], periods)


def polar(w_re: np.ndarray, w_im: np.ndarray) -> np.ndarray:
    """arg(w_re + i w_im) in (-pi, pi]."""
    ph = np.arctan2(w_im, w_re)
    return np.where(ph <= -np.pi, np.pi, ph)


def run(frames: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    R, months = field(frames)
    K, N, P = R.shape
    periods = wavelets.periods(P, cfg)
    if periods.size == 0:
        raise AcceptanceError("wavelet", f"no scale: P = {P} months is shorter than wavelet.period_min under the rule {cfg['wavelet.period_max_rule']!r}")
    scales = wavelets.scales(periods, cfg)
    J = periods.size
    coi = wavelets.coi_mask(scales, P)
    xc, mean, variance, ar1 = moments(R)
    flat = ~(variance > 0)
    if flat.any():
        kk, ii = np.nonzero(flat)
        raise AcceptanceError("wavelet", f"{int(flat.sum())} constant rows have no variance to transform or to test",
                              pd.DataFrame({"k": kk, "i": ii, "artifact": "wavelet_series", "problem": "variance > 0"}))
    W = wavelets.transform(xc, scales, cfg)                       # (K, N, J, P)
    w_re, w_im = np.ascontiguousarray(W.real), np.ascontiguousarray(W.imag)
    power = w_re * w_re + w_im * w_im
    threshold = red_noise_level(variance, ar1, periods) * stats.chi2.ppf(cfg["wavelet.significance"], 2) / 2.0
    kc, ic, jc, tc = keys((K, N, J, P))
    k2, i2 = keys((K, N))
    k3, i3, j3 = keys((K, N, J))
    in_coi = np.broadcast_to(coi, (K, N, J, P))
    built = {
        "wavelet_scale": contracts.from_columns({"j": np.arange(J), "period": periods, "scale": scales}, "wavelet_scale"),
        "wavelet_series": contracts.from_columns({"k": k2, "i": i2, "mean": mean.reshape(-1), "variance": variance.reshape(-1),
                                                  "ar1": ar1.reshape(-1)}, "wavelet_series"),
        "wavelet_red_noise": contracts.from_columns({"k": k3, "i": i3, "j": j3, "threshold": threshold.reshape(-1)}, "wavelet_red_noise"),
        "wavelet_cwt": contracts.from_columns({
            "k": kc, "i": ic, "j": jc, "t": months[tc], "w_re": w_re.reshape(-1), "w_im": w_im.reshape(-1),
            "power": power.reshape(-1), "amplitude": np.sqrt(power).reshape(-1), "phase": polar(w_re, w_im).reshape(-1),
            "in_coi": in_coi.reshape(-1), "significant": (in_coi & (power > threshold[..., None])).reshape(-1),
        }, "wavelet_cwt"),
    }
    check(built, frames, cfg)
    info = {
        "family": cfg["wavelet.family"], "omega0": cfg["wavelet.omega0"], "scales": int(J),
        "period_months": [float(periods[0]), float(periods[-1])], "voices_per_octave": cfg["wavelet.voices_per_octave"],
        "padding": cfg["wavelet.padding"], "padded_length": int(wavelets.pad_length(P, scales)),
        "normalization": "unit energy, exact on the discrete grid", "rows": "each (k, i) row on its own, centred on its own mean",
        "coi": "in_coi = at least sqrt(2) x scale months from both ends", "in_coi_months_per_scale": [int(n) for n in coi.sum(axis=1)],
        "red_noise": {"reference": cfg["wavelet.red_noise"], "significance": cfg["wavelet.significance"],
                      "threshold": "variance x P_ar1(period) x chi2_2(significance) / 2"},
        "not_built": "rdiag's s2a.complex and s2a.holonomy (the cell complex needs adjacency edges; a later stage)",
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Acceptance: rdiag's s2a.cwt invariants with k in the key; a failure carries the failing rows."""
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    sc, se, rn, cw = (b[x] for x in ("wavelet_scale", "wavelet_series", "wavelet_red_noise", "wavelet_cwt"))
    J = len(sc)
    problems, rows = [], []
    for name, want in {"wavelet_series": K * N, "wavelet_red_noise": K * N * J, "wavelet_cwt": K * N * J * P}.items():
        if len(b[name]) != want:
            problems.append(f"{name} has {len(b[name])} rows, expected {want}")
    period, scale = sc["period"].to_numpy(), sc["scale"].to_numpy()
    want_period = cfg["wavelet.period_min"] * 2.0 ** (sc["j"].to_numpy() / cfg["wavelet.voices_per_octave"])
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    tidx = np.searchsorted(months, cw["t"].to_numpy())
    reach = np.sqrt(2.0) * scale[cw["j"].to_numpy()]
    w_re, w_im, power, amp, ph = (cw[c].to_numpy() for c in ("w_re", "w_im", "power", "amplitude", "phase"))
    thr = cw[["k", "i", "j"]].merge(rn, on=["k", "i", "j"], how="left")["threshold"].to_numpy()
    lvl = rn[["k", "i"]].merge(se, on=["k", "i"], how="left")
    want_thr = (lvl["variance"].to_numpy() * wavelets.ar1_spectrum(lvl["ar1"].to_numpy(), period[rn["j"].to_numpy()])
                * stats.chi2.ppf(cfg["wavelet.significance"], 2) / 2.0)
    in_coi = cw["in_coi"].to_numpy()
    rules = [
        ("wavelet_scale", sc, np.abs(period - want_period) > 1e-9 * period, "periods start at wavelet.period_min and step by 2^(1 / voices_per_octave)"),
        ("wavelet_scale", sc, np.abs(scale - period / wavelets.fourier_factor(cfg["wavelet.omega0"])) > 1e-9 * period, "scale equals period over the Morlet Fourier factor"),
        ("wavelet_series", se, ~((se["variance"].to_numpy() > 0) & (np.abs(se["ar1"].to_numpy()) < 1)), "variance > 0 and |ar1| < 1"),
        ("wavelet_red_noise", rn, ~(np.abs(rn["threshold"].to_numpy() - want_thr) <= RTOL * want_thr), "threshold equals variance x P_ar1(period) x chi2_2(significance) / 2"),
        ("wavelet_cwt", cw, in_coi != ((tidx >= reach) & (P - 1 - tidx >= reach)), "in_coi follows from the scale and P alone"),
        ("wavelet_cwt", cw, power != w_re * w_re + w_im * w_im, "power equals w_re^2 + w_im^2"),
        ("wavelet_cwt", cw, ~((np.abs(amp * amp - power) <= RTOL * np.maximum(1.0, power)) & (ph > -np.pi) & (ph <= np.pi)
                              & (np.abs(amp * np.cos(ph) - w_re) <= 1e-9 * np.maximum(1.0, amp)) & (np.abs(amp * np.sin(ph) - w_im) <= 1e-9 * np.maximum(1.0, amp))),
         "amplitude and phase are the polar form of (w_re, w_im), phase in (-pi, pi]"),
        ("wavelet_cwt", cw, cw["significant"].to_numpy() != (in_coi & (power > thr)), "significant equals in_coi and power > threshold"),
    ]
    for artifact, frame, mask, rule in rules:
        if mask.any():
            problems.append(f"{artifact}: {rule} ({int(mask.sum())} rows)")
            cols = [c for c in ("k", "i", "j", "t") if c in frame.columns]
            rows.append(frame.loc[mask, cols].assign(artifact=artifact, problem=rule))
    if problems:
        raise AcceptanceError("wavelet", "; ".join(problems), pd.concat(rows, ignore_index=True) if rows else None)
