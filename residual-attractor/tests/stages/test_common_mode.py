"""Common mode: rdiag's Stage 3 common_mode under v2, inside each configuration."""

import re

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.common import linalg, surrogates
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, common_mode


def grid_of(R, start="2015-01-01"):
    """The grid tables a stage on the archive reads, for a field R[k, i, t]."""
    K, N, P = R.shape
    months = pd.date_range(start, periods=P, freq="MS").to_numpy()
    kk, ii, pp = (a.reshape(-1) for a in np.meshgrid(np.arange(K), np.arange(N), np.arange(P), indexing="ij"))
    return {
        "grid_resid": contracts.from_columns({"k": kk, "i": ii, "t": months[pp], "resid": np.asarray(R, dtype=np.float64).reshape(-1)}, "grid_resid"),
        "grid_config": contracts.from_columns({"k": np.arange(K), "core_spec_id": [f"core{k}" for k in range(K)], "exog_set": [[] for _ in range(K)]}, "grid_config"),
        "grid_series": contracts.from_columns({"i": np.arange(N)}, "grid_series"),
        "grid_month": contracts.from_columns({"t": months}, "grid_month"),
    }


def cubes(built, frames):
    """Every column as an array over (k, month) or (k, month, rank or series)."""
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    mo = built["common_mode_month"].sort_values(["k", "t"])
    out = {c: mo[c].to_numpy().reshape(K, P) for c in mo.columns if c not in ("k", "t")}
    out["eigenvalue"] = built["common_mode_eigen"].sort_values(["k", "t", "r"])["eigenvalue"].to_numpy().reshape(K, P, N)
    out["loading"] = built["common_mode_vector"].sort_values(["k", "t", "i"])["loading"].to_numpy().reshape(K, P, N)
    return out


def run(R, cfg, **over):
    frames = grid_of(R)
    built, info = common_mode.run(frames, {**cfg, **over})
    return frames, built, info, cubes(built, frames)


DRAWS = "surrogates.n_common_mode"
WINDOW = "common_mode.window"


# ---- the pieces --------------------------------------------------------------------------------

def test_top_count_reads_the_fraction_as_the_decimal_it_states():
    assert [common_mode.top_count(n, 0.2) for n in (1, 4, 5, 6, 14, 15)] == [1, 1, 1, 2, 3, 3]   # top ceil(N / 5)
    assert int(np.ceil(100 * 0.07)) == 8 and common_mode.top_count(100, 0.07) == 7                 # binary 0.07 x 100 is 7.000000000000001
    assert common_mode.top_count(3, 1.0) == 3 and common_mode.top_count(3, 1) == 3 and common_mode.top_count(10, 0.3) == 3


def test_unit_windows_are_the_rows_trailing_windows_and_wrap_before_them(rng):
    X, w = rng.standard_normal((3, 30)), 7
    X[1, 10:20] = 0.3                                    # ten equal months: the windows inside them are flat
    Z, flat = common_mode.unit_windows(X, w)
    assert Z.shape == (3, 30, 7) and flat.shape == (3, 30)
    for i, s in ((0, 6), (0, 29), (2, 13), (0, 0), (2, 3), (1, 9), (1, 22)):
        win = X[i, np.arange(s - w + 1, s + 1) % 30]     # months s - 6 .. s, wrapping below 0
        z = (win - win.mean()) / np.sqrt(((win - win.mean()) ** 2).sum())
        np.testing.assert_allclose(Z[i, s], z, atol=1e-15)
        assert not flat[i, s]
    assert flat[1].nonzero()[0].tolist() == [16, 17, 18, 19] and not flat[[0, 2]].any() and (Z[1, 16:20] == 0).all()
    # the dot product of two rows' unit windows is their Pearson correlation over those windows
    assert Z[0, 12] @ Z[2, 12] == pytest.approx(np.corrcoef(X[0, 6:13], X[2, 6:13])[0, 1], abs=1e-14)


# ---- exact answers -----------------------------------------------------------------------------

