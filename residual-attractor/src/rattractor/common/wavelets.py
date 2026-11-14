"""Morlet machinery shared by the stages that read the transform, so that every one of them uses the same
kernels (rdiag common/wavelets; Torrence and Compo 1998).

    periods(P, cfg)            period_min x 2^(j / voices_per_octave) months, j = 0, 1, ..., while <= the period_max_rule
    scales(periods, cfg)       period / (4 pi / (omega0 + sqrt(2 + omega0^2)))
    transform(x, scales, cfg)  W[..., j, t] for every row x[..., t]
    coi_mask(scales, P)        in_coi[j, t] = t >= sqrt(2) s_j and P - 1 - t >= sqrt(2) s_j
    ar1_spectrum(a, periods)   (1 - a^2) / (1 + a^2 - 2 a cos(2 pi / period)); its mean over frequency is 1

The transform is Torrence and Compo's, taken in Fourier space on the row padded with zeros to length M:
    W[j, t] = (1 / M) sum_k xhat[k] psihat_j[k] exp(2 pi i k t / M),   t = 0..P-1
    psihat_j[k] = c_j exp(-(s_j w_k - omega0)^2 / 2) at w_k = 2 pi k / M for k = 1..M/2, and 0 at every other k
so the phase of W grows with time on an oscillation, and a row that is a sinusoid of period p has its largest
power at the scale whose Fourier period is p. Unit energy: c_j makes sum_k psihat_j[k]^2 = M exactly, so white
noise of variance v has expected power v at every scale. That is Torrence and Compo's factor
(2 pi s)^(1/2) pi^(-1/4) wherever the wavelet's pass band lies below the Nyquist frequency, and differs from it
at the shortest periods, where their factor understates the power (white noise would average 0.50 v at period 2,
0.78 v and 0.95 v at the next two scales). M is the power of two at or above P + PAD_EFOLDINGS e-folding times
(sqrt(2) s) of the largest scale, so nothing wraps around above rounding. The row is transformed as given; the
stages centre it first.

The cone of influence follows rdiag's naming: in_coi is true where a cell is at least one e-folding time
sqrt(2) s_j from both ends of the row (the cells Torrence and Compo treat as free of edge effects). It depends
on the scales and P only.
"""

from __future__ import annotations

import re

import numpy as np

PAD_EFOLDINGS = 6.0   # zero padding of the transform in e-folding times of the largest scale; exp(-36) = 2e-16
_RULE = re.compile(r"P / (\d+(?:\.\d+)?)")


def period_max_divisor(rule: str) -> float:
    """The number d in wavelet.period_max_rule = "P / d": the longest period is P / d months."""
    m = _RULE.fullmatch(rule)
    if m is None or float(m.group(1)) < 1.0:
        raise ValueError(f'wavelet.period_max_rule {rule!r} is not "P / d" with a number d >= 1')
    return float(m.group(1))


def periods(P: int, cfg: dict) -> np.ndarray:
    """Fourier periods in months, ascending: the geometric grid from period_min up to P / d."""
    p0, voices = float(cfg["wavelet.period_min"]), cfg["wavelet.voices_per_octave"]
    top = P / period_max_divisor(cfg["wavelet.period_max_rule"])
    if top < p0:
        return np.empty(0)
    J = int(np.floor(voices * np.log2(top / p0) + 1e-9)) + 1
    return p0 * 2.0 ** (np.arange(J) / voices)


def fourier_factor(omega0: float) -> float:
    """Fourier period / scale for the Morlet wavelet."""
    return 4.0 * np.pi / (omega0 + np.sqrt(2.0 + omega0 * omega0))


def scales(periods: np.ndarray, cfg: dict) -> np.ndarray:
    return np.asarray(periods, dtype=np.float64) / fourier_factor(float(cfg["wavelet.omega0"]))


def pad_length(P: int, scales: np.ndarray) -> int:
    need = P + int(np.ceil(PAD_EFOLDINGS * np.sqrt(2.0) * float(np.max(scales))))
    return 1 << int(np.ceil(np.log2(need)))


def daughters(scales: np.ndarray, M: int, omega0: float) -> np.ndarray:
    """psihat[j, k] for k = 0..M-1: real, zero outside k = 1..M/2, sum over k of its square = M."""
    w = 2.0 * np.pi * np.arange(1, M // 2 + 1) / M
    g = np.exp(-0.5 * (np.asarray(scales)[:, None] * w[None, :] - omega0) ** 2)
    g *= np.sqrt(M / (g * g).sum(axis=1, keepdims=True))
    out = np.zeros((len(scales), M))
    out[:, 1 : M // 2 + 1] = g
    return out


def transform(x: np.ndarray, scales: np.ndarray, cfg: dict) -> np.ndarray:
    """complex128 W[..., j, t] of every row x[..., t]. Each row is transformed on its own."""
    x = np.asarray(x, dtype=np.float64)
    P = x.shape[-1]
    M = pad_length(P, scales)
    psi = daughters(scales, M, float(cfg["wavelet.omega0"]))
    xhat = np.fft.fft(x, n=M, axis=-1)
    return np.fft.ifft(xhat[..., None, :] * psi, axis=-1)[..., :P]


def coi_mask(scales: np.ndarray, P: int) -> np.ndarray:
    t = np.arange(P)[None, :]
    reach = np.sqrt(2.0) * np.asarray(scales)[:, None]
    return (t >= reach) & (P - 1 - t >= reach)


def ar1_spectrum(a, periods: np.ndarray) -> np.ndarray:
    """Normalized AR(1) spectrum at each period; a broadcasts against periods (a[..., None] for many rows)."""
    a = np.asarray(a, dtype=np.float64)
    return (1.0 - a * a) / (1.0 + a * a - 2.0 * a * np.cos(2.0 * np.pi / np.asarray(periods)))
