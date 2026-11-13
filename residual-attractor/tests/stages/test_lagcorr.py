"""Stages 6-7: lag correlation per configuration and the bundle summary (no A(t))."""

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts, fixtures
from rattractor.config import validate_config
from rattractor.registry import build_registry
from rattractor.stages import AcceptanceError, bundle, fit, forecast, lagcorr, register


def series_frame(y, ts, sid="s"):
    n = y.size
    return contracts.from_columns({"series_id": [sid] * n, "t": np.arange(n), "y": np.asarray(y, float),
                                   "split": np.where(np.arange(n) < ts, "train", "test")}, "series")


def run6(y, ts, cfg, reg=None):
    s = series_frame(y, ts)
    reg = register.run(cfg) if reg is None else reg
    states, _ = fit.run(s, reg, cfg)
    return s, reg, states, lagcorr.run_series("s", s, states, reg, cfg)


def grid(method, **params):
    return [{"method": method, "grid_axes": list(params)[:2], "params": {k: list(v) for k, v in params.items()}}]


# ---- known answers (spec lines 568-573) ------------------------------------------------------

def test_known_answer_sinusoid_half_twist_at_lag_four(cfg):
    reg = build_registry(grid("ses", alpha=[0.1, 0.3, 0.5, 0.7, 0.9]), cfg)
    _, _, _, lc = run6(fixtures.sinusoid(400, period=8), 200, cfg, reg)
    W = cfg["lagcorr.window"]
    for _, g in lc.groupby("config_id"):
        m4, p4 = g[g["k"] == -4], g[g["k"] == 4]
        assert m4["rho"].notna().all() and (m4["n_pairs"] == W).all()
        full = p4[p4["n_pairs"] >= cfg["lagcorr.min_pairs"]]
        assert p4["rho"].notna().sum() == len(full)
        for part in (m4, full):
            assert np.abs(part["rho"] + 1).max() <= 1e-6
            assert (part["theta"] >= np.float32(np.pi) - 1e-3).all()
        whole = g[(g["n_pairs"] == W) & (g["k"] != 0)]
        np.testing.assert_allclose(whole["rho"], np.cos(2 * np.pi * whole["k"] / 8), atol=1e-6)


def _share_inside(phi1, cfg):
    reg = build_registry(grid("ar", phi1=[phi1], phi2=[0.0]), cfg)
    y = fixtures.ar1(2000, np.random.default_rng(cfg["seed"]), phi=0.7)
    _, _, _, lc = run6(y, 1000, cfg, reg)
    past = lc[(lc["k"] < 0)]
    assert past["rho"].notna().all()
    inside = np.abs(past["rho"]) <= 2 / np.sqrt(cfg["lagcorr.window"])
    return inside.groupby(past["k"]).mean(), inside.mean()


def test_known_answer_matched_ar1_past_lags_inside_the_band(cfg):
    # Share form of "past-lag rho within +-2/sqrt(W_rho)": a 2-sigma band cannot hold on every row.
    per_lag, overall = _share_inside(0.7, cfg)
    assert (per_lag >= 0.85).all() and overall >= 0.90
    per_lag, overall = _share_inside(0.3, cfg)  # a mismatched configuration must fail the same test
    assert not ((per_lag >= 0.85).all() and overall >= 0.90)


def lagcorr_frame(rho_p1, K=6, other=0.3, cfg=None, smoothing="trailing3", paths=None):
    """A hand-built lagcorr frame for one configuration: rho = 1 at k = 0, rho_p1 at k = +1, `paths[k]` at any other
    lag given, and `other` elsewhere."""
    T = len(rho_p1)
    paths = {**(paths or {}), 1: rho_p1}
    rows = []
    for k in range(-K, K + 1):
        r = np.full(T, 1.0 if k == 0 else other, dtype=np.float32)
        if k in paths:
            r = np.asarray(paths[k], dtype=np.float32)
        th = lagcorr.twist(r, smoothing)
        n = np.where(np.isnan(r), 5, 24)
        rows.append(pd.DataFrame({"t": np.arange(T), "k": k, "rho": r, "theta": th, "n_pairs": n}))
    f = pd.concat(rows, ignore_index=True)
    return contracts.from_columns({
        "series_id": ["s"] * len(f), "config_id": ["c"] * len(f), "t": f["t"].to_numpy(), "k": f["k"].to_numpy(),
        "rho": f["rho"].to_numpy(), "theta": f["theta"].to_numpy(), "n_pairs": f["n_pairs"].to_numpy(), "cell_id": [pd.NA] * len(f),
    }, "lagcorr")


