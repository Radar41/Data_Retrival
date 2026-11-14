"""Stage tails: rdiag's Stage 2d under v2. Hill curve, mean excess, rolling Hill and each row's own threshold."""

import atexit
import json
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy import optimize, stats

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, tails

TABLES = ("tails_hill_curve", "tails_mean_excess", "tails_rolling_hill", "tails_thresholds")
_SHARED = {}


def grid_frames(R, start="1700-01-01"):
    """The grid tables an analysis stage reads (resid, config, series, month) for a field R[k, i, t]."""
    K, N, P = R.shape
    months = pd.date_range(start, periods=P, freq="MS").to_numpy().astype("datetime64[ns]")
    kk, ii, tt = np.meshgrid(np.arange(K), np.arange(N), np.arange(P), indexing="ij")
    return {
        "grid_resid": contracts.from_columns({"k": kk.ravel(), "i": ii.ravel(), "t": months[tt.ravel()], "resid": R.ravel()}, "grid_resid"),
        "grid_config": contracts.from_columns({"k": np.arange(K), "core_spec_id": [f"c{k}" for k in range(K)],
                                               "exog_set": [[] for _ in range(K)]}, "grid_config"),
        "grid_series": contracts.from_columns({"i": np.arange(N)}, "grid_series"),
        "grid_month": contracts.from_columns({"t": months}, "grid_month"),
    }


def three_series_grid(cfg):
    """Stage 9's tables for test_grid's three synthetic series (54 configurations x 3 series x 168 months), built once."""
    if "grid" not in _SHARED:
        from rattractor.stages import fibers, fit, grid, register
        from tests.stages.test_grid import three_series

        series, calendar = three_series(cfg)
        reg = register.run(cfg)
        states, _ = fit.run(series, reg, cfg)
        coords = list(fibers.fiber_index(reg, cfg)["config_id"])
        months, t_of = grid.holdout(series, calendar)
        Z, ids = [], []
        for n, (sid, g) in enumerate(series.groupby("series_id", sort=False, observed=True)):
            Z.append(grid.series_rows(str(sid), n, g, states, coords, t_of[str(sid)], cfg))
            ids.append(str(sid))
        _SHARED["grid"] = grid.assemble(Z, ids, reg, coords, months, t_of, calendar, cfg, "test:v1", "build-x")
    return _SHARED["grid"]


def fixture_build(cfg):
    """(directory, manifest) of one build of the one-series fixture, shared by the tests of tails, events and coincidence."""
    if "fixture" not in _SHARED:
        from rattractor.build import build
        from rattractor.runspec import load_run_spec

        root = Path(tempfile.mkdtemp(prefix="rattractor-tails-"))
        atexit.register(shutil.rmtree, root, True)
        out = build(load_run_spec("fixture_six_regime.yaml"), cfg, root)
        _SHARED["fixture"] = (out, json.loads((out / "manifest.json").read_text()))
    return _SHARED["fixture"]


def one_row(x, cfg):
    """The stage on a single row (one configuration, one series)."""
    return tails.run(grid_frames(np.asarray(x, dtype=np.float64)[None, None, :]), cfg)[0]


# ---- grids from the config ----------------------------------------------------------------------

def test_grids_resolve_from_the_config(cfg):
    assert tails.resolve_count("floor(P / 4)", 98) == 24 and tails.resolve_count(10, 98) == 10
    assert tails.n_tail_grid(cfg, 98).tolist() == list(range(10, 25))        # spec 0: 15 counts
    assert tails.n_tail_grid(cfg, 39).size == 0                               # floor(39 / 4) = 9 < 10: no curve
    q = tails.quantile_grid(cfg)
    assert q.size == 29 and q[0] == 0.70 and q[-1] == 0.98 and np.allclose(np.diff(q), 0.01, atol=1e-12)


# ---- Hill ---------------------------------------------------------------------------------------

def test_hill_by_hand():
    g = tails.hill(np.array([[8.0, 4.0, 2.0, 1.0]]), np.array([1, 2, 3]))
    np.testing.assert_allclose(g[0], [np.log(2), 1.5 * np.log(2), 2 * np.log(2)], rtol=1e-14)
    # the (n_tail + 1)-th largest value is 0: no logarithm, no estimate
    assert np.isnan(tails.hill(np.array([[3.0, 2.0, 0.0, 0.0]]), np.array([1, 2]))).tolist() == [[False, True]]


