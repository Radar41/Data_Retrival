"""Stage 10: rdiag's Stage 1 under v2, configuration against configuration, no fused reference."""

import re

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.config import validate_config
from rattractor.stages import compare


# ---- the long-run variance and the tests on one differential -----------------------------------

def test_hac_lag_rule():
    assert [compare.hac_lag(n) for n in (98, 100, 200, 1000)] == [3, 4, 4, 6]


@pytest.mark.parametrize("n", [98, 99, 100])
def test_long_run_variance_matches_the_bartlett_sum(n):
    rng = np.random.default_rng(1)
    d = rng.normal(size=n)
    q, x = compare.hac_lag(n), d - d.mean()
    want = (x @ x) / n + 2 * sum((1 - j / (q + 1)) * (x[j:] @ x[:-j]) / n for j in range(1, q + 1))
    got, lag = compare.long_run_variance(d[None, :])
    assert lag == q and got[0] == pytest.approx(want, rel=1e-12)


def test_dm_hln_is_dm_times_the_small_sample_factor():
    rng = np.random.default_rng(2)
    d = rng.normal(0.2, 1, (3, 98))
    stat, p, q = compare.dm_hln(d)
    lrv, _ = compare.long_run_variance(d)
    dm = d.mean(1) / np.sqrt(lrv / 98)
    np.testing.assert_allclose(stat, dm * np.sqrt(97 / 98), rtol=1e-12)
    from scipy import stats
    np.testing.assert_allclose(p, 2 * stats.t.sf(np.abs(stat), 97), rtol=1e-12)


def test_dm_hln_size_and_power():
    rng = np.random.default_rng(3)
    _, p0, _ = compare.dm_hln(rng.normal(0, 1, (4000, 98)))
    _, p1, _ = compare.dm_hln(rng.normal(0.5, 1, (4000, 98)))
    assert 0.03 <= (p0 < 0.05).mean() <= 0.08   # close to nominal on iid differentials
    assert (p1 < 0.05).mean() > 0.95
    assert ((p0 > 0) & (p0 <= 1)).all()


def test_clark_west_identity_and_sign():
    rng = np.random.default_rng(4)
    y = rng.normal(size=(1, 200))
    x = rng.normal(size=(1, 200))
    e_small = y.copy()                      # forecast 0
    e_large = y - 0.8 * x                    # a model that uses a useless regressor
    stat, p, _ = compare.clark_west(e_small, e_large)
    f = 2 * e_small * (e_small - e_large)    # the MSPE adjustment, rewritten
    lrv, _ = compare.long_run_variance(f)
    assert stat[0] == pytest.approx(f.mean() / np.sqrt(lrv[0] / 200), rel=1e-12)
    y2 = 0.8 * x + 0.3 * rng.normal(size=(1, 200))   # now the regressor matters
    s2, p2, _ = compare.clark_west(y2, y2 - 0.8 * x)
    assert s2[0] > 3 and p2[0] < 0.01


def test_nesting_selects_clark_west():
    config = contracts.from_columns({"k": [0, 1, 2], "core_spec_id": ["a", "a", "b"],
                                     "exog_set": [[], ["x1"], []]}, "grid_config")
    ka, kb = np.array([0, 0, 1]), np.array([1, 2, 2])
    nested, a_small = compare._nested(config, ka, kb)
    assert nested.tolist() == [True, False, False] and a_small.tolist() == [True, False, False]


# ---- the model confidence set -----------------------------------------------------------------

def mcs_of(L, alpha=0.10, B=2000, seed=5):
    w = compare.stationary_bootstrap_weights(L.shape[1], B, 6.0, np.random.default_rng(seed))
    return compare.mcs(L, alpha, w)


def test_stationary_bootstrap_weights():
    w = compare.stationary_bootstrap_weights(98, 500, 6.0, np.random.default_rng(6))
    np.testing.assert_allclose(w.sum(axis=1), 1.0)
    assert (w >= 0).all() and w.shape == (500, 98)
    # The circular wrap gives every month the same expected weight, the ends included.
    big = compare.stationary_bootstrap_weights(98, 20000, 6.0, np.random.default_rng(7))
    assert np.abs(big.mean(axis=0) * 98 - 1).max() < 0.1