def test_known_answer_three_sign_changes_on_a_closed_base_is_mobius(cfg):
    path = [0.5] * 20 + [-0.5] * 20 + [0.5] * 20 + [-0.5] * 10 + [np.nan] * 10
    lc = lagcorr_frame(path)
    row = bundle.run_series("s", lc, dict(cfg, **{"base.closed": True})).iloc[0]
    assert (row["flips_lag_p1"], row["flips_lag_m1"], row["closure_p1"]) == (3, 0, "mobius")
    assert row["total_rotation"] == pytest.approx(1.0, abs=1e-6)  # three swings of pi/3
    assert bundle.run_series("s", lc, cfg).iloc[0]["closure_p1"] == "n/a"  # open base


def test_two_sign_changes_are_orientable(cfg):
    lc = lagcorr_frame([0.5] * 30 + [-0.5] * 30 + [0.5] * 20)
    row = bundle.run_series("s", lc, dict(cfg, **{"base.closed": True})).iloc[0]
    assert (row["flips_lag_p1"], row["closure_p1"]) == (2, "orientable")
    assert row["total_rotation"] == pytest.approx(2 / 3, abs=1e-6)


def test_flips_bridge_nulls_and_zeros_between_opposite_signs(cfg):
    closed = dict(cfg, **{"base.closed": True})
    # The null sits between -0.6 and 0.2 and the zero between 0.3 and -0.6: both gaps must be bridged.
    path = [0.5, 0.4, -0.3, -0.6, np.nan, 0.2, 0.3, 0.0, -0.6, 0.2, -0.1, -0.5]
    row = bundle.run_series("s", lagcorr_frame(path, other=0.5), closed).iloc[0]
    assert (row["flips_lag_p1"], row["closure_p1"]) == (5, "mobius")
    # An even count across nulls: parity cannot catch a miss here, so assert the count.
    row = bundle.run_series("s", lagcorr_frame([0.5, np.nan, -0.5, np.nan, 0.5], other=0.5), closed).iloc[0]
    assert (row["flips_lag_p1"], row["closure_p1"]) == (2, "orientable")


def test_closure_with_one_signed_entry_is_na(cfg):
    row = bundle.run_series("s", lagcorr_frame([np.nan, 0.5, np.nan, np.nan], other=0.5), dict(cfg, **{"base.closed": True})).iloc[0]
    assert (row["flips_lag_p1"], row["closure_p1"]) == (0, "n/a")


def test_total_rotation_sums_every_nonzero_lag(cfg):
    # Lag +1 swings 0.5 -> -0.5 (1/3 half twist); lag -1 swings 0.2 -> -0.2; every other lag is constant.
    lc = lagcorr_frame([0.5] * 10 + [-0.5] * 10, other=0.3, paths={-1: [0.2] * 10 + [-0.2] * 10})
    want = (np.pi / 3 + (np.arccos(-0.2) - np.arccos(0.2))) / np.pi
    assert bundle.run_series("s", lc, cfg).iloc[0]["total_rotation"] == pytest.approx(want, abs=1e-6)


def test_total_rotation_matches_an_independent_sum_on_the_fixture(cfg, fixture_run):
    _, _, _, lc = fixture_run
    got = bundle.run_series("fixture_six_regime", lc, cfg).set_index("config_id")["total_rotation"]
    for cid, g in lc[lc["k"] != 0].groupby("config_id"):
        acc = sum(np.abs(np.diff(p.sort_values("t")["theta"].dropna().to_numpy(np.float64))).sum() for _, p in g.groupby("k"))
        assert got[cid] == pytest.approx(acc / np.pi, rel=1e-5)