def test_n_tail_star_is_the_middle_of_the_steadiest_range():
    g = np.array([[0.9, 0.5, 0.31, 0.30, 0.30, 0.30, 0.35, 0.6, 0.9]])
    assert tails.hill_star(g, 3).tolist() == [4]            # the range 3..5 is flat; its middle
    assert tails.hill_star(g, 4).tolist() == [3]            # the range 2..5; the lower middle of an even width
    assert tails.hill_star(np.full((1, 6), 0.3), 3).tolist() == [1]   # every range ties: the lowest
    holed = g.copy()
    holed[0, 4] = np.nan                                    # ranges holding a null gamma are passed over
    assert tails.hill_star(holed, 3).tolist() == [np.nanargmin([np.var(holed[0, j : j + 3]) for j in range(7)]) + 1]
    assert tails.hill_star(g, 10).tolist() == [-1] and tails.hill_star(np.full((1, 4), np.nan), 2).tolist() == [-1]


def test_hill_returns_the_tail_index_of_exact_pareto_samples(cfg):
    # |x| Pareto with index alpha: gamma = 1 / alpha at every n_tail, up to sampling error gamma / sqrt(n_tail).
    rng = np.random.default_rng(0)
    P, alphas = 4000, (2.0, 4.0)
    R = np.stack([(rng.pareto(a, P) + 1.0) * rng.choice([-1, 1], P) for a in alphas])[:, None, :]
    b, _ = tails.run(grid_frames(R), cfg)
    for k, alpha in enumerate(alphas):
        h = b["tails_hill_curve"].query("k == @k")
        assert h["n_tail"].tolist() == list(range(10, 1001))
        assert ((h["gamma"] - 1 / alpha).abs() < 3 * h["se"]).all()
        np.testing.assert_allclose(h["se"], h["gamma"] / np.sqrt(h["n_tail"]), rtol=1e-15)
        assert h["star"].sum() == 1
        m = b["tails_mean_excess"].query("k == @k")
        # the excesses of a Pareto over any threshold are generalized Pareto with shape 1 / alpha: stable from the lowest quantile
        assert ((m["gpd_ci_lo"] <= 1 / alpha) & (1 / alpha <= m["gpd_ci_hi"])).all()
        assert b["tails_thresholds"].query("k == @k")["u"].tolist() == [0]