def test_two_series_give_one_plus_and_minus_the_correlation(cfg, rng):
    R = rng.standard_normal((2, 2, 40))
    R[0, 1] = R[0, 0] + 0.5 * rng.standard_normal(40)    # configuration 0: the two rows move together
    R[1, 1] = -R[1, 0] + 0.5 * rng.standard_normal(40)   # configuration 1: they move against each other
    _, _, info, c = run(R, cfg, **{DRAWS: 30})
    w = cfg[WINDOW]
    assert info["absorption"]["top_count"] == 1 and info["mp_edge"]["value"] == (1 + np.sqrt(2 / w)) ** 2
    for k in range(2):
        for t in range(w - 1, 40):
            r = np.corrcoef(R[k, 0, t - w + 1 : t + 1], R[k, 1, t - w + 1 : t + 1])[0, 1]
            np.testing.assert_allclose(c["eigenvalue"][k, t], [1 + abs(r), 1 - abs(r)], atol=1e-13)
            assert c["lambda1"][k, t] == c["eigenvalue"][k, t, 0] and c["absorption_ratio"][k, t] == pytest.approx((1 + abs(r)) / 2, abs=1e-13)
            # (1, 1) / sqrt(2) when they move together; (1, -1) / sqrt(2), sum 0 and first entry positive, when against
            np.testing.assert_allclose(c["loading"][k, t], np.array([1.0, np.sign(r)]) / np.sqrt(2), atol=1e-12)
    assert (c["loading"][1, w - 1 :, 1] < 0).all() and (c["loading"][0, w - 1 :] > 0).all()


def test_values_match_a_direct_recomputation_from_the_shared_surrogates(cfg, rng):
    K, N, P, B = 3, 5, 64, 80
    R = rng.standard_normal((K, N, P)) + 0.6 * rng.standard_normal((K, 1, P))
    _, _, _, c = run(R, cfg, **{DRAWS: B})
    w, q = cfg[WINDOW], cfg["common_mode.quantile"]
    for k, t in ((0, w - 1), (1, 40), (2, P - 1)):
        C = np.corrcoef(R[k, :, t - w + 1 : t + 1])
        vals, vecs = np.linalg.eigh(C)
        np.testing.assert_allclose(c["eigenvalue"][k, t], vals[::-1], atol=1e-12)
        v = vecs[:, -1] * np.sign(vecs[:, -1].sum())
        np.testing.assert_allclose(c["loading"][k, t], v, atol=1e-10)
        assert c["absorption_ratio"][k, t] == pytest.approx(vals[-1] / N, abs=1e-12)   # top ceil(5 x 0.2) = 1
        # purpose "common_mode", unit (i,): every row of configuration k is shifted by its own offset in each draw
        off = np.stack([surrogates.offsets(cfg, "common_mode", P, B, k, i) for i in range(N)])
        lam = np.empty(B)
        for b in range(B):
            S = np.stack([surrogates.shift(R[k, i], off[i, b]) for i in range(N)])
            lam[b] = np.linalg.eigvalsh(np.corrcoef(S[:, t - w + 1 : t + 1]))[-1]
        assert c["lambda1_q"][k, t] == pytest.approx(np.quantile(lam, q), abs=1e-12)
        assert c["p_value"][k, t] == (1 + (lam >= vals[-1]).sum()) / (1 + B) and c["n_surrogates"][k, t] == B
    v0, v1 = c["loading"][1, 39], c["loading"][1, 40]
    assert c["vector_turnover"][1, 40] == pytest.approx(np.arccos(np.clip(v0 @ v1, -1, 1)), abs=1e-7)


def test_a_draw_that_reproduces_the_windows_ties_with_them(cfg, rng):
    # P = twice the minimum offset leaves one offset, P / 2; rows of period P / 2 are their own shift.
    m = cfg["surrogates.circular_shift_min_offset"]
    R = np.tile(rng.standard_normal((2, 4, m)), (1, 1, 2))
    _, _, info, c = run(R, cfg, **{DRAWS: 25, WINDOW: m})
    d = np.isfinite(c["lambda1"])
    assert info["surrogates"]["offsets_per_row"] == 1 and d.sum() == 2 * (m + 1)
    assert (c["p_value"][d] == 1.0).all()                      # ">=": every draw counts, (1 + B) / (1 + B)
    np.testing.assert_array_equal(c["lambda1_q"][d], c["lambda1"][d])


# ---- known answers -----------------------------------------------------------------------------