def test_smoothing_skips_null_neighbours(cfg):
    r = np.float32([0.2, np.nan, 0.4, 0.6])
    np.testing.assert_allclose(lagcorr.twist(r, "trailing3"), np.arccos([0.2, np.nan, 0.3, 0.5]), atol=1e-6)
    np.testing.assert_allclose(lagcorr.twist(r, "centred3"), np.arccos([0.2, np.nan, 0.5, 0.5]), atol=1e-6)


def test_missing_residuals_inside_a_window_give_nulls_not_a_failed_check(cfg):
    # A run of non-finite e1 inside one past window: k != 0 rows lose pairs (null under the minimum);
    # k = 0 keeps its assigned rho = 1 whatever its pair count.
    s, _ = fixtures.six_regime(cfg)
    reg = register.run(cfg)
    one = reg[reg["admissible"]].iloc[[0]].reset_index(drop=True)
    states, _ = fit.run(s, one, cfg)
    t0 = int(forecast.origins(len(s), int((s["split"] == "test").to_numpy().argmax()), cfg)[0]) + 30
    states = states.copy()
    states.loc[(states["t"] > t0 - 20) & (states["t"] <= t0), "e1"] = np.nan
    lc = lagcorr.run_series("fixture_six_regime", s, states, one, cfg)
    at = lc[lc["t"] == t0]
    assert (at.loc[at["k"] == 0, "rho"] == 1).all() and (at.loc[at["k"] == 0, "n_pairs"] < cfg["lagcorr.min_pairs"]).all()
    assert at.loc[at["k"] < 0, "rho"].isna().all()


def test_flips_bridge_nulls_and_skip_exact_zeros(cfg):
    path = [0.5, 0.4, -0.3, -0.6, np.nan, -0.2, 0.3, 0.0, 0.6, 0.2, -0.1, -0.5]
    closed = dict(cfg, **{"base.closed": True})
    row = bundle.run_series("s", lagcorr_frame(path, other=0.5), closed).iloc[0]
    assert (row["flips_lag_p1"], row["closure_p1"]) == (3, "mobius")
    row = bundle.run_series("s", lagcorr_frame(path[:8], other=0.5), closed).iloc[0]
    assert (row["flips_lag_p1"], row["closure_p1"]) == (2, "orientable")


def test_known_answer_flat_windows_are_null(cfg):
    reg = build_registry(grid("ses", alpha=[0.2, 0.6]), cfg)
    _, _, _, lc = run6(fixtures.constant(400), 200, cfg, reg)
    nz = lc[lc["k"] != 0]
    assert nz["rho"].isna().all() and (nz["n_pairs"] >= cfg["lagcorr.min_pairs"]).any()
    z = lc[lc["k"] == 0]
    assert (z["rho"] == 1).all() and (z["theta"] == 0).all()
    s = bundle.run_series("s", lc, dict(cfg, **{"base.closed": True}))
    assert (s["flips_lag_m1"] == 0).all() and (s["flips_lag_p1"] == 0).all()
    assert s["total_rotation"].isna().all() and (s["closure_p1"] == "n/a").all()
    # Flat at a level binary floats cannot store: rounding residue must not make correlations.
    reg_ar = build_registry(grid("ar", phi1=[0.7], phi2=[0.0]), cfg)
    _, _, _, lc2 = run6(np.full(400, 0.1), 200, cfg, reg_ar)
    assert lc2.loc[lc2["k"] != 0, "rho"].isna().all()


# ---- the estimator ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fixture_run(cfg):
    s, _ = fixtures.six_regime(cfg)
    reg = register.run(cfg)
    states, _ = fit.run(s, reg, cfg)
    return s, reg, states, lagcorr.run_series("fixture_six_regime", s, states, reg, cfg)


