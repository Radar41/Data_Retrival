"""Stage 4b: the fiber over each base point, its axes, transport, and the fused coordinate."""

import re

import numpy as np
import pandas as pd
import pytest

from rattractor import contracts, fixtures
from rattractor.methods import Fused, SES
from rattractor.registry import fused_member_ids
from rattractor.stages import AcceptanceError, fibers, fit, forecast, register

SID = "fixture_six_regime"


def run_all(series, cfg, reg=None):
    reg = register.run(cfg) if reg is None else reg
    states, cache = fit.run(series, reg, cfg)
    steps = forecast.run(series, reg, states, cfg, cache)
    index = fibers.fiber_index(reg, cfg)
    sid = str(series["series_id"].iloc[0])
    fb = fibers.run_series(sid, series, states, steps[sid], cfg, index)
    return reg, states, steps[sid], index, fb


@pytest.fixture(scope="module")
def built(cfg):
    series, _ = fixtures.six_regime(cfg)
    return (series, *run_all(series, cfg))


def stack(col):
    return np.stack(col.to_numpy()).astype(np.float64)


def oriented(u, w):
    """The spec's sign rules with ties broken by coordinate order, as the stage applies them."""
    if abs(u.sum()) <= fibers.SUM_TOL:
        u = u if u[fibers.lead(u)] > 0 else -u
    elif u.sum() < 0:
        u = -u
    return u, (w if w[fibers.lead(w)] > 0 else -w)


# ---- fiber_index -------------------------------------------------------------------------

def test_index_is_registry_order_with_fused_last(cfg, built):
    _, reg, _, _, index, _ = built
    adm = reg[reg["admissible"]]
    assert index["config_id"].tolist() == adm["config_id"].tolist()  # fused is already last in the registry
    assert index["is_fused"].tolist() == [False] * (len(index) - 1) + [True]
    assert index["k"].tolist() == list(range(len(index)))


def test_exclude_fused(cfg, built):
    _, reg, _, _, _, _ = built
    idx = fibers.fiber_index(reg, dict(cfg, **{"fibers.include_fused": False}))
    assert not idx["is_fused"].any() and len(idx) == int(reg["admissible"].sum()) - 1


def test_include_fused_without_a_fused_config_refused(cfg, built):
    _, reg, _, _, _, _ = built
    with pytest.raises(AcceptanceError, match="no admissible fused"):
        fibers.fiber_index(reg[reg["method"] != "fused"], cfg)


# ---- the node-table invariant -------------------------------------------------------------

def test_x_equals_minus_uf_and_abs_x_equals_r(built):
    _, _, _, steps, index, fb = built
    key = ["origin", "ladder", "h"]
    X = stack(fb["x"]).astype(np.float32)
    for k, cid in enumerate(index["config_id"]):
        s = steps[steps["config_id"] == cid].set_index(key).loc[pd.MultiIndex.from_frame(fb[key])]
        assert np.array_equal(X[:, k], -s["u_f"].to_numpy())
        assert np.array_equal(np.abs(X[:, k]), s["r"].to_numpy())


def test_step_issuance_and_rows(cfg, built):
    series, _, _, steps, index, fb = built
    H = cfg["horizon.H"]
    b, f = fb[fb["ladder"] == "backward"], fb[fb["ladder"] == "forward"]
    assert (b["step"] == b["h"] - H).all() and (f["step"] == f["h"]).all()
    assert (b["issuance"] == b["origin"] - H).all() and (f["issuance"] == f["origin"]).all()
    assert len(fb) * len(index) == len(steps[steps["config_id"].isin(index["config_id"])])


# ---- axes ----------------------------------------------------------------------------------

def test_axes_orthonormal_and_signed(built):
    _, _, _, _, _, fb = built
    U, W = stack(fb["u"]), stack(fb["w"])
    np.testing.assert_allclose(np.linalg.norm(U, axis=1), 1.0, atol=1e-6)
    np.testing.assert_allclose(np.linalg.norm(W, axis=1), 1.0, atol=1e-6)
    np.testing.assert_allclose((U * W).sum(axis=1), 0.0, atol=1e-6)
    assert (U.sum(axis=1) > 0).all()
    assert (W[np.arange(len(W)), fibers.lead(W)] > 0).all()
    assert (fb["lam1"] >= fb["lam2"]).all()