def test_mcs_keeps_the_clearly_best_model_alone():
    rng = np.random.default_rng(7)
    L = rng.chisquare(1, (6, 98))
    L[2] *= 0.2  # model 2 is far better
    p, in_set, elim = mcs_of(L)
    assert in_set.tolist() == [False, False, True, False, False, False]
    assert p[2] == 1.0 and elim[2] == 0 and sorted(elim[elim > 0].tolist()) == [1, 2, 3, 4, 5]


def test_mcs_keeps_indistinguishable_models():
    rng = np.random.default_rng(8)
    p, in_set, _ = mcs_of(rng.chisquare(1, (8, 98)))
    assert in_set.sum() >= 6


def test_mcs_p_values_never_fall_along_the_elimination_order():
    rng = np.random.default_rng(9)
    L = rng.chisquare(1, (10, 98)) * np.linspace(0.6, 1.4, 10)[:, None]
    p, in_set, elim = mcs_of(L)
    out = np.argsort(np.where(elim > 0, elim, 999))
    seq = p[out[: (elim > 0).sum()]]
    assert (np.diff(seq) >= 0).all() and in_set.any() and (p[in_set] >= 0.10).all() and (p[~in_set] < 0.10).all()


# ---- fluctuation ------------------------------------------------------------------------------

def test_fluctuation_critical_value_interpolates_the_table():
    assert compare.fluctuation_critical_value(0.25, 0.05) == pytest.approx((3.179 + 3.012) / 2)
    with pytest.raises(Exception, match="outside"):
        compare.fluctuation_critical_value(0.05, 0.05)


def test_fluctuation_table_agrees_with_simulation():
    # sup over tau in [mu, 1] of |W(tau) - W(tau - mu)| / sqrt(mu), W a Brownian motion.
    rng = np.random.default_rng(10)
    n, sims = 1000, 6000
    W = np.concatenate([np.zeros((sims, 1)), np.cumsum(rng.normal(0, np.sqrt(1 / n), (sims, n)), axis=1)], axis=1)
    for mu in (0.2, 0.5):
        Lw = int(mu * n)
        q = np.quantile(np.abs(W[:, Lw:] - W[:, :-Lw]).max(axis=1) / np.sqrt(mu), 0.95)
        assert q == pytest.approx(compare.fluctuation_critical_value(mu, 0.05), rel=0.04)


def test_fluctuation_path():
    rng = np.random.default_rng(11)
    d = rng.normal(size=(2, 98))
    m = 24
    f = compare.fluctuation(d, m)
    assert np.isnan(f[:, : m - 1]).all() and np.isfinite(f[:, m - 1 :]).all()
    lrv, _ = compare.long_run_variance(d)
    t = 50
    assert f[0, t] == pytest.approx(np.sqrt(m) * d[0, t - m + 1 : t + 1].mean() / np.sqrt(lrv[0]), rel=1e-12)


# ---- conditional predictive ability -----------------------------------------------------------

def test_cpa_size_and_power():
    rng = np.random.default_rng(12)
    _, p0, n = compare.cpa(rng.normal(size=(3000, 98)), ["const", "d_lag1"])
    # With HAC covariance at n ~ 100 the Wald test runs slightly conservative (about 3-4% at 5%).
    assert n == 97 and 0.02 <= (p0 < 0.05).mean() <= 0.08
    e = rng.normal(size=(500, 99))
    d = e[:, 1:] + 0.7 * e[:, :-1]  # mean zero, but predictable from its own lag
    _, p1, _ = compare.cpa(d, ["const", "d_lag1"])
    assert (p1 < 0.05).mean() > 0.6


@pytest.mark.parametrize("P", [98, 101])
def test_cpa_constant_only_is_a_dm_like_test(P):
    rng = np.random.default_rng(13)
    d = rng.normal(0.4, 1, (1, P))
    stat, p, n = compare.cpa(d, ["const"])
    y = d[0, 1:]
    lrv, _ = compare.long_run_variance(y[None])
    # the uncentred Bartlett variance of y differs from the centred one by the squared mean term only
    x, q = y, compare.hac_lag(n)
    unc = (x @ x) / n + 2 * sum((1 - j / (q + 1)) * (x[j:] @ x[:-j]) / n for j in range(1, q + 1))
    assert stat[0] == pytest.approx(n * y.mean() ** 2 / unc, rel=1e-10)