def test_grid_is_configurations_by_base_by_lags(cfg, fixture_run):
    s, reg, _, lc = fixture_run
    n = len(s)
    ts = int((s["split"] == "test").to_numpy().argmax())
    O = forecast.origins(n, ts, cfg)
    K = cfg["lagcorr.K"]
    assert len(lc) == int(reg["admissible"].sum()) * O.size * (2 * K + 1)
    assert sorted(lc["t"].unique()) == O.tolist() and sorted(lc["k"].unique()) == list(range(-K, K + 1))


def test_n_pairs_closed_forms(cfg, fixture_run):
    s, _, _, lc = fixture_run
    N, W = len(s), cfg["lagcorr.window"]
    past, fwd = lc[lc["k"] < 0], lc[lc["k"] > 0]
    assert (past["n_pairs"] == W).all()
    np.testing.assert_array_equal(fwd["n_pairs"], np.clip(N - fwd["t"] - fwd["k"], 0, W))
    assert (lc.loc[lc["n_pairs"] < cfg["lagcorr.min_pairs"], "rho"].isna()).all()


def test_rho_matches_an_independent_pearson(cfg, fixture_run):
    s, _, states, lc = fixture_run
    N, W = len(s), cfg["lagcorr.window"]
    rows = lc[(lc["k"] != 0) & lc["rho"].notna()].sample(300, random_state=3)
    e_by = {c: g.sort_values("t")["e1"].to_numpy() for c, g in states.groupby("config_id")}
    for _, r in rows.iterrows():
        e, t, k = e_by[r["config_id"]], int(r["t"]), int(r["k"])
        idx = np.arange(t - W + 1, t + 1) if k < 0 else np.arange(t, t + W)
        part = idx + k
        ok = (idx >= 1) & (idx <= N - 1) & (part >= 1) & (part <= N - 1)
        want = np.corrcoef(e[idx[ok]], e[part[ok]])[0, 1]
        assert r["rho"] == pytest.approx(want, abs=2e-7)
        assert r["n_pairs"] == ok.sum()


def test_theta_is_arccos_of_the_trailing_mean_along_the_base(cfg, fixture_run):
    _, _, _, lc = fixture_run
    g = lc[(lc["config_id"] == lc["config_id"].iloc[0]) & (lc["k"] == -2)].sort_values("t")
    r = g["rho"].to_numpy(np.float64)
    S = np.array([r[max(0, j - 2) : j + 1].mean() for j in range(r.size)])
    np.testing.assert_allclose(g["theta"], np.arccos(S), atol=1e-6)
    zero = lc[lc["k"] == 0]
    assert (zero["rho"] == 1).all() and (zero["theta"] == 0).all()


def test_past_lags_do_not_see_the_future(cfg, fixture_run):
    s, reg, _, lc = fixture_run
    cut = int(lc["t"].min()) + 40
    s2 = s.copy()
    y = s2["y"].to_numpy().copy()
    y[cut + 1 :] += np.random.default_rng(5).normal(0, 20, y.size - cut - 1)
    s2["y"] = y
    states2, _ = fit.run(s2, reg, cfg)
    lc2 = lagcorr.run_series("fixture_six_regime", s2, states2, reg, cfg)
    key = ["config_id", "t", "k"]
    a = lc[(lc["k"] < 0) & (lc["t"] <= cut)].sort_values(key).reset_index(drop=True)
    b = lc2[(lc2["k"] < 0) & (lc2["t"] <= cut)].sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_centred_smoothing_would_leak_into_past_lag_theta(cfg, fixture_run):
    # Why trailing3 is the default: centred3 lets theta at t read rho at t + 1.
    r = np.array([0.2, 0.4, 0.6, 0.8], dtype=np.float32)
    assert lagcorr.twist(r, "trailing3")[1] == lagcorr.twist(np.r_[r[:2], [-0.9, -0.9]].astype(np.float32), "trailing3")[1]
    assert lagcorr.twist(r, "centred3")[1] != lagcorr.twist(np.r_[r[:2], [-0.9, -0.9]].astype(np.float32), "centred3")[1]
    np.testing.assert_array_equal(lagcorr.twist(r, "none"), np.arccos(r.astype(np.float64)).astype(np.float32))