def test_axes_are_eigenvectors_of_the_window_ending_at_each_rows_issuance(cfg, built):
    # Every row, both ladders: an independent eigendecomposition of the window correlation matrix.
    _, _, states, steps, index, fb = built
    W, ddof = cfg["sigma.window"], cfg["sigma.ddof"]
    coords = index["config_id"].tolist()
    E = states.pivot(index="t", columns="config_id", values="e1")[coords].to_numpy()
    sig = steps.groupby(["issuance", "config_id"])["sigma"].first().unstack("config_id")[coords]
    expect = {}
    for i in fb["issuance"].unique():
        win = E[i - W + 1 : i + 1]
        z = (win - win.mean(axis=0)) / sig.loc[i].to_numpy()
        lam, vec = np.linalg.eigh(z.T @ z / (W - ddof))
        u, w = oriented(vec[:, -1], vec[:, -2])
        expect[i] = (u, w, lam[-1], lam[-2])
    U = np.stack([expect[i][0] for i in fb["issuance"]])
    Wx = np.stack([expect[i][1] for i in fb["issuance"]])
    np.testing.assert_allclose(stack(fb["u"]), U, atol=1e-6)
    np.testing.assert_allclose(stack(fb["w"]), Wx, atol=1e-6)
    np.testing.assert_allclose(fb["lam1"], [expect[i][2] for i in fb["issuance"]], rtol=1e-6)
    np.testing.assert_allclose(fb["lam2"], [expect[i][3] for i in fb["issuance"]], rtol=1e-6)


def window(cols, W=40, seed=0):
    rng = np.random.default_rng(seed)
    base = {name: rng.normal(size=W) for name in ("g", "h", "n1", "n2", "n3")}
    z = np.column_stack([sum(wt * base[name] for name, wt in col) for col in cols])
    z -= z.mean(axis=0)
    return z / z.std(axis=0, ddof=1)


def test_axes_known_answer_one_common_block_and_pinned_fallback():
    # Every coordinate the same residual (plus 1e-13 noise so only lam2 is degenerate):
    # u uniform, lam1 = K, and w exactly the fallback built from e_0.
    z = window([[("g", 1.0)]] * 5)
    z = z + 1e-13 * np.random.default_rng(7).normal(size=z.shape)
    u, w, lam1, lam2 = fibers.axes(z, 1, 1e-9)
    np.testing.assert_allclose(u, np.full(5, 1 / np.sqrt(5)), atol=1e-12)
    assert lam1 == pytest.approx(5.0) and lam2 < 1e-9
    np.testing.assert_allclose(w, np.array([0.8, -0.2, -0.2, -0.2, -0.2]) / np.sqrt(0.8), atol=1e-12)


def test_axes_known_answer_two_uncorrelated_blocks():
    # Block A (3 coordinates) shares g, block B (2) shares h, g and h nearly uncorrelated:
    # u is uniform on A, w uniform on B, lam1 = 3 and lam2 = 2 up to the sample correlation of g and h.
    z = window([[("g", 1.0)]] * 3 + [[("h", 1.0)]] * 2, W=4000, seed=1)
    u, w, lam1, lam2 = fibers.axes(z, 1, 1e-9)
    np.testing.assert_allclose(u, [1 / np.sqrt(3)] * 3 + [0, 0], atol=0.03)
    np.testing.assert_allclose(w, [0, 0, 0] + [1 / np.sqrt(2)] * 2, atol=0.03)
    assert lam1 == pytest.approx(3.0, abs=0.1) and lam2 == pytest.approx(2.0, abs=0.1)


def test_u_sign_follows_the_loading_sum_not_the_largest_loading():
    # The negated coordinate carries the largest |loading| by a real margin, yet the sum is positive:
    # the sum rule keeps u[3] negative where the largest-loading rule would flip u.
    z = window([[("g", 1.0), ("n1", 0.5)], [("g", 1.0), ("n2", 0.5)], [("g", 1.0), ("n3", 0.5)], [("g", -1.0)]])
    u, w, _, _ = fibers.axes(z, 1, 1e-9)
    assert int(np.argmax(np.abs(u))) == 3 and u[3] < 0 and u.sum() > 0
    assert w[fibers.lead(w)] > 0
    u2, w2, _, _ = fibers.axes(-z, 1, 1e-9)  # flipping every residual flips no axis
    np.testing.assert_allclose(u2, u, atol=1e-12)
    np.testing.assert_allclose(w2, w, atol=1e-12)


