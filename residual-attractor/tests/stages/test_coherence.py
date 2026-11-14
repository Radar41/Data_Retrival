"""Stage coherence: wavelet coherence, relative phase and circular-shift significance for every pair inside one configuration (rdiag s3.coherence under v2)."""

import re

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.common import surrogates, wavelets
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, coherence, spectral, wavelet
from tests.stages.test_wavelet import (ar1_rows, assert_frames_equal_under_reindexing, assert_other_configurations_identical,
                                       fixture_build, make_grid, rows_of, subgrid, three_series_grid)


def staged(R, cfg):
    """(frames, wav, spec, built, info) of the three stages up to coherence on a synthetic field R[k, i, t]."""
    frames = make_grid(R)
    wav, _ = wavelet.run(frames, cfg)
    spec, _ = spectral.run(frames, wav, cfg)
    built, info = coherence.run(frames, wav, spec, cfg)
    return frames, wav, spec, built, info


def ar2(rng, n, period, r, burn=300):
    """A stochastic cycle: AR(2) with its spectral peak at `period` months and pole radius r, unit variance."""
    e = rng.standard_normal(n + burn)
    x = np.zeros(n + burn)
    for t in range(2, n + burn):
        x[t] = 2 * r * np.cos(2 * np.pi / period) * x[t - 1] - r * r * x[t - 2] + e[t]
    return x[burn:] / x[burn:].std()


LAGS = (2, -3, 0)   # months by which series 1 trails series 0 in configurations 0, 1, 2 of `delayed` (negative: series 1 is ahead)


def delayed_field(seed=302, P=128):
    """K = 3 x 3 series x P months. Series 0 and 1 share a stochastic 10-month cycle, series 1 carrying it LAGS[k] months later; series 2 is unrelated."""
    rng = np.random.default_rng(seed)
    R = 0.3 * rng.standard_normal((3, 3, P))
    for k, L in enumerate(LAGS):
        c = ar2(rng, P + 20, 10.0, 0.9)
        R[k, 0] += c[10 : 10 + P]
        R[k, 1] += c[10 - L : 10 - L + P]
    R[:, 2] = ar1_rows(rng, (3, P), 0.5)
    return R


@pytest.fixture(scope="module")
def delayed(cfg):
    R = delayed_field()
    return (R,) + staged(R, cfg)


# ---- the pieces ---------------------------------------------------------------------------------