def test_every_per_month_value_is_null_before_the_first_full_window(cfg, rng):
    K, N, P = 2, 4, 50
    frames, built, info, c = run(rng.standard_normal((K, N, P)), cfg, **{DRAWS: 20})
    w = cfg[WINDOW]
    assert [len(built[x]) for x in ("common_mode_month", "common_mode_eigen", "common_mode_vector")] == [K * P, K * P * N, K * P * N]
    for col in ("lambda1", "lambda1_q", "p_value", "absorption_ratio", "vector_turnover", "eigenvalue", "loading"):
        assert np.isnan(c[col][:, : w - 1]).all(), col
        first = w if col == "vector_turnover" else w - 1   # a turnover needs the month before as well
        assert np.isfinite(c[col][:, first:]).all() and np.isnan(c[col][:, w - 1 : first]).all(), col
    assert (c["n_surrogates"][:, : w - 1] == 0).all() and (c["n_surrogates"][:, w - 1 :] == 20).all()
    assert info["months_with_a_full_window"] == P - w + 1 and np.isfinite(c["mp_edge"]).all()


def test_independent_rows_leave_the_band_at_about_the_nominal_rate(cfg):
    K, N, P = 30, 8, 120
    _, _, _, c = run(np.random.default_rng(1).standard_normal((K, N, P)), cfg, **{DRAWS: 200})
    d = np.isfinite(c["lambda1"])
    np.testing.assert_allclose(c["eigenvalue"][d].sum(axis=1), N, atol=1e-10)      # the trace, at every defined month
    assert (np.diff(c["eigenvalue"][d], axis=1) <= 0).all()
    np.testing.assert_allclose((c["loading"][d] ** 2).sum(axis=1), 1.0, atol=1e-10)
    assert (c["loading"][d].sum(axis=1) >= 0).all()
    above = (c["lambda1"][d] > c["lambda1_q"][d]).mean()
    assert 0.02 <= above <= 0.10, above                                            # the band is the 0.95 quantile: about 5%
    p = c["p_value"][d]
    assert 0.02 <= (p < 0.05).mean() <= 0.10 and p.min() >= 1 / 201 and p.max() <= 1
    assert 0.35 <= p.mean() <= 0.65                                                # no pile-up at either end


def test_autocorrelated_rows_pass_the_marchenko_pastur_edge_but_not_the_band(cfg):
    # Independent AR(1) rows, phi = 0.9: nothing is shared, yet windows of persistent rows correlate by chance.
    K, N, P, burn = 30, 8, 120, 200
    e = np.random.default_rng(1).standard_normal((K, N, P + burn))
    x = np.zeros_like(e)
    for t in range(1, P + burn):
        x[:, :, t] = 0.9 * x[:, :, t - 1] + e[:, :, t]
    _, _, _, c = run(x[:, :, burn:], cfg, **{DRAWS: 200})
    d = np.isfinite(c["lambda1"])
    assert (c["lambda1"][d] > c["mp_edge"][d]).mean() > 0.9        # the white-noise edge calls nearly every month a common mode
    assert (c["lambda1"][d] > c["lambda1_q"][d]).mean() < 0.12     # the surrogates keep each row's persistence: about nominal
    assert np.median(c["lambda1_q"][d]) > c["mp_edge"][d][0] + 1


def test_a_common_factor_switched_on_mid_sample(cfg):
    K, N, P, T0, rho = 3, 10, 144, 72, 0.7
    planted = np.array([1, 3, 4, 6, 8, 9])
    rng = np.random.default_rng(1)
    R = rng.standard_normal((K, N, P))
    f = rng.standard_normal((K, 1, P))
    R[:, planted, T0:] = np.sqrt(rho) * f[:, :, T0:] + np.sqrt(1 - rho) * R[:, planted, T0:]
    _, _, info, c = run(R, cfg, **{DRAWS: 200})
    w, others = cfg[WINDOW], np.setdiff1d(np.arange(N), planted)
    before, inside = slice(w - 1, T0), slice(T0 + w - 1, P)        # windows wholly before the factor, wholly inside it
    target = 1 + (planted.size - 1) * rho                           # 4.5
    assert info["absorption"]["top_count"] == 2
    for k in range(K):
        assert c["lambda1"][k, inside].mean() == pytest.approx(target, rel=0.10)
        assert c["lambda1"][k, before].mean() < 0.6 * target
        V = c["loading"][k, inside]
        assert (V[:, planted] > 0.2).all() and np.abs(V[:, others]).max() < V[:, planted].min()
        assert (V[:, planted] ** 2).sum(axis=1).min() > 0.85       # the vector sits on the planted series
        assert c["absorption_ratio"][k, inside].min() > c["absorption_ratio"][k, before].max()
        assert (c["p_value"][k, inside] == 1 / 201).all()          # no surrogate reaches it: the smallest p there is
        assert (c["lambda1"][k, inside] > c["lambda1_q"][k, inside]).all()
    assert (c["lambda1"][:, before] > c["lambda1_q"][:, before]).mean() < 0.15