def test_axes_degenerate_window_pins_both_fallbacks():
    u, w, lam1, lam2 = fibers.axes(np.zeros((40, 4)), 1, 1e-9)
    np.testing.assert_allclose(u, 0.5)
    assert lam1 == 0.0 and lam2 == 0.0
    np.testing.assert_allclose(w, np.array([0.75, -0.25, -0.25, -0.25]) / np.sqrt(0.75), atol=1e-12)


def test_fallback_is_orthogonal_when_u_hugs_a_basis_vector():
    # Coordinate 0 carries the window, the others are 5e-9 copies of it (rank 1, lam2 = 0):
    # u lies within ~1e-8 of e_0, and the fallback must not build w from e_0.
    a = window([[("g", 1.0)]])[:, 0]
    z = np.column_stack([a] + [5e-9 * a] * 5)
    u, w, _, lam2 = fibers.axes(z, 1, 1e-9)
    assert lam2 < 1e-9 * 6 and abs(u[0]) > 1 - 1e-12
    assert abs(u @ w) < 1e-12 and np.linalg.norm(w) == pytest.approx(1.0, abs=1e-12)


def test_two_coordinates_keep_one_orientation(cfg):
    # |C| = 2: the eigenvectors are (1, +-1)/sqrt2, an exact tie for the largest-loading rule.
    # Ties go to the first coordinate, so every issuance stores the same orientation.
    series, _ = fixtures.six_regime(cfg)
    reg = register.run(cfg)
    ses = reg[reg["method"] == "ses"]
    pick = ses[ses["params"].isin(['{"alpha":0.3}', '{"alpha":0.7}'])]
    assert len(pick) == 2
    *_, fb = run_all(series, dict(cfg, **{"fibers.include_fused": False}), pick.reset_index(drop=True))
    U, W = stack(fb["u"]), stack(fb["w"])
    assert (U[:, 0] > 0).all() and (W[:, 0] > 0).all()


def test_two_negatively_correlated_coordinates_keep_one_orientation():
    # rho < 0: u = +-(1, -1)/sqrt2, so its loadings cancel and the sign falls to the largest-loading
    # rule, whose exact tie goes to the first coordinate; w = +-(1, 1)/sqrt2 ties the same way.
    rng = np.random.default_rng(5)
    for _ in range(200):
        a = rng.normal(size=40)
        z = np.column_stack([a, -0.6 * a + rng.normal(size=40)])
        z = (z - z.mean(axis=0)) / z.std(axis=0, ddof=1)
        u, w, _, _ = fibers.axes(z, 1, 1e-9)
        assert abs(u.sum()) <= fibers.SUM_TOL and u[0] > 0 and w[0] > 0


# ---- per-step quantities and transport ---------------------------------------------------

def test_per_step_quantities(built):
    _, _, _, _, index, fb = built
    X, U, W = stack(fb["x"]), stack(fb["u"]), stack(fb["w"])
    norm = np.linalg.norm(X, axis=1)
    np.testing.assert_allclose(fb["norm"], norm, rtol=1e-6)
    np.testing.assert_allclose(fb["rms"], norm / np.sqrt(len(index)), rtol=1e-6)
    np.testing.assert_allclose(fb["c"], (X * U).sum(axis=1), rtol=1e-5, atol=1e-4)
    np.testing.assert_allclose(fb["s"], (X * W).sum(axis=1), rtol=1e-5, atol=1e-4)
    np.testing.assert_allclose(fb["share"], (X * U).sum(axis=1) ** 2 / norm**2, rtol=1e-4, atol=1e-6)


def test_transport_and_issuance_switch(cfg, built):
    _, _, _, _, _, fb = built
    H = cfg["horizon.H"]
    X = stack(fb["x"])
    for o, g in fb.groupby("origin"):
        g = g.sort_values(["ladder", "h"])  # backward 1..H, then forward 1..H
        Xo = X[g.index]
        n = np.linalg.norm(Xo, axis=1)
        cos = (Xo[:-1] * Xo[1:]).sum(axis=1) / (n[:-1] * n[1:])
        np.testing.assert_allclose(g["rot_out"].to_numpy()[:-1], np.degrees(np.arccos(np.clip(cos, -1, 1))), atol=1e-3)
        np.testing.assert_allclose(g["dlog_out"].to_numpy()[:-1], np.log(n[1:] / n[:-1]), atol=1e-5)
        assert np.isnan(g["rot_out"].iloc[-1]) and np.isnan(g["dlog_out"].iloc[-1])
        sw = g[g["issuance_switch"]]
        has_fwd = (g["ladder"] == "forward").any()
        assert len(sw) == int(has_fwd)
        if has_fwd:
            assert sw["ladder"].iloc[0] == "backward" and sw["h"].iloc[0] == H and sw["step"].iloc[0] == 0
    last = fb[fb["origin"] == fb["origin"].max()]
    assert not (last["ladder"] == "forward").any() and not last["issuance_switch"].any()  # o = N - 1