def test_smoothing_kernels(cfg, rng):
    P = 60
    s = wavelets.scales(wavelets.periods(P, cfg), cfg)
    G, b = wavelets.smoother(s, P, cfg)
    np.testing.assert_allclose(b, np.array([0.9, 1, 1, 1, 0.9]) / 4.8, rtol=1e-12)   # 0.6 octaves = 4.8 steps of 1/8
    assert wavelets.scale_weights({**cfg, "coherence.scale_smoothing_width": 0.1}).tolist() == [1.0]
    j, u = 5, 30
    g = np.exp(-0.5 * ((np.arange(P) - u) / s[j]) ** 2)
    np.testing.assert_allclose(G[j, :, u], g / np.exp(-0.5 * (np.arange(-400, 401) / s[j]) ** 2).sum(), rtol=1e-12)
    assert G[j, u, :].sum() == pytest.approx(1.0, abs=1e-12) and G[j, 0, :].sum() < 0.6    # nothing is renormalized at the ends
    f = rng.standard_normal((2, s.size, P)) + 1j * rng.standard_normal((2, s.size, P))
    out = wavelets.smooth(f, (G, b))
    t = np.einsum("rjt,jtu->rju", f, G)
    want = np.zeros_like(t)
    for jj in range(s.size):
        for d in range(-2, 3):
            if 0 <= jj + d < s.size:
                want[:, jj] += b[d + 2] * t[:, jj + d]
    np.testing.assert_allclose(out, want, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(wavelets.smooth(f[0], (G, b)), wavelets.smooth(f[:1], (G, b))[0])
    np.testing.assert_allclose(wavelets.smooth(f.real, (G, b)), out.real, rtol=0, atol=1e-13)


def test_pairs_are_ordered_and_positions_invert_them():
    ia, ib = coherence.pairs(4)
    assert list(zip(ia.tolist(), ib.tolist())) == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    assert coherence.pair_position(ia, ib, 4).tolist() == list(range(6))
    assert coherence.pairs(1)[0].size == 0 and coherence.pairs(0)[0].size == 0
    ia, ib = coherence.pairs(14)
    assert ia.size == 91 and (ia < ib).all() and coherence.pair_position(ia, ib, 14).tolist() == list(range(91))


def test_the_level_is_an_order_statistic(rng):
    assert [coherence.rank_level(n, 0.95) for n in (18, 19, 39, 75, 97, 1000)] == [0, 1, 2, 3, 4, 50]
    assert coherence.rank_level(75, 0.90) == 7 and coherence.rank_level(9, 0.9) == 1 and coherence.rank_level(8, 0.9) == 0
    surr = rng.random((75, 4, 5))
    np.testing.assert_array_equal(coherence.cell_level(surr, 0.95), np.sort(surr, axis=0)[-3])
    np.testing.assert_array_equal(coherence.cell_level(surr[:19], 0.95), surr[:19].max(axis=0))
    np.testing.assert_array_equal(coherence.cell_level(surr[:18], 0.95), np.ones((4, 5)))     # no level is that strict
    x = rng.random((76, 20000))                                  # exchangeable values clear the level r times in n + 1
    assert (x[0] > coherence.cell_level(x[1:], 0.95)).mean() == pytest.approx(3 / 76, abs=0.005)


def test_every_offset_is_used_once_when_the_draws_would_cover_them(cfg):
    assert coherence.plan(cfg, 98) == {"mode": "enumerated", "n": 75, "requested": 1000, "distinct_offsets": 75, "rank": 3, "smallest_p_value": 1 / 76}
    offs = coherence.pair_offsets(cfg, 98, 5, 2, 9)
    assert offs.tolist() == list(range(12, 87))
    assert set(np.unique(surrogates.offsets(cfg, "coherence", 98, 20000, 5, 2, 9)).tolist()) == set(offs.tolist())   # the shared recipe's own support
    few = {**cfg, "surrogates.n_coherence": 20}
    assert coherence.plan(few, 98) == {"mode": "drawn", "n": 20, "requested": 20, "distinct_offsets": 75, "rank": 1, "smallest_p_value": 1 / 21}
    np.testing.assert_array_equal(coherence.pair_offsets(few, 98, 5, 2, 9), surrogates.offsets(few, "coherence", 98, 20, 5, 2, 9))
    assert coherence.plan({**cfg, "surrogates.n_coherence": 75}, 98)["mode"] == "enumerated"
    assert coherence.plan({**cfg, "surrogates.n_coherence": 74}, 98)["mode"] == "drawn"
    assert coherence.plan(cfg, 24)["n"] == 1
    with pytest.raises(AcceptanceError, match="no circular shift exists"):
        coherence.plan(cfg, 23)


def test_scopes_are_all_scales_and_every_overlap_of_the_two_rows_bands():
    assert coherence.scopes([(0, 3, 6), (1, 10, 14)], [(0, 5, 11), (1, 20, 22)], 33) == [(-1, -1, 0, 32), (0, 0, 5, 6), (1, 0, 10, 11)]
    assert coherence.scopes([], [(0, 5, 11)], 33) == [(-1, -1, 0, 32)]
    assert coherence.scopes([(0, 3, 6)], [(0, 6, 6)], 7) == [(-1, -1, 0, 6), (0, 0, 6, 6)]     # one shared scale is an overlap
    assert coherence.scopes([(0, 3, 6)], [(0, 4, 5)], 0) == []                                 # no scale, no scope


def test_the_cross_spectrum_taken_the_other_way_round_is_the_exact_conjugate(rng):
    a = rng.standard_normal((7, 50)) + 1j * rng.standard_normal((7, 50))
    b = rng.standard_normal((3, 7, 50)) + 1j * rng.standard_normal((3, 7, 50))
    c, d = coherence.cross_spectrum(a[None], b), coherence.cross_spectrum(b, a[None])
    np.testing.assert_array_equal(c.real, d.real)
    np.testing.assert_array_equal(c.imag, -d.imag)
    np.testing.assert_allclose(c, a[None] * np.conj(b), rtol=1e-13, atol=1e-13)


# ---- the definition, written out a second time --------------------------------------------------

def reference(xa, xb, bands_a, bands_b, offsets, cfg):
    """One pair from the definition: explicit kernels, numpy.roll for the shifts, a sort for the level, masks for the scopes."""
    P = xa.size
    per = wavelets.periods(P, cfg)
    s = wavelets.scales(per, cfg)
    J, q, t = s.size, cfg["coherence.quantile"], np.arange(P)
    gauss = [np.exp(-0.5 * ((t[:, None] - t[None, :]) / sj) ** 2) / np.exp(-0.5 * (np.arange(-3000, 3001) / sj) ** 2).sum() for sj in s]
    h = cfg["coherence.scale_smoothing_width"] * cfg["wavelet.voices_per_octave"] / 2
    box = np.array([[max(0.0, min(jj - j + 0.5, h) - max(jj - j - 0.5, -h)) / (2 * h) for jj in range(J)] for j in range(J)])

    def S(f):
        return box @ np.stack([gauss[j] @ f[j] for j in range(J)])

    def fields(a, b):
        Wa, Wb = wavelets.transform(a, s, cfg), wavelets.transform(b, s, cfg)
        c = S(Wa * np.conj(Wb) / s[:, None])
        return np.abs(c) ** 2 / (S(np.abs(Wa) ** 2 / s[:, None]) * S(np.abs(Wb) ** 2 / s[:, None])), np.angle(c)

    a, b = xa - xa.mean(), xb - xb.mean()
    r2, phase = fields(a, b)
    null = np.stack([fields(a, np.roll(b, -int(o)))[0] for o in offsets])
    n = null.shape[0]
    r = int(np.floor((1 - q) * (n + 1) + 1e-9))
    level = np.sort(null, axis=0)[n - r] if r else np.ones_like(r2)
    cone = np.array([[min(u, P - 1 - u) >= np.sqrt(2) * sj for u in t] for sj in s])
    sig = cone & (r2 > level)
    overlaps = [(x[0], y[0], max(x[1], y[1]), min(x[2], y[2])) for x in bands_a for y in bands_b if max(x[1], y[1]) <= min(x[2], y[2])]
    rows = []
    for band_a, band_b, lo, hi in [(-1, -1, 0, J - 1)] + overlaps:
        w = np.zeros((J, P), bool)
        w[lo : hi + 1] = cone[lo : hi + 1]
        stat = r2[w].mean()
        pv = (1 + sum(null[d][w].mean() >= stat for d in range(n))) / (1 + n)
        ws = w & sig
        ph = period = lag = np.nan
        if ws.any():
            ph = np.angle(np.exp(1j * phase[ws]).sum())
            period = np.exp(np.log(np.broadcast_to(per[:, None], (J, P))[ws]).mean())
            lag = ph * period / (2 * np.pi)
        rows.append((band_a, band_b, lo, hi, int(w.sum()), int(ws.sum()), stat, n, pv, ph, period, lag))
    return r2, phase, level, cone, sig, rows


def _bands(spec, k, i):
    b = rows_of(spec["spectral_bands"], k=k, i=i)
    return list(zip(b["band"].tolist(), b["j_lo"].tolist(), b["j_hi"].tolist()))


def _assert_pair_matches(built, spec, R, k, a, b, offsets, cfg):
    r2, phase, level, cone, sig, rows = reference(R[k, a], R[k, b], _bands(spec, k, a), _bands(spec, k, b), offsets, cfg)
    ce = rows_of(built["coherence_cells"], k=k, i_a=a, i_b=b).sort_values(["j", "t"])
    shape = r2.shape
    np.testing.assert_allclose(ce["r2"].to_numpy().reshape(shape), r2, rtol=0, atol=1e-10)
    np.testing.assert_allclose(ce["r2_q"].to_numpy().reshape(shape), level, rtol=0, atol=1e-10)
    coherency = np.sqrt(r2) * np.exp(1j * phase)                      # a phase is only as well defined as the coherence is large
    np.testing.assert_allclose(np.sqrt(ce["r2"].to_numpy()) * np.exp(1j * ce["phase"].to_numpy()), coherency.reshape(-1), rtol=0, atol=1e-8)
    np.testing.assert_array_equal(ce["in_coi"].to_numpy().reshape(shape), cone)
    np.testing.assert_array_equal(ce["significant"].to_numpy().reshape(shape), sig)
    sp = rows_of(built["coherence_scope"], k=k, i_a=a, i_b=b).sort_values(["band_a", "band_b"])
    assert len(sp) == len(rows)
    for got, want in zip(sp.itertuples(index=False), sorted(rows)):
        assert (got.band_a, got.band_b, got.j_lo, got.j_hi, got.n_cells, got.n_significant, got.n_surrogates) == want[:6] + (want[7],)
        np.testing.assert_allclose([got.r2_mean, got.p_value, got.phase, got.period, got.lag_months], [want[6]] + list(want[8:]), rtol=0, atol=1e-9)
    return sp


def test_cells_and_scopes_follow_the_definition(cfg):
    rng = np.random.default_rng(311)
    P = 60
    R = ar1_rows(rng, (2, 3, P), 0.4)
    R[:, 0] += 1.5 * ar2(rng, P, 6.0, 0.9)
    R[:, 1] += 1.5 * ar2(rng, P, 6.0, 0.9)
    _, wav, spec, built, info = staged(R, cfg)
    assert info["surrogates"]["mode"] == "enumerated" and info["surrogates"]["n"] == 37 and info["surrogates"]["rank"] == 1
    scopes = [_assert_pair_matches(built, spec, R, 1, a, b, range(12, P - 12 + 1), cfg) for a, b in ((0, 1), (0, 2), (1, 2))]
    assert sum(len(s) for s in scopes) > 3                      # at least one band overlap went through the comparison


def test_drawn_offsets_are_the_shared_recipes_and_keyed_by_configuration_and_pair(cfg):
    few = {**cfg, "surrogates.n_coherence": 20}
    rng = np.random.default_rng(312)
    R = ar1_rows(rng, (2, 3, 98), 0.4)
    _, wav, spec, built, info = staged(R, few)
    assert info["surrogates"]["mode"] == "drawn" and (built["coherence_scope"]["n_surrogates"] == 20).all()
    for k, a, b in ((0, 0, 1), (1, 0, 2), (1, 1, 2)):
        _assert_pair_matches(built, spec, R, k, a, b, surrogates.offsets(few, "coherence", 98, 20, k, a, b), few)


def test_shared_scope_gives_every_configuration_the_same_draws(cfg, rng):
    x = ar1_rows(rng, (1, 3, 98), 0.5)
    R = np.concatenate([x, x])                                   # two configurations with the same rows
    few = {**cfg, "surrogates.n_coherence": 20}
    own, shared = staged(R, few)[3]["coherence_cells"], staged(R, {**few, "surrogates.scope": "shared"})[3]["coherence_cells"]
    a, b = rows_of(own, k=0), rows_of(own, k=1)
    np.testing.assert_array_equal(a["r2"], b["r2"])
    assert not a["r2_q"].equals(b["r2_q"])                       # per_configuration: each has its own draws
    pd.testing.assert_frame_equal(rows_of(shared, k=0).drop(columns="k"), rows_of(shared, k=1).drop(columns="k"), check_exact=True)
    every = staged(R, cfg)[3]["coherence_cells"]                 # with every offset used once, nothing is left to draw
    pd.testing.assert_frame_equal(rows_of(every, k=0).drop(columns="k"), rows_of(every, k=1).drop(columns="k"), check_exact=True)


# ---- known answers ------------------------------------------------------------------------------

def test_a_planted_delay_comes_back_in_months_with_its_sign(delayed):
    *_, b, info = delayed
    sp = b["coherence_scope"]
    floor = 1 / 106                                              # 128 months leave 105 shifts
    assert info["surrogates"]["n"] == 105
    for k, L in enumerate(LAGS):
        rows = rows_of(sp, k=k, i_a=0, i_b=1)
        band, every = rows[rows["band_a"] >= 0], rows[rows["band_a"] == -1].iloc[0]
        assert len(band) >= 1 and (rows["p_value"] == floor).all()             # no shift is as coherent as the true alignment
        assert (band["n_significant"] > 0.8 * band["n_cells"]).all() and every["n_significant"] > 0.4 * every["n_cells"]
        np.testing.assert_allclose(band["lag_months"], L, atol=0.4)            # positive: series 0 leads
        assert every["lag_months"] == pytest.approx(L, abs=0.5)
        assert ((band["period"] > 6) & (band["period"] < 16)).all()            # around the shared 10-month cycle
    unrelated = sp[sp["i_b"] == 2]
    assert (unrelated["p_value"] > 0.05).all() and (unrelated["n_significant"] < 0.2 * unrelated["n_cells"]).all()


def test_swapping_the_two_series_flips_the_lag(delayed, cfg):
    R, *_, b, _ = delayed
    *_, s, _ = staged(R[:, [1, 0, 2]], cfg)
    c1, c2 = rows_of(b["coherence_cells"], i_a=0, i_b=1), rows_of(s["coherence_cells"], i_a=0, i_b=1)
    np.testing.assert_array_equal(c1["r2"], c2["r2"])                          # coherence has no direction, bit for bit
    np.testing.assert_array_equal(c1["phase"], -c2["phase"])                   # the phase has
    assert (c1["phase"].abs() > 1e-3).mean() > 0.9
    for k, L in enumerate(LAGS):
        one, two = rows_of(b["coherence_scope"], k=k, i_a=0, i_b=1), rows_of(s["coherence_scope"], k=k, i_a=0, i_b=1)
        np.testing.assert_allclose(two["lag_months"], -one["lag_months"], atol=0.2)      # which row is shifted changes the significant cells a little
        if L:
            assert (np.sign(one["lag_months"]) == np.sign(L)).all() and (np.sign(two["lag_months"]) == -np.sign(L)).all()


def test_a_shared_deterministic_cycle_is_coherent_under_every_shift_so_it_is_not_significant(cfg):
    P = 128
    t, per = np.arange(P), wavelets.periods(P, cfg)
    R = 0.3 * np.random.default_rng(1).standard_normal((1, 2, P))
    R[0, 0] += np.sin(2 * np.pi * t / per[16])                                 # 8 months
    R[0, 1] += np.sin(2 * np.pi * (t - 2) / per[16])                           # the same cycle two months later
    *_, b, _ = staged(R, cfg)
    c = b["coherence_cells"]
    c = c[(c["j"] == 16) & c["in_coi"]]
    lag = c["phase"] * per[16] / (2 * np.pi)
    assert c["r2"].min() > 0.9 and lag.mean() == pytest.approx(2.0, abs=0.15) and lag.std() < 0.3    # the phase still gives the two months
    assert c["r2_q"].min() > 0.95 and not c["significant"].any()               # but every shift of a pure cycle is as coherent
    band = b["coherence_scope"][b["coherence_scope"]["band_a"] >= 0]
    assert len(band) == 1 and band["p_value"].iloc[0] > 0.5 and band["n_significant"].iloc[0] == 0 and band["lag_months"].isna().all()


@pytest.fixture(scope="module")
def unrelated():
    return ar1_rows(np.random.default_rng(307), (6, 8, 98), 0.5)                # 168 pairs of independent rows


def _null_summary(R, cfg):
    *_, b, info = staged(R, cfg)
    ce, sp = b["coherence_cells"], b["coherence_scope"]
    inc = ce[ce["in_coi"]]
    every = sp[sp["band_a"] == -1]
    return info["surrogates"], inc["significant"].mean(), inc.groupby("j")["significant"].mean(), every["p_value"]


def test_with_every_nonzero_shift_in_the_null_unrelated_rows_meet_the_rank_rule(unrelated, cfg):
    s, share, by_scale, p = _null_summary(unrelated, {**cfg, "surrogates.circular_shift_min_offset": 1})
    assert (s["n"], s["rank"]) == (97, 4)                                      # the 98 alignments are exchangeable: 4 / 98 = 4.1%
    assert 0.030 < share < 0.052, share
    assert by_scale.max() < 0.09, by_scale.to_dict()
    assert 0.44 < p.mean() < 0.56 and (p <= 0.05).mean() < 0.09 and (p == 1 / 98).mean() < 0.035


def test_rdiags_minimum_offset_leaves_the_true_alignment_without_neighbours_in_the_null(unrelated, cfg):
    s, share, by_scale, p = _null_summary(unrelated, cfg)
    assert (s["n"], s["rank"], s["min_offset"]) == (75, 3, 12)                 # the rule alone would give 3 / 76 = 3.9%
    assert 0.055 < share < 0.105, share                                        # measured on 6,552 pairs: 7.7%
    assert 0.03 < by_scale[:5].mean() < 0.07 and by_scale[28:].mean() > 0.08, by_scale.to_dict()     # 5% at short periods, 12 to 15% at long
    assert (p == 1 / 76).mean() > 0.03, (p == 1 / 76).mean()                   # the smallest p-value: 7% of unrelated pairs, not 1.3%


def test_cells_outside_the_cone_are_kept_flagged_and_never_counted(delayed):
    _, frames, wav, _, b, _ = delayed
    ce, sp = b["coherence_cells"], b["coherence_scope"]
    K, NP, J, P = 3, 3, len(wav["wavelet_scale"]), len(frames["grid_month"])
    assert len(ce) == K * NP * J * P and ce[["r2", "phase", "r2_q"]].notna().all().all()
    cone = rows_of(wav["wavelet_cwt"], k=0, i=0).sort_values(["j", "t"])["in_coi"].to_numpy()
    for (k, a, c), g in ce.groupby(["k", "i_a", "i_b"]):
        np.testing.assert_array_equal(g.sort_values(["j", "t"])["in_coi"].to_numpy(), cone)
    out = ce[~ce["in_coi"]]
    assert len(out) > 0 and not out["significant"].any()
    assert (out["r2"] > out["r2_q"]).sum() > 100                               # cells that would count if the cone did not exclude them
    assert (sp.loc[sp["band_a"] == -1, "n_cells"] == cone.sum()).all()
    counted = ce[ce["in_coi"]].groupby(["k", "i_a", "i_b"])["significant"].sum().reset_index()
    got = sp[sp["band_a"] == -1].merge(counted, on=["k", "i_a", "i_b"])
    assert (got["n_significant"] == got["significant"]).all()


def test_a_row_against_itself_is_fully_coherent_and_in_phase(cfg, rng):
    x = ar1_rows(rng, (1, 1, 98), 0.4)
    *_, b, _ = staged(np.concatenate([x, x], axis=1), cfg)
    ce, row = b["coherence_cells"], b["coherence_scope"].iloc[0]
    assert ce["r2"].min() > 1 - 1e-12 and (ce["phase"] == 0).all()
    assert ce.loc[ce["in_coi"], "significant"].all()
    assert row["n_significant"] == row["n_cells"] and row["p_value"] == 1 / 76 and row["phase"] == 0 and row["lag_months"] == 0
    assert row["r2_mean"] == pytest.approx(1.0, abs=1e-12)


def test_rescaling_or_shifting_a_row_changes_nothing_and_a_sign_flip_turns_the_phase_by_pi(cfg, rng):
    R = ar1_rows(rng, (1, 3, 98), 0.5)
    R2 = R.copy()
    R2[0, 1] = 3.7 * R[0, 1] + 100.0
    R2[0, 2] = -R[0, 2]
    one, two = staged(R, cfg)[3]["coherence_cells"], staged(R2, cfg)[3]["coherence_cells"]
    np.testing.assert_allclose(two["r2"], one["r2"], rtol=0, atol=1e-9)
    np.testing.assert_allclose(two["r2_q"], one["r2_q"], rtol=0, atol=1e-9)
    np.testing.assert_array_equal(two["significant"], one["significant"])
    turn = np.where(two["i_b"] == 2, -1.0, 1.0)                                # pairs with the flipped row
    np.testing.assert_allclose(np.sqrt(two["r2"]) * np.exp(1j * two["phase"]), turn * np.sqrt(one["r2"]) * np.exp(1j * one["phase"]), rtol=0, atol=1e-8)


# ---- the archive rule and count independence ----------------------------------------------------

@pytest.mark.parametrize("draws", [1000, 20])
def test_changing_one_configuration_leaves_every_other_row_bit_identical(delayed, cfg, draws):
    R = delayed[0]
    c = {**cfg, "surrogates.n_coherence": draws}
    built = delayed[4] if draws == 1000 else staged(R, c)[3]
    R2 = R.copy()
    R2[1] = ar1_rows(np.random.default_rng(8), R[1].shape, 0.8) * 3.0
    other = staged(R2, c)[3]
    assert_other_configurations_identical(built, other, changed=1)
    assert not rows_of(built["coherence_cells"], k=1)["r2"].equals(rows_of(other["coherence_cells"], k=1)["r2"])


def test_rows_do_not_depend_on_how_many_series_or_configurations_there_are(delayed, cfg):
    R, frames, _, _, built, _ = delayed

    def on(sub, c):
        wav, _ = wavelet.run(sub, c)
        spec, _ = spectral.run(sub, wav, c)
        return coherence.run(sub, wav, spec, c)[0]

    ks, iis = [2, 0], [0, 2]            # every offset is used once, so no index enters; a pair keeps its direction when the order is kept
    small = on(subgrid(frames, ks=ks, iis=iis), cfg)
    for name in built:
        assert_frames_equal_under_reindexing(small[name], built[name], kmap=ks, imap=iis, pair=True)
    few = {**cfg, "surrogates.n_coherence": 20}                 # drawn offsets are keyed by (k, i_a, i_b): units added after a pair leave it alone
    full, small = on(frames, few), on(subgrid(frames, ks=[0, 1], iis=[0, 1]), few)
    for name in full:
        assert_frames_equal_under_reindexing(small[name], full[name], kmap=[0, 1], imap=[0, 1], pair=True)


# ---- acceptance ---------------------------------------------------------------------------------

def _with(b, name, **cols):
    return {**b, name: b[name].assign(**cols)}


def _at(b, name, row, col, value):
    f = b[name].copy()
    f.loc[row, col] = value
    return {**b, name: f}


def _first(b, **where):
    """The index of the first scope row that matches."""
    sp = b["coherence_scope"]
    m = np.ones(len(sp), bool)
    for col, val in where.items():
        m &= (sp[col] == val).to_numpy() if not callable(val) else val(sp[col]).to_numpy()
    return sp.index[m][0]


SCOPE_RULE = "the scopes of a pair are all scales and every overlap of its two rows' bands"
COUNT_RULE = "n_cells and n_significant count the scope's in-cone and significant cells"
MEAN_RULE = "r2_mean is the mean r2 over the scope's in-cone cells, null where it has none"
P_RULE = "p_value is (1 + a count) / (1 + n_surrogates), in (0, 1], null where the scope has no in-cone cell"
LAG_RULE = "phase, period and lag_months exist exactly where the scope has significant cells, and lag_months = phase x period / (2 pi)"


@pytest.mark.parametrize("rule, corrupt", [
    ("pairs have i_a < i_b", lambda b: _with(b, "coherence_cells", i_a=b["coherence_cells"]["i_b"])),
    ("r2 and r2_q lie in [0, 1] and phase in (-pi, pi]", lambda b: _at(b, "coherence_cells", 7, "r2", 1.5)),
    ("r2 and r2_q lie in [0, 1] and phase in (-pi, pi]", lambda b: _at(b, "coherence_cells", 7, "r2_q", -0.1)),
    ("r2 and r2_q lie in [0, 1] and phase in (-pi, pi]", lambda b: _at(b, "coherence_cells", 7, "phase", -np.pi)),
    ("in_coi is the wavelet stage's cone", lambda b: _with(b, "coherence_cells", in_coi=True)),
    ("significant equals in_coi and r2 > r2_q", lambda b: _with(b, "coherence_cells", significant=~b["coherence_cells"]["significant"])),
    ("significant equals in_coi and r2 > r2_q", lambda b: _with(b, "coherence_cells", significant=b["coherence_cells"]["r2"] > b["coherence_cells"]["r2_q"])),
    (SCOPE_RULE, lambda b: {**b, "coherence_scope": b["coherence_scope"].drop(index=_first(b, band_a=0)).reset_index(drop=True)}),
    (SCOPE_RULE, lambda b: {**b, "coherence_scope": b["coherence_scope"].drop(index=_first(b, band_a=-1)).reset_index(drop=True)}),
    (SCOPE_RULE, lambda b: _at(b, "coherence_scope", _first(b, band_a=0), "j_hi", b["coherence_scope"].loc[_first(b, band_a=0), "j_hi"] + 1)),
    (COUNT_RULE, lambda b: _with(b, "coherence_scope", n_cells=b["coherence_scope"]["n_cells"] + np.int32(1))),
    (COUNT_RULE, lambda b: _at(b, "coherence_scope", 0, "n_significant", b["coherence_scope"].loc[0, "n_significant"] - 1)),
    (MEAN_RULE, lambda b: _at(b, "coherence_scope", 2, "r2_mean", b["coherence_scope"].loc[2, "r2_mean"] * 1.001)),
    (MEAN_RULE, lambda b: _at(b, "coherence_scope", 2, "r2_mean", np.nan)),
    (P_RULE, lambda b: _at(b, "coherence_scope", 2, "p_value", b["coherence_scope"].loc[2, "p_value"] + 0.001)),
    (P_RULE, lambda b: _at(b, "coherence_scope", 2, "p_value", 0.0)),
    (P_RULE, lambda b: _with(b, "coherence_scope", n_surrogates=np.int32(104))),
    (LAG_RULE, lambda b: _at(b, "coherence_scope", _first(b, n_significant=lambda x: x > 0), "lag_months", 99.0)),
    (LAG_RULE, lambda b: _at(b, "coherence_scope", _first(b, n_significant=lambda x: x > 0), "phase", np.nan)),
    (LAG_RULE, lambda b: _with(b, "coherence_scope", period=1.0, lag_months=b["coherence_scope"]["phase"] / (2 * np.pi))),
    (LAG_RULE, lambda b: _with(b, "coherence_scope", phase=b["coherence_scope"]["phase"] + 7.0, lag_months=(b["coherence_scope"]["phase"] + 7.0) * b["coherence_scope"]["period"] / (2 * np.pi))),
])
def test_check_rules_fire_with_rows(delayed, cfg, rule, corrupt):
    _, frames, wav, spec, built, _ = delayed
    coherence.check(built, frames, wav, spec, cfg)  # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        coherence.check(corrupt(built), frames, wav, spec, cfg)
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_check_counts_rows(delayed, cfg):
    _, frames, wav, spec, built, _ = delayed
    with pytest.raises(AcceptanceError, match="coherence_cells has"):
        coherence.check({**built, "coherence_cells": built["coherence_cells"].iloc[1:].reset_index(drop=True)}, frames, wav, spec, cfg)


def test_the_transform_must_be_the_one_the_wavelet_stage_wrote(delayed, cfg):
    _, frames, wav, spec, _, _ = delayed
    cw = wav["wavelet_cwt"].copy()
    cw.loc[5, "w_re"] += 1e-9
    with pytest.raises(AcceptanceError, match="not the one in wavelet_cwt"):
        coherence.run(frames, {**wav, "wavelet_cwt": cw}, spec, cfg)


def test_rows_too_short_for_any_shift_are_refused_and_too_few_shifts_set_no_level(cfg, rng):
    with pytest.raises(AcceptanceError, match="no circular shift exists"):
        staged(rng.standard_normal((1, 2, 23)), cfg)
    *_, b, info = staged(rng.standard_normal((1, 2, 40)), cfg)                  # 17 shifts: none of them is a 5% level
    assert (info["surrogates"]["n"], info["surrogates"]["rank"]) == (17, 0)
    ce, sp = b["coherence_cells"], b["coherence_scope"]
    assert (ce["r2_q"] == 1.0).all() and not ce["significant"].any()
    assert sp["p_value"].notna().all() and sp["lag_months"].isna().all() and (sp["n_significant"] == 0).all()


def test_artifacts_round_trip_with_and_without_rows(tmp_path, delayed, cfg, rng):
    built = delayed[4]
    empty = staged(rng.standard_normal((2, 1, 60)), cfg)[3]                    # one series: no pair
    assert len(empty["coherence_cells"]) == 0 and len(empty["coherence_scope"]) == 0
    for tag, frames in (("delayed", built), ("empty", empty)):
        for name, f in frames.items():
            back = contracts.read(contracts.write(f, name, tmp_path / f"{tag}_{name}.parquet"), name)
            pd.testing.assert_frame_equal(back, f)


@pytest.mark.parametrize("key, value, match", [
    ("coherence.quantile", 1.0, "strictly between 0 and 1"),
    ("coherence.quantile", 0.0, "strictly between 0 and 1"),
    ("coherence.scale_smoothing_width", -0.1, "< 0"),
    ("coherence.time_smoothing", "boxcar", "not in"),
    ("surrogates.n_coherence", 0, "< 1"),
])
def test_coherence_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


# ---- on built grids -----------------------------------------------------------------------------

def test_three_series_grid(cfg):
    frames = three_series_grid()
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    wav, _ = wavelet.run(frames, cfg)
    spec, _ = spectral.run(frames, wav, cfg)
    built, info = coherence.run(frames, wav, spec, cfg)
    J = len(wav["wavelet_scale"])
    ce, sp = built["coherence_cells"], built["coherence_scope"]
    assert info["pairs_per_configuration"] == 3 and len(ce) == K * 3 * J * P
    assert (sp["band_a"] == -1).sum() == K * 3 and (sp["n_surrogates"] == P - 24 + 1).all()
    assert sp["p_value"].between(1 / (P - 22), 1).all() and (ce["i_a"] < ce["i_b"]).all()
    assert info["cells"] == {"all": len(ce), "in_cone": int(ce["in_coi"].sum()), "significant": int(ce["significant"].sum())}


def test_one_series_fixture_build_writes_empty_tables(cfg):
    out, m = fixture_build()
    assert m["stages_passed"].index("coherence") == m["stages_passed"].index("spectral") + 1
    rows = {rel: a["rows"] for rel, a in m["artifacts"].items() if rel.startswith("coherence/")}
    assert rows == {"coherence/cells.parquet": 0, "coherence/scope.parquet": 0}
    assert m["coherence"]["pairs_per_configuration"] == 0 and m["coherence"]["surrogates"] is None
    for name in ("cells", "scope"):
        assert len(contracts.read(out / f"coherence/{name}.parquet", f"coherence_{name}")) == 0