def _disjoint_blocks(P, a):
    """Four rows in two blocks that never meet: rows 0-1 live on even months, rows 2-3 on odd months.

    Each row is built from zero-mean patterns of period 4 and 8, so over any 24 months rows 2 and 3
    correlate at exactly 0.5, and rows 0 and 1 at a[t] where a is constant. The cross-block
    correlations are exactly 0 in every window, so the leading vector is (1, 1, 0, 0) / sqrt(2) or
    (0, 0, 1, 1) / sqrt(2): whichever block is more tightly bound.
    """
    t = np.arange(P)
    u1, u2 = np.array([1.0, 0, -1, 0])[t % 4], np.array([1.0, 0, 1, 0, -1, 0, -1, 0])[t % 8]
    v1, v2 = np.array([0, 1.0, 0, -1])[t % 4], np.array([0, 1.0, 0, 1, 0, -1, 0, -1])[t % 8]
    return np.stack([u1, a * u1 + np.sqrt(1 - a**2) * u2, v1, 0.5 * v1 + np.sqrt(0.75) * v2])


def test_turnover_is_zero_for_a_fixed_structure_and_a_right_angle_when_the_mode_moves(cfg):
    P, T1 = 96, 48
    fixed = _disjoint_blocks(P, np.full(P, 0.9))
    moving = _disjoint_blocks(P, np.where(np.arange(P) < T1, 0.9, 0.1))   # the first block comes apart at T1
    _, _, _, c = run(np.stack([fixed, moving]), cfg, **{DRAWS: 20})
    w = cfg[WINDOW]
    A, B = np.array([1, 1, 0, 0]) / np.sqrt(2), np.array([0, 0, 1, 1]) / np.sqrt(2)
    assert np.abs(c["vector_turnover"][0, w:]).max() < 1e-9 and np.abs(c["loading"][0, w - 1 :] - A).max() < 1e-12
    np.testing.assert_allclose(c["lambda1"][0, w - 1 :], 1.9, atol=1e-12)
    turn = c["vector_turnover"][1, w:]
    jump = int(np.argmax(turn)) + w
    assert T1 < jump < T1 + w                                              # while the window slides across T1
    assert turn.max() == pytest.approx(np.pi / 2, abs=1e-9) and np.sort(turn)[-2] < 1e-9   # one month turns 90 degrees, no other turns
    assert np.abs(c["loading"][1, w - 1 : jump] - A).max() < 1e-9 and np.abs(c["loading"][1, jump:] - B).max() < 1e-9
    assert (c["lambda1"][1, jump:] == pytest.approx(1.5, abs=1e-12))


def test_a_factor_moving_to_other_series_ends_at_a_right_angle(cfg):
    # The same move on noisy data: the window blends the two regimes for a while, so no single month turns 90 degrees.
    K, N, P, T1, rho = 2, 8, 144, 72, 0.8
    rng = np.random.default_rng(1)
    R, f = rng.standard_normal((K, N, P)), rng.standard_normal((K, 1, P))
    R[:, :4, :T1] = np.sqrt(rho) * f[:, :, :T1] + np.sqrt(1 - rho) * R[:, :4, :T1]
    R[:, 4:, T1:] = np.sqrt(rho) * f[:, :, T1:] + np.sqrt(1 - rho) * R[:, 4:, T1:]
    _, _, _, c = run(R, cfg, **{DRAWS: 20})
    w = cfg[WINDOW]
    for k in range(K):
        start, end = c["loading"][k, T1 - 1], c["loading"][k, T1 + w - 1]
        assert linalg.angle(start, end) == pytest.approx(np.pi / 2, abs=0.2)
        assert (start[:4] ** 2).sum() > 0.8 and (end[4:] ** 2).sum() > 0.8   # on the first four series, then on the other four
        settled = np.r_[c["vector_turnover"][k, w : T1], c["vector_turnover"][k, T1 + w :]]
        assert np.median(settled) < 0.1 and np.nanmax(c["vector_turnover"][k, T1 : T1 + w]) > 4 * np.median(settled)