def test_star_matches_a_direct_search(staged, cfg):
    _, built, _ = staged
    hc, width = built["tails_hill_curve"], cfg["tails.n_tail_stability_width"]
    for (k, i), h in hc.groupby(["k", "i"]):
        g, n = h["gamma"].to_numpy(), h["n_tail"].to_numpy()
        var = [np.var(g[j : j + width]) for j in range(g.size - width + 1)]
        assert h.loc[h["star"], "n_tail"].tolist() == [n[int(np.argmin(var)) + (width - 1) // 2]]


def test_rolling_hill_is_hill_on_the_trailing_window(cfg):
    rng = np.random.default_rng(1)
    R = rng.standard_t(3, (2, 2, 60))
    for window, n_tail in ((cfg["tails.rolling_window"], cfg["tails.rolling_n_tail"]), (12, 3)):
        c = {**cfg, "tails.rolling_window": window, "tails.rolling_n_tail": n_tail}
        rh = tails.run(grid_frames(R), c)[0]["tails_rolling_hill"]
        months = np.sort(rh["t"].unique())
        pos = np.searchsorted(months, rh["t"].to_numpy())
        assert (rh["gamma"].isna() == (pos < window - 1)).all() and (rh["se"].isna() == rh["gamma"].isna()).all()
        full = rh.assign(pos=pos)[pos >= window - 1]
        for row in full.sample(40, random_state=2).itertuples():
            t = row.pos
            top = sorted(np.abs(R[row.k, row.i, t - window + 1 : t + 1]), reverse=True)
            want = np.mean(np.log(top[:n_tail])) - np.log(top[n_tail])
            assert row.gamma == pytest.approx(want, rel=1e-12) and row.se == pytest.approx(want / np.sqrt(n_tail), rel=1e-12)
    late = tails.run(grid_frames(R), {**cfg, "tails.rolling_window": 61, "tails.rolling_n_tail": 6})[0]["tails_rolling_hill"]
    assert late["gamma"].isna().all()   # a window longer than the sample: null everywhere, not an error


# ---- mean excess and the generalized Pareto fit ---------------------------------------------------

def test_the_mean_excess_of_an_exponential_is_flat(cfg):
    rng = np.random.default_rng(100)
    x = rng.exponential(1.0, 6000) * rng.choice([-1, 1], 6000)
    b = one_row(x, cfg)
    m = b["tails_mean_excess"]
    assert ((m["mean_excess"] - 1.0).abs() < 3 / np.sqrt(m["n_exceed"])).all()       # e(u) = 1 at every threshold
    assert ((m["gpd_ci_lo"] <= 0) & (0 <= m["gpd_ci_hi"])).all() and m["gpd_shape"].abs().max() < 0.2   # shape 0
    assert m["stable"].all() and b["tails_thresholds"]["u"].tolist() == [0]
    a = np.abs(x)
    for row in m.itertuples():
        assert row.threshold == np.quantile(a, 0.70 + 0.01 * row.u) or row.threshold == pytest.approx(np.quantile(a, 0.70 + 0.01 * row.u), rel=1e-12)
        assert row.n_exceed == (a > row.threshold).sum()
        assert row.mean_excess == pytest.approx((a[a > row.threshold] - row.threshold).mean(), rel=1e-12)


def gpd_loglik(xi, sigma, y):
    if abs(xi) < 1e-12:
        return -y.size * np.log(sigma) - y.sum() / sigma
    t = 1 + xi * y / sigma
    return -np.inf if (t <= 0).any() else -y.size * np.log(sigma) - (1 + 1 / xi) * np.log(t).sum()


def gpd_profile(xi, y):
    """max over sigma of the two-parameter log-likelihood at shape xi, by a bounded search over ln sigma."""
    lo = np.log(-xi * y.max()) if xi < 0 else np.log(y.max()) - 40.0   # sigma > -xi max(y)
    r = optimize.minimize_scalar(lambda s: -gpd_loglik(xi, np.exp(s), y), bounds=(lo, np.log(y.max()) + 40.0),
                                 method="bounded", options={"xatol": 1e-13})
    return -r.fun


def test_gpd_fit_maximizes_the_two_parameter_likelihood(cfg):
    rng = np.random.default_rng(3)
    chi2 = stats.chi2.ppf(0.95, 1)
    at_min = cut = 0
    for _ in range(36):
        n = int(rng.integers(3, 41))
        y = stats.genpareto.rvs(rng.choice([-0.3, 0.0, 0.3, 1.0]), scale=rng.choice([0.2, 1.0, 30.0]), size=n, random_state=rng)
        Y = np.zeros((1, 45))
        Y[0, :n] = y
        (shape,), (lo,), (hi,) = tails.gpd_fit(Y, np.array([n]), -0.5, 0.95)
        best = gpd_profile(shape, y)
        assert shape >= -0.5 and lo <= shape <= hi
        assert all(best >= gpd_profile(x, y) - 1e-8 for x in np.linspace(-0.5, 4.0, 46))     # nothing on the allowed range does better
        assert 2 * (best - gpd_profile(hi, y)) == pytest.approx(chi2, abs=1e-6)             # the upper end sits on the level
        if lo > -0.5:
            assert 2 * (best - gpd_profile(lo, y)) == pytest.approx(chi2, abs=1e-6)
        else:
            assert 2 * (best - gpd_profile(-0.5, y)) <= chi2 + 1e-8                          # the bound cuts the interval
            cut += 1
        at_min += shape == -0.5
    assert at_min >= 3 and cut > at_min   # both the bound as estimate and the bound as interval end were exercised


def test_gpd_fit_does_not_depend_on_scale_or_padding():
    rng = np.random.default_rng(4)
    y = stats.genpareto.rvs(0.4, size=17, random_state=rng)
    Y = np.zeros((3, 30))
    Y[0, :17], Y[1, :17], Y[2, :17] = y, 1000.0 * y, y
    Y[2, 17:] = -7.0                                         # values past n are never read
    shape, lo, hi = tails.gpd_fit(Y, np.array([17, 17, 17]), -0.5, 0.95)
    np.testing.assert_allclose(shape, shape[0], rtol=1e-9)
    np.testing.assert_allclose(lo, lo[0], rtol=1e-9)
    np.testing.assert_allclose(hi, hi[0], rtol=1e-9)
    assert shape[2] == shape[0] and lo[2] == lo[0] and hi[2] == hi[0]


def test_the_profile_interval_covers_where_estimate_plus_minus_z_se_does_not():
    # Why the stability rule reads the profile-likelihood interval: at the handful of exceedances a row has,
    # shape +/- 1.96 (1 + shape) / sqrt(n) misses the true shape most of the time.
    rng = np.random.default_rng(5)
    for n, wald_max, profile_min in ((5, 0.40, 0.95), (10, 0.65, 0.93), (30, 0.82, 0.89)):
        Y = rng.exponential(1.0, (2000, n))                  # true shape 0
        shape, lo, hi = tails.gpd_fit(Y, np.full(2000, n), -0.5, 0.95)
        wald = np.abs(shape) <= stats.norm.ppf(0.975) * (1 + shape) / np.sqrt(n)
        assert wald.mean() < wald_max and ((lo <= 0) & (0 <= hi)).mean() > profile_min


def test_stable_thresholds_by_hand():
    nan = np.nan
    shape = np.array([[0.9, 0.2, 0.5, nan, 0.4], [0.3, 0.9, 0.3, nan, nan], [-0.5, 0.0, nan, nan, nan]])
    lo = np.array([[0.5, 0.0, 0.1, nan, -0.5], [0.0, 0.6, 0.1, nan, nan], [-0.5, -0.5, nan, nan, nan]])
    hi = np.array([[1.3, 0.45, 0.9, nan, 2.0], [0.6, 1.2, 0.5, nan, nan], [0.1, 0.4, nan, nan, nan]])
    assert tails.stable_thresholds(shape, lo, hi).tolist() == [
        [False, True, True, False, True],      # 0.9 lies outside [0.0, 0.45]; an unfitted threshold is never stable
        [False, False, True, False, False],    # 0.3 is inside the top interval but outside [0.6, 1.2]: every higher one counts
        [True, True, False, False, False],     # an estimate on an interval's end is inside
    ]
    assert tails.stable_thresholds(np.array([[0.4, 0.1]]), np.array([[0.0, -0.5]]), np.array([[0.9, 0.4]])).tolist() == [[True, True]]   # the upper end too
    assert not tails.stable_thresholds(np.full((1, 3), nan), np.full((1, 3), nan), np.full((1, 3), nan)).any()


def test_the_threshold_lands_where_the_tail_begins(cfg):
    # 85% of |x| uniform on (0, 1), 15% a Pareto tail starting at 1: below the 0.85 quantile the excesses are not
    # generalized Pareto and their shape is far off; from it on the shape is 1/2 at every threshold.
    rng = np.random.default_rng(300)
    x = np.concatenate([rng.uniform(0, 1, 5100), 1.0 + 50.0 * rng.pareto(2.0, 900)])
    rng.shuffle(x)
    b = one_row(x * rng.choice([-1, 1], x.size), cfg)
    th, m = b["tails_thresholds"].iloc[0], b["tails_mean_excess"]
    assert th["u"] == 15 and 1.0 <= th["u_star"] < 1.01 and th["n_exceed"] == 900     # index 15 is the 0.85 quantile
    assert not m["stable"].iloc[:15].any() and m["stable"].iloc[15:].all()
    assert m["gpd_shape"].iloc[0] > 2.0 and ((m["gpd_ci_lo"] <= 0.5) & (0.5 <= m["gpd_ci_hi"])).iloc[15:].all()


def test_thresholds_with_too_few_exceedances_are_not_fitted(cfg):
    rng = np.random.default_rng(6)
    x = rng.standard_normal(98)                               # spec 0's length: 2 exceedances at the 0.98 quantile
    m = one_row(x, cfg)["tails_mean_excess"]
    assert m["n_exceed"].tolist() == [30 - j for j in range(29)]
    assert m["gpd_shape"].isna().tolist() == [False] * 28 + [True] and not m["stable"].iloc[-1] and m["stable"].iloc[-2]
    m10 = one_row(x, {**cfg, "tails.min_exceed": 10})["tails_mean_excess"]
    assert (m10["gpd_shape"].isna() == (m10["n_exceed"] < 10)).all() and m10["stable"].iloc[20] and not m10["stable"].iloc[21:].any()
    np.testing.assert_array_equal(m10["gpd_shape"].iloc[:21], m["gpd_shape"].iloc[:21])   # a fit does not depend on which others exist


# ---- the stage on a grid ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def staged(cfg):
    frames = three_series_grid(cfg)
    built, info = tails.run(frames, cfg)
    return frames, built, info


def test_tables_on_three_series(staged, cfg):
    frames, built, info = staged
    R, months = tails.dense(frames)
    K, N, P = R.shape
    hc, me, rh, th = (built[x] for x in TABLES)
    assert (len(hc), len(me), len(rh), len(th)) == (K * N * 33, K * N * 29, K * N * P, K * N)   # n_tail 10..42 at P = 168
    assert info["rows"] == K * N and info["rows_without_threshold"] == 0 and info["rows_without_star"] == 0
    a = np.abs(R)
    for row in th.sample(60, random_state=7).itertuples():
        x = a[row.k, row.i]
        rows = me[(me["k"] == row.k) & (me["i"] == row.i)]
        assert row.u == rows.loc[rows["stable"], "u"].min()                       # the lowest stable threshold ...
        assert row.u_star == rows.loc[rows["u"] == row.u, "threshold"].iloc[0]   # ... of the row itself
        assert row.n_exceed == (x > row.u_star).sum() >= cfg["tails.min_exceed"]
    for row in me.sample(200, random_state=8).itertuples():
        x = a[row.k, row.i]
        assert row.threshold == pytest.approx(np.quantile(x, 0.70 + 0.01 * row.u), rel=1e-12)
        assert row.n_exceed == (x > row.threshold).sum()
        assert row.mean_excess == pytest.approx((x[x > row.threshold] - row.threshold).mean(), rel=1e-12)
    for row in hc.sample(200, random_state=9).itertuples():
        top = np.sort(a[row.k, row.i])[::-1]
        assert row.gamma == pytest.approx(np.mean(np.log(top[: row.n_tail])) - np.log(top[row.n_tail]), rel=1e-12)


def changed(frames, k, factor, seed=11):
    """The same grid with configuration k's residuals replaced."""
    r = frames["grid_resid"].copy()
    sel = (r["k"] == k).to_numpy()
    r.loc[sel, "resid"] = factor * r.loc[sel, "resid"].to_numpy() + np.random.default_rng(seed).standard_normal(int(sel.sum()))
    return {**frames, "grid_resid": contracts.validate(r, "grid_resid")}


def assert_other_configurations_identical(before, after, k):
    for name in before:
        x, y = before[name], after[name]
        keep_x, keep_y = (x["k"] != k).to_numpy(), (y["k"] != k).to_numpy()
        pd.testing.assert_frame_equal(x[keep_x].reset_index(drop=True), y[keep_y].reset_index(drop=True), check_exact=True)
        if "threshold" in x.columns or "gamma" in x.columns or "u_star" in x.columns:
            col = next(c for c in ("threshold", "gamma", "u_star") if c in x.columns)
            assert not np.array_equal(x.loc[~keep_x, col].to_numpy(), y.loc[~keep_y, col].to_numpy(), equal_nan=True)


def test_changing_one_configuration_leaves_every_other_row_bit_identical(staged, cfg):
    # The archive rule: no value in any table is computed from more than one configuration.
    frames, built, _ = staged
    again, _ = tails.run(changed(frames, 7, 1.7), cfg)
    assert_other_configurations_identical(built, again, 7)


def test_rows_do_not_depend_on_which_configurations_and_series_are_present(staged, cfg):
    frames, built, _ = staged
    R, months = tails.dense(frames)
    keep_k, keep_i = [30, 3, 17], [2, 0]
    small, _ = tails.run(grid_frames(R[np.ix_(keep_k, keep_i)], start=str(months[0])[:10]), cfg)
    for name in TABLES:
        full = built[name]
        for nk, k in enumerate(keep_k):
            for ni, i in enumerate(keep_i):
                x = small[name].query("k == @nk and i == @ni").drop(columns=["k", "i"]).reset_index(drop=True)
                y = full[(full["k"] == k) & (full["i"] == i)].drop(columns=["k", "i"]).reset_index(drop=True)
                pd.testing.assert_frame_equal(x, y, check_exact=True)


def test_rows_that_cannot_be_measured_get_nulls_and_disturb_nothing(cfg, tmp_path):
    rng = np.random.default_rng(12)
    P = 98
    sparse = np.zeros(P)
    sparse[rng.choice(P, 18, replace=False)] = rng.standard_t(3, 18) + 5.0
    ordinary = rng.standard_t(4, P)
    R = np.stack([np.zeros(P), np.where(np.arange(P) % 2 == 0, 1.0, -1.0), sparse, ordinary])[None, :, :]
    b, info = tails.run(grid_frames(R), cfg)                      # the stage's own check passes on all of it
    hc, me, rh, th = (b[x] for x in TABLES)
    zero = lambda f: f[f["i"] == 0]
    assert zero(hc)["gamma"].isna().all() and not zero(hc)["star"].any() and zero(rh)["gamma"].isna().all()
    assert zero(me)["mean_excess"].isna().all() and (zero(me)["n_exceed"] == 0).all() and zero(me)["gpd_shape"].isna().all()
    flat = th[th["i"].isin([0, 1])]                               # all zero, and all of one size: nothing lies above any quantile
    assert flat["u"].isna().all() and flat["u_star"].isna().all() and (flat["n_exceed"] == 0).all()
    assert (hc.loc[hc["i"] == 1, "gamma"] == 0).all() and hc.loc[hc["i"] == 1, "star"].sum() == 1
    s = hc[hc["i"] == 2]                                          # 18 values above zero: the curve exists for n_tail <= 17
    assert (s["gamma"].isna() == (s["n_tail"] >= 18)).all() and s.loc[s["star"], "n_tail"].between(12, 15).all()
    assert th.loc[th["i"] == 2, "n_exceed"].iloc[0] >= 3 and info["rows_without_threshold"] == 2 and info["rows_without_star"] == 1
    back = contracts.read(contracts.write(th, "tails_thresholds", tmp_path / "thresholds.parquet"), "tails_thresholds")
    pd.testing.assert_frame_equal(back, th)                       # the nulls survive the file
    alone, _ = tails.run(grid_frames(ordinary[None, None, :]), cfg)
    for name in TABLES:
        pd.testing.assert_frame_equal(b[name][b[name]["i"] == 3].drop(columns="i").reset_index(drop=True),
                                      alone[name].drop(columns="i"), check_exact=True)


def test_a_short_sample_gets_no_hill_curve_and_a_grid_past_the_sample_stops(cfg):
    rng = np.random.default_rng(13)
    R = rng.standard_normal((1, 2, 36))
    b, info = tails.run(grid_frames(R), cfg)                      # floor(36 / 4) = 9 < 10: an empty n_tail grid
    assert len(b["tails_hill_curve"]) == 0 and info["rows_without_star"] == 2 and b["tails_thresholds"]["u_star"].notna().all()
    with pytest.raises(AcceptanceError, match="Hill needs"):
        tails.run(grid_frames(R), {**cfg, "tails.n_tail_grid": [10, 36]})


def _first(frame, col, value):
    out = frame.copy()
    out.loc[out.index[0], col] = value
    return out


@pytest.mark.parametrize("rule, table, corrupt", [
    ("se equals gamma / sqrt(n_tail)", "tails_hill_curve", lambda f: f.assign(se=f["se"] * 1.01)),
    ("gamma is null exactly where", "tails_hill_curve", lambda f: _first(_first(f, "gamma", np.nan), "se", np.nan)),
    ("at most one star per row", "tails_hill_curve", lambda f: f.assign(star=True)),
    ("n_exceed counts |resid| above the threshold", "tails_mean_excess", lambda f: f.assign(n_exceed=f["n_exceed"] + np.int32(1))),
    ("mean_excess is null exactly where nothing exceeds", "tails_mean_excess", lambda f: _first(f, "mean_excess", np.nan)),
    ("thresholds are not negative and mean excesses are positive", "tails_mean_excess", lambda f: f.assign(mean_excess=-f["mean_excess"])),
    ("a generalized Pareto fit exactly where", "tails_mean_excess", lambda f: _first(f, "gpd_shape", np.nan)),
    ("tails.gpd_shape_min <= gpd_ci_lo <= gpd_shape <= gpd_ci_hi", "tails_mean_excess", lambda f: f.assign(gpd_ci_lo=f["gpd_ci_hi"], gpd_ci_hi=f["gpd_ci_lo"])),
    ("tails.gpd_shape_min <= gpd_ci_lo <= gpd_shape <= gpd_ci_hi", "tails_mean_excess", lambda f: f.assign(gpd_ci_lo=f["gpd_ci_lo"] - 1.0)),
    ("stable means the shape lies inside the interval of every higher fitted threshold", "tails_mean_excess", lambda f: f.assign(stable=~f["stable"])),
    ("rolling gamma is null exactly before the first full window", "tails_rolling_hill", lambda f: f.assign(gamma=f["gamma"].fillna(0.5), se=f["se"].fillna(0.2))),
    ("rolling se equals gamma / sqrt(tails.rolling_n_tail)", "tails_rolling_hill", lambda f: f.assign(se=f["se"] * 2)),
    ("u_star is the row's lowest stable threshold", "tails_thresholds", lambda f: f.assign(u_star=f["u_star"] * 1.1)),
    ("u_star is the row's lowest stable threshold", "tails_thresholds", lambda f: f.assign(u=pd.array(f["u"] + 1, dtype="Int16"))),
    ("n_exceed counts |resid| above u_star", "tails_thresholds", lambda f: f.assign(n_exceed=f["n_exceed"] + np.int32(1))),
    ("a chosen threshold has at least tails.min_exceed exceedances", "tails_thresholds", lambda f: f.assign(n_exceed=np.int32(1))),
])
def test_check_rules_fire_with_rows(staged, cfg, rule, table, corrupt):
    frames, built, _ = staged
    tails.check(built, frames, cfg)                               # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        tails.check({**built, table: contracts.validate(corrupt(built[table]), table)}, frames, cfg)
    rows = err.value.rows
    assert rows is not None and rows["problem"].str.contains(rule, regex=False).any() and {"k", "i", "artifact"} <= set(rows.columns)


def test_check_counts_rows(staged, cfg):
    frames, built, _ = staged
    with pytest.raises(AcceptanceError, match="tails_thresholds has 161 rows, expected 162"):
        tails.check({**built, "tails_thresholds": built["tails_thresholds"].iloc[1:].reset_index(drop=True)}, frames, cfg)


def test_artifacts_round_trip(tmp_path, staged):
    _, built, _ = staged
    for name, f in built.items():
        pd.testing.assert_frame_equal(contracts.read(contracts.write(f, name, tmp_path / f"{name}.parquet"), name), f)


def test_one_series_fixture_build(cfg):
    out, m = fixture_build(cfg)
    assert "tails" in m["stages_passed"] and m["stages_passed"].index("tails") > m["stages_passed"].index("compare")
    K, P = m["configurations"]["admissible"], m["grid"]["rdiag_minimums"]["P"]
    grid_n = tails.n_tail_grid(cfg, P)
    want = {"tails/hill_curve.parquet": K * grid_n.size, "tails/mean_excess.parquet": K * 29, "tails/rolling_hill.parquet": K * P, "tails/thresholds.parquet": K}
    for rel, rows in want.items():
        assert m["artifacts"][rel]["rows"] == rows == len(contracts.read(out / rel, m["artifacts"][rel]["artifact"]))
    assert m["tails"]["rows"] == K and m["tails"]["gpd"]["interval"] == "profile_likelihood"


@pytest.mark.parametrize("key, value, match", [
    ("tails.n_tail_grid", [10], "n_tail_grid"),
    ("tails.n_tail_grid", [10, "P / 4"], "n_tail_grid"),
    ("tails.n_tail_grid", [0, 24], "n_tail_grid"),
    ("tails.n_tail_grid", [30, 24], "n_tail_grid"),
    ("tails.n_tail_grid", [10, True], "n_tail_grid"),
    ("tails.threshold_grid_quantiles", [0.7, 0.98], "threshold_grid_quantiles"),
    ("tails.threshold_grid_quantiles", [0.9, 0.7, 0.01], "threshold_grid_quantiles"),
    ("tails.threshold_grid_quantiles", [0.7, 1.0, 0.01], "threshold_grid_quantiles"),
    ("tails.threshold_grid_quantiles", [0.7, 0.98, 0], "threshold_grid_quantiles"),
    ("tails.rolling_n_tail", 36, "rolling_n_tail"),
    ("tails.min_exceed", 2, "tails.min_exceed"),
    ("tails.gpd_shape_min", 0.0, "gpd_shape_min"),
    ("tails.gpd_shape_min", -0.9, "gpd_shape_min"),
    ("tails.gpd_ci", "wald", "not in"),
    ("tails.threshold_rule", "fixed_sigma", "not in"),
    ("tails.n_tail_rule", "eyeball", "not in"),
])
def test_tails_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    validate_config(dict(c))
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)