# ---- the stage on a grid ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def staged(cfg):
    from tests.stages.test_grid import three_series
    from rattractor.stages import fibers, fit, forecast, grid, register

    series, calendar = three_series(cfg)
    reg = register.run(cfg)
    states, cache = fit.run(series, reg, cfg)
    index = fibers.fiber_index(reg, cfg)
    coords = list(index["config_id"])
    months, t_of = grid.holdout(series, calendar)
    Z, ids = [], []
    for n, (sid, g) in enumerate(series.groupby("series_id", sort=False, observed=True)):
        Z.append(grid.series_rows(str(sid), n, g, states, coords, t_of[str(sid)], cfg))
        ids.append(str(sid))
    frames = grid.assemble(Z, ids, reg, coords, months, t_of, calendar, cfg, "test:v1", "build-x")
    built, info = compare.run(frames, reg, index, cfg)
    return frames, reg, index, built, info


def test_losses_are_each_configurations_own(staged, cfg):
    frames, _, _, built, _ = staged
    m = built["compare_loss"].merge(frames["grid_resid"], on=["k", "i", "t"])
    np.testing.assert_array_equal(m["loss"].to_numpy(), m["resid"].to_numpy() ** 2)


def test_twins_are_marked_not_tested(staged):
    _, reg, index, built, info = staged
    pw, mc = built["compare_pairwise"], built["compare_mcs"]
    tw = pw[pw["test"] == "twin"]
    assert len(tw) == info["twin_pairs_per_series"] * 3 == 12 and tw["p_value"].isna().all() and tw["statistic"].isna().all()
    groups = {tuple(g) for g in info["twin_groups"]}
    assert {(int(a), int(b)) for a, b in zip(tw["k_a"], tw["k_b"]) if True} == {tuple(sorted(g)) for g in groups}
    for g in info["twin_groups"]:
        rows = mc[mc["k"].isin(g)]
        assert rows.groupby("i")[["mcs_p_value", "in_set", "elimination_order"]].nunique().max().max() == 1
        assert (rows["represented_by"] == min(g)).all()
    fs = built["compare_fluctuation_sup"]
    assert fs.merge(tw[["i", "k_a", "k_b"]])["reject"].isna().all()


def test_a_pairs_results_depend_only_on_its_two_configurations(staged, cfg):
    frames, reg, index, built, _ = staged
    keep = [3, 17, 30]
    sub = {**frames}
    r = frames["grid_resid"]
    sub["grid_resid"] = contracts.validate(r[r["k"].isin(keep)].assign(k=lambda f: f["k"].map({k: j for j, k in enumerate(keep)}).astype(np.int32)).reset_index(drop=True), "grid_resid")
    sub["grid_config"] = contracts.validate(frames["grid_config"][frames["grid_config"]["k"].isin(keep)].assign(k=np.arange(3, dtype=np.int32)).reset_index(drop=True), "grid_config")
    idx = contracts.validate(index[index["k"].isin(keep)].assign(k=np.arange(3, dtype=np.int16)).reset_index(drop=True), "fiber_index")
    small, _ = compare.run(sub, reg, idx, cfg)
    full = built["compare_pairwise"]
    for (a, b) in ((0, 1), (0, 2), (1, 2)):
        x = small["compare_pairwise"].query("k_a == @a and k_b == @b").reset_index(drop=True)
        y = full.query("k_a == @keep[@a] and k_b == @keep[@b]").reset_index(drop=True)
        np.testing.assert_array_equal(x["statistic"], y["statistic"])
        np.testing.assert_array_equal(x["p_value"], y["p_value"])


def test_every_series_has_a_confidence_set_and_valid_p_values(staged):
    *_, built, _ = staged
    pw = built["compare_pairwise"]
    p = pw.loc[pw["test"] != "twin", "p_value"]
    assert ((p > 0) & (p <= 1)).all()
    assert built["compare_mcs"].groupby("i")["in_set"].any().all()
    assert set(built["compare_cpa"]["df"]) == {2} and all(list(x) == ["const", "d_lag1"] for x in built["compare_cpa"]["instruments"])


