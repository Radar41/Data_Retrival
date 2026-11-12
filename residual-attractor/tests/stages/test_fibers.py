"""Stage 4b: the fiber over each base point is the collection of every configuration's own residual."""

import re

import numpy as np
import pandas as pd
import pytest

from rattractor import contracts, fixtures
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


def test_index_is_every_admissible_configuration_in_registry_order(built):
    _, reg, _, _, index, _ = built
    assert index["config_id"].tolist() == reg.loc[reg["admissible"], "config_id"].tolist()
    assert index["k"].tolist() == list(range(len(index)))
    assert list(index.columns) == ["k", "config_id"]


def test_one_configuration_is_a_valid_archive(cfg):
    # Archiving one configuration's residuals never depends on another configuration existing.
    series, _ = fixtures.six_regime(cfg)
    reg = register.run(cfg)
    one = reg[reg["admissible"]].iloc[[0]].reset_index(drop=True)
    _, _, steps, index, fb = run_all(series, cfg, one)
    assert len(index) == 1 and fb["x"].iloc[0].size == 1
    key = ["origin", "ladder", "h"]
    s = steps.set_index(key).loc[pd.MultiIndex.from_frame(fb[key])]
    assert np.array_equal(stack(fb["x"])[:, 0].astype(np.float32), -s["u_f"].to_numpy())


def test_no_configuration_combines_others(built):
    # Every registered configuration is a parameter configuration with its own residuals.
    _, reg, _, _, _, _ = built
    assert set(reg["method"]) == {"ses", "ar", "holt"}


def test_redundant_configurations_are_kept(built):
    # Holt(alpha, beta = 0) is exactly SES(alpha); both stay, and the fiber carries both residuals.
    _, reg, states, _, index, _ = built
    holt0 = reg[(reg["method"] == "holt") & reg["params"].str.contains('"beta":0.0')]
    assert len(holt0) == 4 and set(holt0["config_id"]) <= set(index["config_id"])
    ses = reg[(reg["method"] == "ses") & (reg["params"] == '{"alpha":0.2}')]["config_id"].iloc[0]
    hol = reg[(reg["method"] == "holt") & (reg["params"] == '{"alpha":0.2,"beta":0.0}')]["config_id"].iloc[0]
    a = states[states["config_id"] == ses]["yhat1"].to_numpy()
    b = states[states["config_id"] == hol]["yhat1"].to_numpy()
    np.testing.assert_allclose(a[1:], b[1:], atol=1e-12)


def test_fiber_rows_carry_only_the_collection(built):
    _, _, _, _, _, fb = built
    assert list(fb.columns) == ["series_id", "origin", "ladder", "h", "step", "issuance", "x", "issuance_switch"]


def test_x_equals_minus_uf_and_abs_x_equals_r(built):
    _, _, _, steps, index, fb = built
    key = ["origin", "ladder", "h"]
    X = stack(fb["x"]).astype(np.float32)
    for k, cid in enumerate(index["config_id"]):
        s = steps[steps["config_id"] == cid].set_index(key).loc[pd.MultiIndex.from_frame(fb[key])]
        assert np.array_equal(X[:, k], -s["u_f"].to_numpy())
        assert np.array_equal(np.abs(X[:, k]), s["r"].to_numpy())


def test_step_issuance_and_rows(cfg, built):
    _, _, _, steps, index, fb = built
    H = cfg["horizon.H"]
    b, f = fb[fb["ladder"] == "backward"], fb[fb["ladder"] == "forward"]
    assert (b["step"] == b["h"] - H).all() and (f["step"] == f["h"]).all()
    assert (b["issuance"] == b["origin"] - H).all() and (f["issuance"] == f["origin"]).all()
    assert len(fb) * len(index) == len(steps)


def test_issuance_switch(cfg, built):
    _, _, _, _, _, fb = built
    H = cfg["horizon.H"]
    for o, g in fb.groupby("origin"):
        sw = g[g["issuance_switch"]]
        has_fwd = (g["ladder"] == "forward").any()
        assert len(sw) == int(has_fwd)
        if has_fwd:
            assert sw["ladder"].iloc[0] == "backward" and sw["h"].iloc[0] == H and sw["step"].iloc[0] == 0
    last = fb[fb["origin"] == fb["origin"].max()]
    assert not (last["ladder"] == "forward").any() and not last["issuance_switch"].any()  # o = N - 1


def test_known_fibers_do_not_see_the_future(cfg, built):
    series, reg, _, _, _, fb = built
    o = int(fb["origin"].min()) + 30
    s2 = series.copy()
    y = s2["y"].to_numpy().copy()
    y[o + 1 :] += np.random.default_rng(3).normal(0, 25, y.size - o - 1)
    s2["y"] = y
    *_, fb2 = run_all(s2, cfg, reg)
    key = ["origin", "ladder", "h"]
    a, b = fb.set_index(key), fb2.set_index(key)
    landed = a.index[(a["issuance"] + a.index.get_level_values("h")) <= o]  # target known by o
    assert len(landed) > 0
    assert np.array_equal(stack(a.loc[landed, "x"]), stack(b.loc[landed, "x"]))