def test_one_configuration_alone_gives_its_own_rows(cfg, fixture_run):
    s, reg, states, lc = fixture_run
    cid = reg.loc[reg["admissible"], "config_id"].iloc[7]
    one = reg[reg["config_id"] == cid].reset_index(drop=True)
    alone = lagcorr.run_series("fixture_six_regime", s, states, one, cfg)
    full = lc[lc["config_id"] == cid].reset_index(drop=True)
    pd.testing.assert_frame_equal(alone, full)


# ---- acceptance checks fire ------------------------------------------------------------------

def _origins(lc):
    return np.array(sorted(lc["t"].unique()))


@pytest.mark.parametrize("rule, corrupt", [
    ("rho = 1 and theta = 0 at k = 0", lambda f: f.assign(rho=np.where(f["k"] == 0, np.float32(0.9), f["rho"]))),
    ("rows under the pair minimum are null", lambda f: f.assign(rho=np.where(f["n_pairs"] < 10, np.float32(0.1), f["rho"]))),
    ("theta = arccos of the declared smoothing of rho", lambda f: f.assign(theta=np.where(f["k"] == -3, np.float32(1.0), f["theta"]))),
])
def test_stage6_checks_fire_with_rows(cfg, fixture_run, rule, corrupt):
    _, reg, _, lc = fixture_run
    coords = list(reg.loc[reg["admissible"], "config_id"])
    lagcorr.check("x", lc, coords, _origins(lc), cfg)  # the clean frame passes
    bad = corrupt(lc.copy())
    for c in ("rho", "theta"):
        bad[c] = bad[c].astype(np.float32)
    with pytest.raises(AcceptanceError, match=re_escape(rule)) as err:
        lagcorr.check("x", bad, coords, _origins(lc), cfg)
    assert err.value.rows is not None and (err.value.rows["problem"] == rule).any()


def re_escape(s):
    import re
    return re.escape(s)


def test_stage7_tampered_closure_or_flips_raise(cfg):
    lc = lagcorr_frame([0.5] * 20 + [-0.5] * 20 + [0.5] * 20 + [-0.5] * 10 + [np.nan] * 10)
    closed = dict(cfg, **{"base.closed": True})
    good = bundle.run_series("s", lc, closed)
    tampered = good.copy()
    tampered["closure_p1"] = pd.Categorical(["orientable"], categories=["orientable", "mobius", "n/a"])
    with pytest.raises(AcceptanceError, match="break a rule"):
        bundle.check("s", tampered, lc, closed)
    odd = bundle.run_series("s", lc, cfg).copy()  # open base: parity is still checked
    odd["flips_lag_p1"] = np.int16(2)
    with pytest.raises(AcceptanceError, match="break a rule") as err:
        bundle.check("s", odd, lc, cfg)
    assert err.value.rows["problem"].str.contains("parity").any()


def test_bundle_summary_has_one_row_per_configuration(cfg, fixture_run):
    _, reg, _, lc = fixture_run
    s = bundle.run_series("fixture_six_regime", lc, cfg)
    assert len(s) == int(reg["admissible"].sum()) and s["config_id"].is_unique
    assert (s["closure_p1"] == "n/a").all()  # open base
    closed = bundle.run_series("fixture_six_regime", lc, dict(cfg, **{"base.closed": True}))
    odd = closed["flips_lag_p1"] % 2 == 1
    assert ((closed["closure_p1"] == "mobius") == odd).all()


# ---- config ----------------------------------------------------------------------------------

@pytest.mark.parametrize("key, value, match", [
    ("lagcorr.min_pairs", 30, "exceeds lagcorr.window"),
    ("lagcorr.K", 200, "1..127"),
    ("lagcorr.smoothing", "mean3", "not in"),
])
def test_lagcorr_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)
