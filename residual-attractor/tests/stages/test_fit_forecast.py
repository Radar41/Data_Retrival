"""Stages 2-4 on the fixture: acceptance checks, leakage, ladder geometry, sigma and sigma_h."""

import json

import numpy as np
import pandas as pd
import pytest

from rattractor import contracts, fixtures
from rattractor.methods import AR, SES, Holt
from rattractor.stages import fit, forecast, register


@pytest.fixture(scope="module")
def built(cfg):
    series, _ = fixtures.six_regime(cfg)
    reg = register.run(cfg)
    states, cache = fit.run(series, reg, cfg)
    steps = forecast.run(series, reg, states, cfg, cache)["fixture_six_regime"]
    return series, reg, states, steps


def test_states_cover_every_admissible_config(built):
    series, reg, states, _ = built
    assert len(states) == len(series) * int(reg["admissible"].sum())
    assert set(states["config_id"]) == set(reg.loc[reg["admissible"], "config_id"])


def test_origins_and_row_count(cfg, built):
    series, reg, _, steps = built
    n, H = len(series), cfg["horizon.H"]
    ts = int((series["split"] == "test").to_numpy().argmax())
    O = forecast.origins(n, ts, cfg)
    assert O[0] == ts + max(cfg["sigma.window"], cfg["lagcorr.window"], H) and O[-1] == n - 1
    assert sorted(steps["origin"].unique()) == O.tolist()
    k = int(reg["admissible"].sum())
    assert len(steps) == k * sum(H + min(H, n - 1 - o) for o in O)


def test_ladder_geometry(cfg, built):
    _, _, _, steps = built
    H = cfg["horizon.H"]
    f, b = steps[steps["ladder"] == "forward"], steps[steps["ladder"] == "backward"]
    assert (f["issued"] == f["origin"]).all() and (b["issued"] == b["origin"] - H).all()
    assert (steps["t_target"] == steps["issued"] + steps["h"]).all()
    assert (b.loc[b["h"] == H, "t_target"] == b.loc[b["h"] == H, "origin"]).all()  # lands on the origin
    np.testing.assert_allclose(f["tau"], f["h"] / H, atol=1e-7)
    np.testing.assert_allclose(b["tau"], (b["h"] - H) / H, atol=1e-7)


def test_coordinates(built):
    _, _, _, s = built
    e, sig = s["e"].to_numpy(), s["sigma"].to_numpy()
    np.testing.assert_allclose(s["u_f"], -e / sig, rtol=1e-6, atol=1e-6)
    assert (s["r"] == np.abs(s["u_f"])).all()
    np.testing.assert_allclose(s["u_s"], (s["s1"] - s["y"]) / sig, rtol=1e-5, atol=1e-5)
    h1 = s[s["h"] == 1]
    np.testing.assert_allclose(h1["sigma_h"], h1["sigma"], rtol=1e-15)  # sigma_1 = sigma
    assert s["window_spans_break"].isna().all() and s["cell_id"].isna().all()


def test_sigma_is_the_window_ending_at_issuance(cfg, built):
    series, reg, states, steps = built
    cid = reg.loc[reg["admissible"], "config_id"].iloc[0]
    row = steps[(steps["config_id"] == cid) & (steps["ladder"] == "backward")].iloc[0]
    e1 = states[states["config_id"] == cid]["e1"].to_numpy()
    W, iss = cfg["sigma.window"], int(row["issued"])
    assert row["sigma"] == pytest.approx(np.std(e1[iss - W + 1 : iss + 1], ddof=cfg["sigma.ddof"]), rel=1e-12)


def test_steps_match_method_forecast(cfg, built):
    series, reg, _, steps = built
    y = series["y"].to_numpy()
    for _, r in reg[reg["admissible"]].groupby("method").head(1).iterrows():
        m = {"ses": SES, "ar": AR, "holt": Holt}[r["method"]](cfg)
        f = m.fit(y, json.loads(r["params"]))
        o = int(steps["origin"].min())
        got = steps[(steps["config_id"] == r["config_id"]) & (steps["issued"] == o) & (steps["ladder"] == "forward")]
        np.testing.assert_allclose(got.sort_values("h")["yhat"], m.forecast(f, o, cfg["horizon.H"]), rtol=0, atol=1e-12)


def test_no_leakage_in_input_side_fields(cfg, built):
    series, reg, _, steps = built
    o = int(steps["origin"].min()) + 30
    s2 = series.copy()
    y = s2["y"].to_numpy().copy()
    y[o + 1 :] += np.random.default_rng(1).normal(0, 25, y.size - o - 1)
    s2["y"] = y
    st2, cache2 = fit.run(s2, reg, cfg)
    p = forecast.run(s2, reg, st2, cfg, cache2)["fixture_six_regime"]
    key = ["config_id", "origin", "ladder", "h"]
    cols = ["yhat", "sigma", "sigma_h", "s1", "s2", "v_s"]
    a = steps[steps["issued"] <= o].sort_values(key).reset_index(drop=True)
    b = p[p["issued"] <= o].sort_values(key).reset_index(drop=True)
    # v_s scales by sigma2 over the training span, which ends before o: unchanged too.
    pd.testing.assert_frame_equal(a[key + cols], b[key + cols])


def test_states_mismatch_is_caught(cfg, built):
    series, reg, states, _ = built
    bad = states.copy()
    bad.loc[bad.index[5], "s1"] += 1.0
    with pytest.raises(Exception, match="disagrees"):
        forecast.run(series, reg, bad, cfg)


def test_constant_series_known_answer(cfg):
    n = 200
    series = contracts.from_columns({
        "series_id": ["flat"] * n, "t": np.arange(n), "y": np.full(n, 10.0),
        "split": np.where(np.arange(n) < 100, "train", "test"),
    }, "series")
    reg = register.run(cfg)
    reg = reg[reg["method"] == "ses"].reset_index(drop=True)
    states, cache = fit.run(series, reg, cfg)
    s = forecast.run(series, reg, states, cfg, cache)["flat"]
    assert (s["e"] == 0).all() and (s["r"] == 0).all()
    assert s["sigma"].eq(forecast.series_floor(np.full(100, 10.0), cfg)).all()  # sigma hits the floor


def test_psi_weights(cfg):
    H = 6
    np.testing.assert_allclose(SES(cfg).sigma_h_factor({"alpha": 0.5}, H), np.sqrt(1 + 0.25 * np.arange(H)))
    np.testing.assert_allclose(AR(cfg).psi({"phi1": 0.7, "phi2": 0.0}, H), 0.7 ** np.arange(H))
    np.testing.assert_allclose(Holt(cfg).psi({"alpha": 0.4, "beta": 0.0}, H), SES(cfg).psi({"alpha": 0.4}, H))
    # Holt psi_j = alpha (1 + j beta)
    assert Holt(cfg).psi({"alpha": 0.4, "beta": 0.5}, H)[3] == pytest.approx(0.4 * 2.5)