# ---- leakage -------------------------------------------------------------------------------

def test_axes_and_known_fibers_do_not_see_the_future(cfg, built):
    series, reg, _, _, _, fb = built
    o = int(fb["origin"].min()) + 30
    s2 = series.copy()
    y = s2["y"].to_numpy().copy()
    y[o + 1 :] += np.random.default_rng(3).normal(0, 25, y.size - o - 1)
    s2["y"] = y
    _, _, _, _, fb2 = run_all(s2, cfg, reg)
    key = ["origin", "ladder", "h"]
    a, b = fb.set_index(key), fb2.set_index(key)
    early = a.index[a["issuance"] <= o]
    for col in ("u", "w"):
        assert np.array_equal(stack(a.loc[early, col]), stack(b.loc[early, col]))
    pd.testing.assert_series_equal(a.loc[early, "lam1"], b.loc[early, "lam1"])
    landed = a.index[(a["issuance"] + a.index.get_level_values("h")) <= o]  # y at the target is known by o
    assert np.array_equal(stack(a.loc[landed, "x"]), stack(b.loc[landed, "x"]))


# ---- the acceptance checks fire ------------------------------------------------------------

def test_x_gate_fires_with_the_failing_coordinate(cfg, built):
    series, _, states, steps, index, _ = built
    fused = index.loc[index["is_fused"], "config_id"].iloc[0]
    bad = steps.copy()
    i = bad.index[bad["config_id"] == fused][7]
    bad.loc[i, "u_f"] = np.nextafter(np.float32(bad.loc[i, "u_f"]), np.float32(np.inf))
    with pytest.raises(AcceptanceError, match="X = -u_f") as err:
        fibers.run_series(SID, series, states, bad, cfg, index)
    rows = err.value.rows
    assert len(rows) == 1 and rows["config_id"].iloc[0] == fused
    assert (rows["origin"].iloc[0], rows["ladder"].iloc[0], rows["h"].iloc[0]) == tuple(bad.loc[i, ["origin", "ladder", "h"]])


def test_sigma_gate_fires_on_every_disagreeing_pair(cfg, built):
    series, _, states, steps, index, fb = built
    bad = states.copy()
    t = int(fb["issuance"].min())
    bad.loc[bad["t"] == t, "e1"] += 1.0  # every coordinate, inside the first window
    with pytest.raises(AcceptanceError, match="sigma in steps disagrees") as err:
        fibers.run_series(SID, series, bad, steps, cfg, index)
    rows = err.value.rows
    assert set(rows["config_id"]) == set(index["config_id"])  # all pairs reported, not one per issuance
    assert rows["issuance"].min() == t


def test_missing_steps_row_refused(cfg, built):
    series, _, states, steps, index, _ = built
    with pytest.raises(AcceptanceError, match="lack a steps row"):
        fibers.run_series(SID, series, states, steps.drop(index=steps.index[11]), cfg, index)


