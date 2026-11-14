"""The shared randomness and surrogate recipes the analyses on the archive draw from."""

import numpy as np
import pytest

from rattractor.common import seeds, surrogates
from rattractor.stages import AcceptanceError


def test_hash32_is_the_first_four_sha256_bytes():
    # fixed numbers, so a change of hash (or Python's salted hash()) cannot pass unnoticed
    assert seeds.hash32("surrogates") == 778357987
    assert seeds.hash32("coherence") == 3002593890


def test_stream_repeats_and_separates(cfg):
    a = seeds.stream(cfg, "coherence", 3, 1).random(8)
    assert np.array_equal(a, seeds.stream(cfg, "coherence", 3, 1).random(8))
    for other in (seeds.stream(cfg, "coherence", 3, 2), seeds.stream(cfg, "coherence", 1, 3),
                  seeds.stream(cfg, "coincidence", 3, 1), seeds.stream(cfg, "coherence", 3),
                  seeds.stream({**cfg, "seed": cfg["seed"] + 1}, "coherence", 3, 1)):
        assert not np.array_equal(a, other.random(8))


@pytest.mark.parametrize("keys", [(-1,), (1.0,), (True,), ("1",)])
def test_stream_refuses_keys_that_are_not_non_negative_ints(cfg, keys):
    with pytest.raises(ValueError):
        seeds.stream(cfg, "coherence", *keys)


def test_offsets_cover_exactly_the_allowed_range(cfg):
    P, m = 98, cfg["surrogates.circular_shift_min_offset"]
    off = surrogates.offsets(cfg, "common_mode", P, 20000, 0, 0)
    assert off.dtype == np.int64 and off.shape == (20000,)
    assert set(off.tolist()) == set(range(m, P - m + 1))  # both ends reached, nothing outside
    assert surrogates.n_distinct(cfg, P) == P - 2 * m + 1 == len(set(off.tolist()))


def test_offsets_repeat_and_extend_without_changing(cfg):
    a = surrogates.offsets(cfg, "coherence", 98, 1000, 5, 2, 9)
    assert np.array_equal(a, surrogates.offsets(cfg, "coherence", 98, 1000, 5, 2, 9))
    assert np.array_equal(a[:10], surrogates.offsets(cfg, "coherence", 98, 10, 5, 2, 9))


def test_offsets_differ_by_purpose_configuration_and_unit(cfg):
    a = surrogates.offsets(cfg, "coherence", 98, 200, 5, 2, 9)
    for other in (surrogates.offsets(cfg, "coincidence", 98, 200, 5, 2, 9),   # purpose
                  surrogates.offsets(cfg, "coherence", 98, 200, 6, 2, 9),     # configuration
                  surrogates.offsets(cfg, "coherence", 98, 200, 5, 2, 10),    # unit
                  surrogates.offsets(cfg, "coherence", 98, 200, 5, 9, 2),     # the pair's order
                  surrogates.offsets(cfg, "coherence", 98, 200, 2, 9),        # a row (k = 2, i = 9) is not the pair (2, 9)
                  surrogates.offsets({**cfg, "seed": cfg["seed"] + 1}, "coherence", 98, 200, 5, 2, 9)):
        assert not np.array_equal(a, other)


def test_scope_decides_whether_configurations_share_draws(cfg):
    assert cfg["surrogates.scope"] == "per_configuration"
    shared = {**cfg, "surrogates.scope": "shared"}
    assert np.array_equal(surrogates.offsets(shared, "common_mode", 98, 300, 0, 4), surrogates.offsets(shared, "common_mode", 98, 300, 53, 4))
    assert not np.array_equal(surrogates.offsets(cfg, "common_mode", 98, 300, 0, 4), surrogates.offsets(cfg, "common_mode", 98, 300, 53, 4))
    # the two scopes are different streams even for configuration 0
    assert not np.array_equal(surrogates.offsets(shared, "common_mode", 98, 300, 0, 4), surrogates.offsets(cfg, "common_mode", 98, 300, 0, 4))


def test_a_series_too_short_for_any_shift_stops_with_the_purpose_named(cfg):
    m = cfg["surrogates.circular_shift_min_offset"]
    assert surrogates.offsets(cfg, "coherence", 2 * m, 5, 0, 0).tolist() == [m] * 5  # exactly one offset exists
    with pytest.raises(AcceptanceError, match="coherence: no circular shift exists"):
        surrogates.offsets(cfg, "coherence", 2 * m - 1, 5, 0, 0)
    with pytest.raises(ValueError):
        surrogates.offsets(cfg, "coherence", 98, 5, 0)  # no unit


def test_shift_moves_alignment_and_nothing_else(rng):
    x = rng.standard_normal((3, 98))
    y = surrogates.shift(x, 17)
    assert all(y[r, t] == x[r, (t + 17) % 98] for r in range(3) for t in (0, 1, 50, 80, 81, 97))
    assert np.array_equal(np.sort(y, axis=-1), np.sort(x, axis=-1))                    # the same values
    assert np.allclose(np.abs(np.fft.rfft(y)), np.abs(np.fft.rfft(x)), rtol=1e-12, atol=1e-12)  # the same spectrum
    assert np.array_equal(surrogates.shift(x, 98), x) and np.array_equal(surrogates.shift(x, 0), x)