def _frames_with_twin_rows_identical(frames, info):
    a, b = info["twin_groups"][0][:2]
    r = frames["grid_resid"].copy()
    src = r[r["k"] == a].set_index(["i", "t"])["resid"]
    sel = r["k"] == b
    r.loc[sel, "resid"] = src.loc[pd.MultiIndex.from_frame(r.loc[sel, ["i", "t"]])].to_numpy()
    return {**frames, "grid_resid": contracts.validate(r, "grid_resid")}, a, b


def test_bitwise_identical_twins_do_not_break_the_tests(staged, cfg):
    # Holt(alpha, beta = 0) and SES(alpha) can compute the very same number; d is then exactly 0.
    frames, reg, index, _, info = staged
    same, a, b = _frames_with_twin_rows_identical(frames, info)
    built, _ = compare.run(same, reg, index, cfg)
    for name in ("compare_pairwise", "compare_cpa"):
        rows = built[name].query("k_a == @a and k_b == @b")
        assert rows["statistic"].isna().all() and rows["p_value"].isna().all()
    _, p, _ = compare.cpa(np.vstack([np.zeros(98), np.random.default_rng(0).normal(size=98)]), ["const", "d_lag1"])
    assert np.isnan(p[0]) and 0 < p[1] <= 1


def test_clark_west_runs_on_the_unscaled_errors(staged, cfg):
    frames, reg, index, _, _ = staged
    c = frames["grid_config"].copy()
    c.loc[c["k"] == 9, "core_spec_id"] = c.loc[c["k"] == 8, "core_spec_id"].iloc[0]
    c["exog_set"] = [["x"] if k == 9 else [] for k in c["k"]]
    nested_frames = {**frames, "grid_config": contracts.validate(c, "grid_config")}
    K, N, P = len(c), 3, len(frames["grid_month"])
    raw = np.random.default_rng(14).normal(size=(K, N, P)) * np.linspace(1, 3, K)[:, None, None]
    with pytest.raises(Exception, match="unscaled errors"):
        compare.run(nested_frames, reg, index, cfg)
    built, info = compare.run(nested_frames, reg, index, cfg, raw)
    row = built["compare_pairwise"].query("k_a == 8 and k_b == 9 and i == 1").iloc[0]
    want, pw, _ = compare.clark_west(raw[8:9, 1, :], raw[9:10, 1, :])
    assert row["test"] == "CW" and row["nested"] and info["nested_pairs_per_series"] == 1
    assert row["statistic"] == pytest.approx(want[0], rel=1e-12) and row["p_value"] == pytest.approx(pw[0], rel=1e-12)


@pytest.mark.parametrize("rule, corrupt", [
    ("loss equals L(resid) exactly", lambda b: {**b, "compare_loss": b["compare_loss"].assign(loss=b["compare_loss"]["loss"] * 1.0001)}),
    ("in_set equals mcs_p_value >= alpha", lambda b: {**b, "compare_mcs": b["compare_mcs"].assign(in_set=~b["compare_mcs"]["in_set"])}),
    ("set members have elimination order 0", lambda b: {**b, "compare_mcs": b["compare_mcs"].assign(elimination_order=np.int16(1))}),
    ("twin pairs carry no test", lambda b: {**b, "compare_pairwise": b["compare_pairwise"].assign(p_value=b["compare_pairwise"]["p_value"].fillna(0.5))}),
    ("critical value from the configured alpha", lambda b: {**b, "compare_fluctuation_sup": b["compare_fluctuation_sup"].assign(critical_value=1.0)}),
    ("fstat null exactly for the first m - 1 months", lambda b: {**b, "compare_fluctuation": b["compare_fluctuation"].assign(fstat=b["compare_fluctuation"]["fstat"].fillna(0.0))}),
    ("outside_band equals |fstat| > critical value", lambda b: {**b, "compare_fluctuation": b["compare_fluctuation"].assign(outside_band=True)}),
])
def test_check_rules_fire_with_rows(staged, cfg, rule, corrupt):
    frames, _, _, built, info = staged
    crit = info["fluctuation"]["critical_value"]
    compare.check(built, frames, cfg, crit, info["twin_pairs_per_series"])  # the clean output passes
    with pytest.raises(Exception, match=re.escape(rule)) as err:
        compare.check(corrupt(built), frames, cfg, crit, info["twin_pairs_per_series"])
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_twin_rows_of_every_table_are_empty(staged):
    *_, built, info = staged
    tw = built["compare_pairwise"].query("test == 'twin'")[["i", "k_a", "k_b"]]
    cp = built["compare_cpa"].merge(tw)
    assert len(cp) == len(tw) and cp["statistic"].isna().all() and cp["p_value"].isna().all()
    fl = built["compare_fluctuation"].merge(tw)
    assert fl["fstat"].isna().all() and not fl["outside_band"].any()
    assert built["compare_fluctuation_sup"].merge(tw)["sup_abs_fstat"].isna().all()