# ---- the archive rule and the counts -----------------------------------------------------------

def _same(a: pd.DataFrame, b: pd.DataFrame):
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_exact=True)


def test_changing_one_configuration_leaves_every_other_row_bit_identical(cfg, rng):
    K, N, P = 4, 6, 60
    R = rng.standard_normal((K, N, P)) + 0.5 * rng.standard_normal((K, 1, P))
    _, base, _, _ = run(R, cfg, **{DRAWS: 60})
    R2 = R.copy()
    R2[2] = 3.0 * rng.standard_normal((N, P)) + rng.standard_normal((1, P))
    _, other, _, _ = run(R2, cfg, **{DRAWS: 60})
    for name in base:
        _same(base[name][base[name]["k"] != 2], other[name][other[name]["k"] != 2])
        assert not base[name][base[name]["k"] == 2].equals(other[name][other[name]["k"] == 2])


def test_adding_a_configuration_changes_no_other_configurations_rows(cfg, rng):
    R = rng.standard_normal((4, 5, 60))
    _, three, _, _ = run(R[:3], cfg, **{DRAWS: 60})
    _, four, _, _ = run(R, cfg, **{DRAWS: 60})
    for name in three:
        _same(three[name], four[name][four[name]["k"] < 3])


def test_what_a_configurations_index_decides(cfg, rng):
    # The index k enters only the surrogate draws, and only when configurations keep their own (surrogates.scope).
    R = rng.standard_normal((3, 5, 60)) + 0.4 * rng.standard_normal((3, 1, 60))
    swap = [2, 0, 1]
    for scope, band_moves in (("shared", False), ("per_configuration", True)):
        _, _, _, a = run(R, cfg, **{DRAWS: 60, "surrogates.scope": scope})
        _, _, _, b = run(R[swap], cfg, **{DRAWS: 60, "surrogates.scope": scope})
        for col in ("lambda1", "absorption_ratio", "vector_turnover", "eigenvalue", "loading"):
            np.testing.assert_array_equal(a[col][swap], b[col])
        assert np.array_equal(a["lambda1_q"][swap], b["lambda1_q"], equal_nan=True) != band_moves
        assert np.array_equal(a["p_value"][swap], b["p_value"], equal_nan=True) != band_moves


def test_the_spectrum_does_not_depend_on_the_order_of_the_series(cfg, rng):
    R = rng.standard_normal((2, 6, 60)) + 0.5 * rng.standard_normal((2, 1, 60))
    order = np.array([3, 0, 5, 1, 4, 2])
    _, _, _, a = run(R, cfg, **{DRAWS: 20})
    _, _, _, b = run(R[:, order], cfg, **{DRAWS: 20})
    for col in ("lambda1", "absorption_ratio", "vector_turnover", "eigenvalue"):
        np.testing.assert_allclose(a[col], b[col], atol=1e-10)
    np.testing.assert_allclose(a["loading"][:, :, order], b["loading"], atol=1e-8)


# ---- where nothing is defined ------------------------------------------------------------------

def test_one_series_gives_valid_null_rows(cfg, rng):
    K, P = 3, 60
    frames, built, info, c = run(rng.standard_normal((K, 1, P)), cfg)
    assert [len(built[x]) for x in built] == [K * P, K * P, K * P] and info["undefined"]["fewer_than_two_series"]
    for col in ("lambda1", "lambda1_q", "p_value", "absorption_ratio", "vector_turnover", "eigenvalue", "loading"):
        assert np.isnan(c[col]).all()
    assert (c["n_surrogates"] == 0).all() and (c["mp_edge"] == (1 + np.sqrt(1 / cfg[WINDOW])) ** 2).all()
    common_mode.check(built, frames, cfg)