def test_x_gate_fires_with_the_failing_coordinate(cfg, built):
    series, _, states, steps, index, _ = built
    cid = index["config_id"].iloc[-1]
    bad = steps.copy()
    i = bad.index[bad["config_id"] == cid][7]
    bad.loc[i, "u_f"] = np.nextafter(np.float32(bad.loc[i, "u_f"]), np.float32(np.inf))
    with pytest.raises(AcceptanceError, match="X = -u_f") as err:
        fibers.run_series(SID, series, states, bad, cfg, index)
    rows = err.value.rows
    assert len(rows) == 1 and rows["config_id"].iloc[0] == cid
    assert (rows["origin"].iloc[0], rows["ladder"].iloc[0], rows["h"].iloc[0]) == tuple(bad.loc[i, ["origin", "ladder", "h"]])


def test_sigma_gate_fires_on_every_disagreeing_pair(cfg, built):
    series, _, states, steps, index, fb = built
    bad = states.copy()
    t = int(fb["issuance"].min())
    bad.loc[bad["t"] == t, "e1"] += 1.0  # every coordinate, inside the first window
    with pytest.raises(AcceptanceError, match="sigma in steps disagrees") as err:
        fibers.run_series(SID, series, bad, steps, cfg, index)
    rows = err.value.rows
    assert set(rows["config_id"]) == set(index["config_id"])
    assert rows["issuance"].min() == t


def test_missing_steps_row_refused(cfg, built):
    series, _, states, steps, index, _ = built
    with pytest.raises(AcceptanceError, match="lack a steps row"):
        fibers.run_series(SID, series, states, steps.drop(index=steps.index[11]), cfg, index)


@pytest.mark.parametrize("rule, corrupt", [
    ("issuance is not o forward and o - H backward", lambda c: {"issuance": c["issuance"] + 1}),
    ("issuance_switch missing", lambda c: {"issuance_switch": np.zeros_like(c["issuance_switch"])}),
    ("issuance_switch on a row other than backward step 0", lambda c: {"issuance_switch": np.ones_like(c["issuance_switch"])}),
])
def test_row_rules_fire_with_failing_rows(cfg, built, rule, corrupt):
    series, _, states, steps, index, _ = built
    cols = fibers.compute_series(SID, series, states, steps, cfg, index)
    fibers.check(SID, len(series), cfg["horizon.H"], len(index), cols)  # the clean columns pass
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        fibers.check(SID, len(series), cfg["horizon.H"], len(index), {**cols, **corrupt(cols)})
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_row_count_and_length_rules_fire(cfg, built):
    series, _, states, steps, index, _ = built
    cols = fibers.compute_series(SID, series, states, steps, cfg, index)
    short = {k: v[:-1] if isinstance(v, np.ndarray) else v for k, v in cols.items()}
    with pytest.raises(AcceptanceError, match="row count"):
        fibers.check(SID, len(series), cfg["horizon.H"], len(index), short)
    with pytest.raises(AcceptanceError, match="x has length"):
        fibers.check(SID, len(series), cfg["horizon.H"], len(index) + 1, cols)


def test_flat_series(cfg):
    n = 200
    series = contracts.from_columns({
        "series_id": ["flat"] * n, "t": np.arange(n), "y": np.full(n, 10.0),
        "split": np.where(np.arange(n) < 100, "train", "test"),
    }, "series")
    *_, fb = run_all(series, cfg)
    assert (stack(fb["x"]) == 0).all()


def test_list_column_round_trip(tmp_path, built):
    _, _, _, _, _, fb = built
    back = contracts.read(contracts.write(fb, "fibers", tmp_path / "f.parquet"), "fibers")
    assert np.array_equal(stack(back["x"]), stack(fb["x"]))
    pd.testing.assert_frame_equal(back.drop(columns=["x"]), fb.drop(columns=["x"]))


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
    empty = fb.copy()
    empty["x"] = [np.array([], dtype=np.float32) for _ in range(len(fb))]
    with pytest.raises(contracts.ContractError, match="share one length"):
        contracts.validate(empty, "fibers")
    p = contracts.write(fb, "fibers", tmp_path / "ok.parquet")
    t = pq.read_table(p)
    i = t.schema.get_field_index("x")
    t = t.set_column(i, pa.field("x", pa.large_list(pa.float32())), t.column("x").cast(pa.large_list(pa.float32())))
    pq.write_table(t, tmp_path / "large.parquet")
    with pytest.raises(contracts.ContractError, match="Arrow type"):
        contracts.read(tmp_path / "large.parquet", "fibers")