def test_the_configured_fluctuation_alpha_sets_the_critical_value(staged, cfg):
    frames, *_, built, info = staged
    want = compare.fluctuation_critical_value(cfg["compare.fluctuation_window"] / len(frames["grid_month"]), cfg["compare.fluctuation_alpha"])
    assert info["fluctuation"]["critical_value"] == want and (built["compare_fluctuation_sup"]["critical_value"] == want).all()


def test_mcs_matches_a_step_by_step_t_max(cfg):
    rng = np.random.default_rng(21)
    L = rng.chisquare(1, (6, 98)) * np.linspace(0.85, 1.15, 6)[:, None]
    w = compare.stationary_bootstrap_weights(98, 2000, 6.0, np.random.default_rng(22))
    p, in_set, elim = compare.mcs(L, 0.10, w)
    Lbar, Ls = L.mean(1), w @ L.T
    alive, ps, order = list(range(6)), [], []
    while len(alive) > 1:
        a = np.array(alive)
        dbar = Lbar[a] - Lbar[a].mean()
        ds = Ls[:, a] - Ls[:, a].mean(1, keepdims=True)
        sd = np.sqrt(((ds - dbar) ** 2).mean(0))
        t = dbar / sd
        ps.append(((((ds - dbar) / sd).max(1)) >= t.max()).mean())
        order.append(int(a[np.argmax(t)]))
        alive.remove(order[-1])
    want = np.ones(6)
    run_max = 0.0
    for e, pv in zip(order, ps):
        run_max = max(run_max, pv)
        want[e] = run_max
    np.testing.assert_array_equal(p, want)


def test_mcs_set_members_and_elimination_order(staged):
    *_, built, _ = staged
    for i, g in built["compare_mcs"].groupby("i"):
        assert (g.loc[g["in_set"], "elimination_order"] == 0).all()
        out = g[~g["in_set"]].drop_duplicates("represented_by")
        assert sorted(out["elimination_order"]) == list(range(1, len(out) + 1))


def test_mcs_keeps_a_model_whose_p_value_equals_alpha():
    # Two models, ten bootstrap draws: one draw reaches T_max exactly, so p = 1/10 = alpha.
    L = np.array([[2.0, 0.0], [0.0, 0.0]])
    w = np.array([[0.5, 0.5]] * 9 + [[1.0, 0.0]])
    p, in_set, elim = compare.mcs(L, 0.10, w)
    assert p.tolist() == [0.1, 1.0] and in_set.all() and (elim == 0).all()


def test_artifacts_round_trip(tmp_path, staged):
    *_, built, _ = staged
    for name, f in built.items():
        back = contracts.read(contracts.write(f, name, tmp_path / f"{name}.parquet"), name)
        if name == "compare_cpa":
            assert [list(x) for x in back["instruments"]] == [list(x) for x in f["instruments"]]
            back, f = back.drop(columns=["instruments"]), f.drop(columns=["instruments"])
        pd.testing.assert_frame_equal(back, f)


@pytest.mark.parametrize("key, value, match", [
    ("compare.cpa_instruments", ["const", "band_power"], "cpa_instruments"),
    ("compare.cpa_instruments", [], "cpa_instruments"),
    ("compare.fluctuation_alpha", 0.01, "not in"),
    ("compare.loss", "huber", "not in"),
])
def test_compare_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)