@pytest.mark.parametrize("rule, corrupt", [
    ("u is not unit length", lambda c: {"u": c["u"] * 2}),
    ("u and w are not orthogonal", lambda c: {"w": c["u"].copy()}),
    ("u loadings sum negative", lambda c: {"u": -c["u"]}),
    ("w's largest loading is not positive", lambda c: {"w": -c["w"]}),
    ("share outside [0, 1]", lambda c: {"share": np.where(np.arange(c["share"].size) == 3, 1.5, c["share"])}),
    ("rot_out outside [0, 180] degrees", lambda c: {"rot_out": np.where(np.arange(c["rot_out"].size) == 3, 190.0, c["rot_out"])}),
    ("set at the last step of an origin", lambda c: {"rot_out": np.where(np.isnan(c["rot_out"]), 5.0, c["rot_out"])}),
    ("issuance_switch missing", lambda c: {"issuance_switch": np.zeros_like(c["issuance_switch"])}),
    ("issuance_switch on a row other than backward step 0", lambda c: {"issuance_switch": np.ones_like(c["issuance_switch"])}),
    ("issuance is not o forward and o - H backward", lambda c: {"issuance": c["issuance"] + 1}),
    ("w is not unit length", lambda c: {"w": c["w"] * 2}),
    ("c^2 + s^2 exceeds |X|^2", lambda c: {"c": c["norm"] * 2}),
    ("share is null somewhere other than X = 0", lambda c: {"share": np.where(np.arange(c["share"].size) == 3, np.nan, c["share"])}),
])
def test_row_rules_fire_with_failing_rows(cfg, built, rule, corrupt):
    series, _, states, steps, index, _ = built
    cols = fibers.compute_series(SID, series, states, steps, cfg, index)
    fibers.check(SID, len(series), cfg["horizon.H"], cols)  # the clean columns pass
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        fibers.check(SID, len(series), cfg["horizon.H"], {**cols, **corrupt(cols)})
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_row_count_rule_fires(cfg, built):
    series, _, states, steps, index, _ = built
    cols = fibers.compute_series(SID, series, states, steps, cfg, index)
    short = {k: v[:-1] if isinstance(v, np.ndarray) else v for k, v in cols.items()}
    with pytest.raises(AcceptanceError, match="row count"):
        fibers.check(SID, len(series), cfg["horizon.H"], short)


# ---- flat series known answer ------------------------------------------------------------

def test_flat_series(cfg):
    n = 200
    series = contracts.from_columns({
        "series_id": ["flat"] * n, "t": np.arange(n), "y": np.full(n, 10.0),
        "split": np.where(np.arange(n) < 100, "train", "test"),
    }, "series")
    reg = register.run(cfg)
    *_, fb = run_all(series, cfg, reg)
    assert (fb["norm"] == 0).all() and fb["share"].isna().all()
    assert fb["rot_out"].isna().all() and fb["dlog_out"].isna().all()
    assert (fb["lam1"] == 0).all() and (fb["lam2"] == 0).all()
    K = stack(fb["u"]).shape[1]
    np.testing.assert_allclose(stack(fb["u"]), 1 / np.sqrt(K), atol=1e-7)
    w0 = -np.full(K, 1 / K)
    w0[0] += 1.0
    np.testing.assert_allclose(stack(fb["w"]), np.tile(w0 / np.linalg.norm(w0), (len(fb), 1)), atol=1e-7)


# ---- the fused coordinate ------------------------------------------------------------------

def test_fused_is_the_mean_of_its_members_and_s2_their_dispersion(cfg, built):
    _, reg, states, steps, _, _ = built
    f = reg[reg["method"] == "fused"].iloc[0]
    members = fused_member_ids(f["params"])
    assert set(members) == set(reg.loc[reg["admissible"] & (reg["method"] != "fused"), "config_id"])
    assert members == sorted(members)  # stored in canonical order
    key = ["origin", "ladder", "h"]
    m_steps = steps[steps["config_id"].isin(members)].groupby(key, observed=True)["yhat"]
    fused = steps[steps["config_id"] == f["config_id"]].set_index(key)
    np.testing.assert_allclose(fused.loc[m_steps.mean().index, "yhat"], m_steps.mean(), rtol=1e-12)
    np.testing.assert_allclose(fused.loc[m_steps.mean().index, "s2"], m_steps.std(ddof=0), rtol=1e-9, atol=1e-12)
    st = states[states["config_id"] == f["config_id"]].sort_values("t")
    Y1 = np.stack([states[states["config_id"] == c].sort_values("t")["yhat1"].to_numpy() for c in members])
    np.testing.assert_allclose(st["yhat1"].to_numpy()[1:], Y1[:, 1:].mean(axis=0), rtol=1e-12)
    # s2 at t is the sd (ddof 0) of the member forecasts for t + 1 made at t.
    np.testing.assert_allclose(st["s2"].to_numpy()[:-1], Y1[:, 1:].std(axis=0, ddof=0), rtol=1e-9, atol=1e-12)


def test_fused_identity_does_not_depend_on_file_order(cfg):
    from rattractor.config import load_registry_grids
    from rattractor.registry import build_registry
    a = build_registry(load_registry_grids(cfg), cfg)
    b = build_registry(load_registry_grids(dict(cfg, **{"registry.files": ["holt.yaml", "ar.yaml", "ses.yaml", "fused.yaml"]})), cfg)
    fa, fb_ = a[a["method"] == "fused"].iloc[0], b[b["method"] == "fused"].iloc[0]
    assert (fa["config_id"], fa["core_spec_id"], fa["params"]) == (fb_["config_id"], fb_["core_spec_id"], fb_["params"])


