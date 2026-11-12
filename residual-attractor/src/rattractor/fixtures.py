"""Seeded synthetic series: the six-regime sample series and the known-answer cases.

The six-regime series runs constant -> linear trend -> sinusoid (period 8) ->
AR(1) phi = 0.7 -> random walk -> level shift with a variance burst, each
regime fixture.regime_length long and starting from where the last one ended.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import contracts

REGIMES = ("constant", "trend", "sinusoid8", "ar1_07", "random_walk", "shift_burst")


def constant(n: int, value: float = 10.0) -> np.ndarray:
    return np.full(n, value)


def trend(n: int, rng: np.random.Generator, slope: float = 0.5, sd: float = 1.0, start: float = 0.0) -> np.ndarray:
    return start + slope * np.arange(n) + rng.normal(0.0, sd, n)


def sinusoid(n: int, period: int = 8, amplitude: float = 3.0, start: float = 0.0) -> np.ndarray:
    return start + amplitude * np.sin(2.0 * np.pi * np.arange(n) / period)


def ar1(n: int, rng: np.random.Generator, phi: float = 0.7, sd: float = 1.0, mean: float = 0.0, burn: int = 200) -> np.ndarray:
    e = rng.normal(0.0, sd, n + burn)
    x = np.zeros(n + burn)
    for t in range(1, n + burn):
        x[t] = phi * x[t - 1] + e[t]
    return mean + x[burn:]


def random_walk(n: int, rng: np.random.Generator, sd: float = 1.0, start: float = 0.0) -> np.ndarray:
    return start + np.cumsum(rng.normal(0.0, sd, n))


def six_regime(cfg: dict) -> tuple[pd.DataFrame, list[tuple[str, int, int]]]:
    """(series artifact frame, [(regime, first t, last t)])."""
    rng = np.random.default_rng(cfg["seed"])
    L, sd = cfg["fixture.regime_length"], cfg["fixture.noise_sd"]
    parts, bounds, level = [], [], 10.0
    for name in REGIMES:
        if name == "constant":
            seg = constant(L, level)
        elif name == "trend":
            seg = trend(L, rng, sd=sd, start=level)
        elif name == "sinusoid8":
            seg = sinusoid(L, start=level)
        elif name == "ar1_07":
            seg = ar1(L, rng, sd=sd, mean=level)
        elif name == "random_walk":
            seg = random_walk(L, rng, sd=sd, start=level)
        else:  # shift_burst
            seg = level + 8.0 * sd + rng.normal(0.0, 3.0 * sd, L)
        first = sum(len(p) for p in parts)
        parts.append(seg)
        bounds.append((name, first, first + L - 1))
        level = float(seg[-1])
    y = np.concatenate(parts)
    n = y.size
    n_test = int(round(cfg["fixture.test_fraction"] * n))
    split = np.where(np.arange(n) < n - n_test, "train", "test")
    df = pd.DataFrame({
        "series_id": pd.Series(["fixture_six_regime"] * n, dtype="string"),
        "t": np.arange(n, dtype=np.int32),
        "y": y.astype(np.float64),
        "split": pd.Categorical(split, categories=["train", "test"]),
    })
    return contracts.validate(df, "series"), bounds