def test_a_grid_shorter_than_the_window_gives_null_rows(cfg, rng):
    w = cfg[WINDOW]
    _, built, info, c = run(rng.standard_normal((2, 4, w - 1)), cfg)
    assert np.isnan(c["lambda1"]).all() and np.isnan(c["loading"]).all() and info["undefined"]["no_full_window"]
    _, _, _, c = run(rng.standard_normal((2, 4, w)), cfg, **{DRAWS: 10})   # one full window: one defined month
    assert np.isfinite(c["lambda1"]).sum(axis=1).tolist() == [1, 1] and np.isnan(c["vector_turnover"]).all()
    assert np.isfinite(c["lambda1_q"][:, -1]).all()


def test_a_flat_row_has_no_correlation(cfg, rng):
    K, N, P, B = 2, 4, 80, 100
    w = cfg[WINDOW]
    R = rng.standard_normal((K, N, P))
    R[1, 2, 30 : 30 + w + 5] = 0.1          # row 2 of configuration 1 stands still for w + 5 months
    frames, built, info, c = run(R, cfg, **{DRAWS: B})
    flat_months = np.arange(30 + w - 1, 30 + w + 5)
    for col in ("lambda1", "lambda1_q", "p_value", "absorption_ratio", "eigenvalue", "loading"):
        assert np.isnan(c[col][1, flat_months]).all() and np.isfinite(np.delete(c[col][1, w - 1 :], flat_months - (w - 1), axis=0)).all(), col
        assert np.isfinite(c[col][0, w - 1 :]).all()
    assert np.isnan(c["vector_turnover"][1, flat_months[0] : flat_months[-1] + 2]).all()   # and the month after them
    assert np.isfinite(c["vector_turnover"][1, flat_months[-1] + 2 :]).all()
    # a draw that moves the flat stretch into the window is left out of that month's band and p-value
    n = c["n_surrogates"][1]
    assert (n[flat_months] == 0).all() and (n[w - 1 :].max() == B) and 0 < np.delete(n[w - 1 :], flat_months - (w - 1)).min() < B
    assert (c["n_surrogates"][0, w - 1 :] == B).all()
    assert info["undefined"]["months_with_a_flat_row"] == flat_months.size and info["undefined"]["surrogate_draws_left_out_for_a_flat_row"] > 0
    k, t = 1, int(np.argmin(np.where(n > 0, n, B + 1)))
    off = np.stack([surrogates.offsets(cfg, "common_mode", P, B, k, i) for i in range(N)])
    lam = []
    for b in range(B):
        S = np.stack([surrogates.shift(R[k, i], off[i, b]) for i in range(N)])[:, t - w + 1 : t + 1]
        if (S.max(axis=1) > S.min(axis=1)).all():
            lam.append(np.linalg.eigvalsh(np.corrcoef(S))[-1])
    assert n[t] == len(lam) < B and c["lambda1_q"][k, t] == pytest.approx(np.quantile(lam, cfg["common_mode.quantile"]), abs=1e-12)
    assert c["p_value"][k, t] == (1 + (np.array(lam) >= c["lambda1"][k, t]).sum()) / (1 + len(lam))


def test_a_grid_with_no_circular_shift_stops_with_the_purpose_named(cfg, rng):
    m = cfg["surrogates.circular_shift_min_offset"]
    with pytest.raises(AcceptanceError, match="common_mode: no circular shift exists"):
        run(rng.standard_normal((2, 3, 2 * m - 1)), cfg, **{WINDOW: 2 * m - 4})


# ---- acceptance --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clean(cfg):
    small = {**cfg, DRAWS: 40}
    R = np.random.default_rng(7).standard_normal((3, 5, 48)) + 0.5 * np.random.default_rng(8).standard_normal((3, 1, 48))
    frames = grid_of(R)
    built, _ = common_mode.run(frames, small)
    return frames, built, small


def _month(b, **cols):
    return {**b, "common_mode_month": b["common_mode_month"].assign(**cols)}


def _swap_ranks(b):
    e = b["common_mode_eigen"]
    return {**b, "common_mode_eigen": e.assign(eigenvalue=e.sort_values(["k", "t", "r"], ascending=[True, True, False])["eigenvalue"].to_numpy())}


def _move_mass(b):
    e = b["common_mode_eigen"]
    return {**b, "common_mode_eigen": e.assign(eigenvalue=e["eigenvalue"] + np.where(e["r"] == 0, 1e-6, np.where(e["r"] == 1, -1e-6, 0.0)))}


