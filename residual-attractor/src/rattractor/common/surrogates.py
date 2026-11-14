"""Circular-shift surrogates: the null every cross-series test on the archive is judged against (rdiag common/surrogates).

    surrogate[t] = x[(t + offset) mod P],    offset in [m, P - m],    m = surrogates.circular_shift_min_offset
A shift keeps every property of a row exactly (its values, spectrum and autocorrelation) and breaks only
its alignment with other rows. Surrogate series are never stored; a consumer regenerates them from offsets.
Offsets are a pure function of (seed, purpose, configuration, unit), so rdiag's recipe table (s3.surrogate_index)
is not written: it would hold nothing the function does not give back.

    offsets(cfg, purpose, P, n_draws, k, *unit) -> (n_draws,) int64
unit is (i,) for one row (common mode and coincidence give every row its own offset per draw) or
(i_a, i_b) for a pair (coherence shifts only the higher-indexed row of the pair). One generator per unit
yields all of its draws, so a unit's offsets depend on neither the number of series nor the number of
configurations, and asking for more draws extends the sequence without changing the earlier ones.
surrogates.scope: per_configuration gives every configuration its own draws (k enters the key);
shared gives every configuration the same draws. Only P - 2m + 1 offsets exist (n_distinct), so a test
that shifts one row has at most that many different surrogates, however many draws it takes.
"""

from __future__ import annotations

import numpy as np

from ..stages import AcceptanceError
from .seeds import hash32, stream

SCOPES = ("shared", "per_configuration")


def n_distinct(cfg: dict, P: int) -> int:
    """How many different offsets a row of length P has (0 or less: none)."""
    return P - 2 * cfg["surrogates.circular_shift_min_offset"] + 1


def offsets(cfg: dict, purpose: str, P: int, n_draws: int, k: int, *unit: int) -> np.ndarray:
    m = cfg["surrogates.circular_shift_min_offset"]
    if n_distinct(cfg, P) < 1:
        raise AcceptanceError(purpose, f"no circular shift exists: P = {P} is shorter than twice surrogates.circular_shift_min_offset = {m}")
    if not unit:
        raise ValueError("offsets need a unit: (i,) for a row or (i_a, i_b) for a pair")
    scope = SCOPES.index(cfg["surrogates.scope"])
    return stream(cfg, "surrogates", hash32(purpose), scope, k if scope else 0, len(unit), *unit).integers(m, P - m + 1, size=n_draws)


def shift(x: np.ndarray, offset: int) -> np.ndarray:
    """x[(t + offset) mod P] along the last axis."""
    return np.roll(x, -int(offset), axis=-1)