def test_fused_identity_and_registry_row(cfg, built):
    _, reg, _, _, _, _ = built
    f = reg[reg["method"] == "fused"]
    assert len(f) == 1 and f.index[0] == reg.index[-1]
    row = f.iloc[0]
    assert row["ell_status"] == "not_applicable" and np.isnan(row["ell"]) and row["admissible"]
    assert row["core_spec_id"] not in set(reg.loc[reg["method"] != "fused", "core_spec_id"])  # its own core (DM, not CW)
    assert (row["s1_name"], row["s2_name"]) == ("consensus", "dispersion")


def test_fused_psi_is_the_member_mean(cfg):
    theta = {"members": [{"method": "ses", "params": {"alpha": 0.4}}, {"method": "ar", "params": {"phi1": 0.7, "phi2": 0.0}}]}
    np.testing.assert_allclose(Fused(cfg).psi(theta, 5), (SES(cfg).psi({"alpha": 0.4}, 5) + 0.7 ** np.arange(5)) / 2)


def test_fused_admissibility(cfg):
    m = Fused(cfg)
    one = {"members": [{"method": "ses", "params": {"alpha": 0.4}}]}
    bad = {"members": [{"method": "ses", "params": {"alpha": 0.4}}, {"method": "ar", "params": {"phi1": 0.9, "phi2": 0.3}}]}
    nested = {"members": [{"method": "ses", "params": {"alpha": 0.4}}, {"method": "fused", "params": one}]}
    assert not m.admissible(one) and not m.admissible(bad) and not m.admissible(nested)
    with pytest.raises(ValueError, match="admissible"):
        m.fit(np.arange(10.0), bad)


# ---- the list contract ---------------------------------------------------------------------

def test_list_column_round_trip(tmp_path, built):
    _, _, _, _, _, fb = built
    back = contracts.read(contracts.write(fb, "fibers", tmp_path / "f.parquet"), "fibers")
    for col in ("x", "u", "w"):
        assert np.array_equal(stack(back[col]), stack(fb[col]))
    pd.testing.assert_frame_equal(back.drop(columns=["x", "u", "w"]), fb.drop(columns=["x", "u", "w"]))


def test_list_column_refusals(tmp_path, built):
    import pyarrow as pa
    import pyarrow.parquet as pq

    _, _, _, _, _, fb = built
    f64 = fb.copy()
    f64["x"] = [v.astype(np.float64) for v in fb["x"]]
    with pytest.raises(contracts.ContractError, match="float32"):
        contracts.validate(f64, "fibers")
    ragged = fb.copy()
    ragged.at[ragged.index[0], "x"] = fb["x"].iloc[0][:-1]
    with pytest.raises(contracts.ContractError, match="lengths differ"):
        contracts.validate(ragged, "fibers")
    nan = fb.copy()
    v = fb["x"].iloc[0].copy()
    v[0] = np.nan
    nan.at[nan.index[0], "x"] = v
    with pytest.raises(contracts.ContractError, match="non-finite"):
        contracts.validate(nan, "fibers")
    short_u = fb.copy()
    short_u["u"] = [v[:-1] for v in fb["u"]]
    with pytest.raises(contracts.ContractError, match="share one length"):
        contracts.validate(short_u, "fibers")
    empty = fb.copy()
    for col in ("x", "u", "w"):
        empty[col] = [np.array([], dtype=np.float32) for _ in range(len(fb))]
    with pytest.raises(contracts.ContractError, match="share one length"):
        contracts.validate(empty, "fibers")
    # A file whose x is stored as large_list<float32> is refused on read: the type is exact.
    p = contracts.write(fb, "fibers", tmp_path / "ok.parquet")
    t = pq.read_table(p)
    i = t.schema.get_field_index("x")
    t = t.set_column(i, pa.field("x", pa.large_list(pa.float32())), t.column("x").cast(pa.large_list(pa.float32())))
    pq.write_table(t, tmp_path / "large.parquet")
    with pytest.raises(contracts.ContractError, match="Arrow type"):
        contracts.read(tmp_path / "large.parquet", "fibers")