def _roll_series(b):
    v = b["common_mode_vector"]
    return {**b, "common_mode_vector": v.assign(loading=v.groupby(["k", "t"])["loading"].transform(lambda s: np.roll(s.to_numpy(), 1)))}


@pytest.mark.parametrize("rule, corrupt", [
    ("every per-month value is null before the first full window", lambda b: _month(b, absorption_ratio=b["common_mode_month"]["absorption_ratio"].fillna(0.5))),
    ("lambda1 is the leading eigenvalue of the configuration's own trailing-window correlation", lambda b: _month(b, lambda1=b["common_mode_month"]["lambda1"] * 1.0001)),
    ("1 <= lambda1 <= N", lambda b: _month(b, lambda1=b["common_mode_month"]["lambda1"] + 5.0)),
    ("0 <= n_surrogates <= surrogates.n_common_mode", lambda b: _month(b, n_surrogates=np.int32(41))),
    ("lambda1_q and p_value are null exactly where no surrogate was counted", lambda b: _month(b, p_value=b["common_mode_month"]["p_value"].fillna(0.5))),
    ("p_value is a count from 1 to 1 + n_surrogates over 1 + n_surrogates", lambda b: _month(b, p_value=b["common_mode_month"]["p_value"] * 0.999)),
    ("p_value is a count from 1 to 1 + n_surrogates over 1 + n_surrogates", lambda b: _month(b, p_value=b["common_mode_month"]["p_value"] * 0.0)),
    ("1 <= lambda1_q <= N", lambda b: _month(b, lambda1_q=b["common_mode_month"]["lambda1_q"] * 0.1)),
    ("mp_edge equals (1 + sqrt(N / window))^2", lambda b: _month(b, mp_edge=b["common_mode_month"]["mp_edge"] + 1e-6)),
    ("absorption_ratio is the top ceil(N x fraction) eigenvalues over N", lambda b: _month(b, absorption_ratio=b["common_mode_month"]["absorption_ratio"] * 1.001)),
    ("vector_turnover is the angle in [0, pi] between the leading vectors at t and t - 1", lambda b: _month(b, vector_turnover=b["common_mode_month"]["vector_turnover"] + 1e-6)),
    ("vector_turnover is the angle in [0, pi] between the leading vectors at t and t - 1", lambda b: _month(b, vector_turnover=b["common_mode_month"]["vector_turnover"].fillna(0.0))),
    ("N eigenvalues per month, summing to N where defined", lambda b: {**b, "common_mode_eigen": b["common_mode_eigen"].assign(eigenvalue=b["common_mode_eigen"]["eigenvalue"] * 1.001)}),
    ("eigenvalues descend with the rank r", _swap_ranks),
    ("the eigenvalue at r = 0 is lambda1", _move_mass),
    ("the leading vector has unit length and a sum >= 0", lambda b: {**b, "common_mode_vector": b["common_mode_vector"].assign(loading=-b["common_mode_vector"]["loading"])}),
    ("the leading vector has unit length and a sum >= 0", lambda b: {**b, "common_mode_vector": b["common_mode_vector"].assign(loading=b["common_mode_vector"]["loading"] * 1.001)}),
    ("the leading vector is an eigenvector of lambda1", _roll_series),
])
def test_check_rules_fire_with_rows(clean, rule, corrupt):
    frames, built, small = clean
    common_mode.check(built, frames, small)  # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        common_mode.check(corrupt(built), frames, small)
    rows = err.value.rows
    assert rows is not None and rows["problem"].str.contains(rule, regex=False).any() and {"k", "t", "artifact"} <= set(rows.columns)


def test_check_counts_the_rows(clean):
    frames, built, small = clean
    for name in built:
        with pytest.raises(AcceptanceError, match=f"{name} has"):
            common_mode.check({**built, name: built[name].iloc[1:]}, frames, small)


def test_check_ties_the_values_to_the_grid(clean):
    # The same tables against a grid whose residuals moved: lambda1 no longer belongs to it.
    frames, built, small = clean
    r = frames["grid_resid"]
    moved = {**frames, "grid_resid": r.assign(resid=np.where(r["k"] == 1, r["resid"].to_numpy()[::-1], r["resid"]))}
    with pytest.raises(AcceptanceError, match="lambda1 is the leading eigenvalue") as err:
        common_mode.check(built, moved, small)
    assert set(err.value.rows["k"]) == {1}   # only the configuration that moved


def test_artifacts_round_trip(tmp_path, clean):
    _, built, _ = clean
    for name, f in built.items():
        _same(contracts.read(contracts.write(f, name, tmp_path / f"{name}.parquet"), name), f)


@pytest.mark.parametrize("key, value, match", [
    ("common_mode.absorption_top_fraction", 0.0, "absorption_top_fraction"),
    ("common_mode.absorption_top_fraction", 1.5, "absorption_top_fraction"),
    ("common_mode.quantile", 1.0, "common_mode.quantile"),
    ("common_mode.quantile", 0.0, "common_mode.quantile"),
    ("common_mode.window", 1, "common_mode.window"),
    ("surrogates.n_common_mode", 0, "n_common_mode"),
])
def test_common_mode_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


# ---- the stage on a built grid -----------------------------------------------------------------

@pytest.fixture(scope="module")
def staged(cfg):
    """Three series through register, fit and the grid, then this stage: every registered configuration."""
    from tests.stages.test_grid import three_series
    from rattractor.stages import fibers, fit, grid, register

    series, calendar = three_series(cfg)
    reg = register.run(cfg)
    states, _ = fit.run(series, reg, cfg)
    coords = list(fibers.fiber_index(reg, cfg)["config_id"])
    months, t_of = grid.holdout(series, calendar)
    Z, ids = [], []
    for n, (sid, g) in enumerate(series.groupby("series_id", sort=False, observed=True)):
        Z.append(grid.series_rows(str(sid), n, g, states, coords, t_of[str(sid)], cfg))
        ids.append(str(sid))
    frames = grid.assemble(Z, ids, reg, coords, months, t_of, calendar, cfg, "test:v1", "build-x")
    small = {**cfg, DRAWS: 40}
    built, info = common_mode.run(frames, small)
    return frames, built, info, small


def test_the_stage_on_a_three_series_grid(staged):
    frames, built, info, small = staged
    K, N, P = len(frames["grid_config"]), 3, len(frames["grid_month"])
    w = small[WINDOW]
    mo, ei, ve = (built[x] for x in ("common_mode_month", "common_mode_eigen", "common_mode_vector"))
    assert (len(mo), len(ei), len(ve)) == (K * P, K * P * N, K * P * N) and info["series"] == 3 and info["absorption"]["top_count"] == 1
    assert set(mo["k"]) == set(range(K)) and set(mo["t"]) == set(frames["grid_month"]["t"]) and set(ve["i"]) == {0, 1, 2} and set(ei["r"]) == {0, 1, 2}
    d = mo.dropna(subset=["lambda1"])
    assert len(d) == K * (P - w + 1) and ((d["p_value"] > 0) & (d["p_value"] <= 1)).all() and (d["n_surrogates"] == 40).all()
    assert d["lambda1"].between(1, 3).all() and d["absorption_ratio"].between(1 / 3, 1).all()
    np.testing.assert_allclose(ei.dropna().groupby(["k", "t"])["eigenvalue"].sum(), 3.0, atol=1e-10)
    # one configuration's rows are its own: recompute configuration 17 from its residuals alone
    r = frames["grid_resid"]
    X = r[r["k"] == 17].pivot(index="i", columns="t", values="resid").to_numpy()
    last = np.linalg.eigvalsh(np.corrcoef(X[:, -w:]))[-1]
    assert mo[(mo["k"] == 17)].sort_values("t")["lambda1"].iloc[-1] == pytest.approx(last, abs=1e-12)


def test_a_failed_check_stops_the_build_and_writes_its_rows(cfg, tmp_path, monkeypatch):
    from rattractor.build import build
    from rattractor.runspec import load_run_spec

    def fail(frames, cfg):
        raise AcceptanceError("common_mode", "planted failure", pd.DataFrame({"k": [0], "problem": ["planted"]}))

    monkeypatch.setattr(common_mode, "run", fail)
    with pytest.raises(AcceptanceError, match="common_mode: planted failure"):
        build(load_run_spec("fixture_six_regime.yaml"), cfg, tmp_path)
    assert len(list((tmp_path / "reports").glob("*/common_mode.parquet"))) == 1   # filed under this stage's name
    assert not list((tmp_path / "builds").glob("*/manifest.json"))
