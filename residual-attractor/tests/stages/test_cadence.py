"""Stage 5: cadence per ladder with the spec's nine labels (decision 4), on r_g (decision 1)."""

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts, fixtures
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, cadence, fit, forecast, register

H = 20


def path(crossings, top=4.5, base=0.2):
    """A non-decreasing failure-scale path that first reaches levels 1..4 at the given steps (None = never)."""
    r = np.full(H, base)
    for level, h in zip((1, 2, 3, 4), crossings):
        if h is not None:
            r[h - 1 :] = np.maximum(r[h - 1 :], level + 0.05)
    if crossings[-1] is not None:
        r[crossings[-1] - 1 :] = top
    return r


@pytest.mark.parametrize("label, r", [
    ("Holds", np.full(H, 0.5)),
    ("Holds", path((3, None, None, None))),
    ("Immediate", path((1, 1, 5, 9))),
    ("Oscillating", np.concatenate([np.linspace(0.2, 2.1, 5), np.full(H - 5, 1.4)])),  # reaches 2, falls below 1.5
    ("Jump", path((3, 4, 4, 10))),                                                    # gap 0 from 2 to 3
    ("Insufficient", path((2, 5, None, None))),                                       # one gap
    ("Steady", path((2, 4, 6, 8))),                                                   # gaps 2, 2, 2
    ("Steady", path((1, 2, 4, 6))),                                                   # h2 = 2 is not Immediate; gaps 1, 2, 2
    ("Steady", path((2, 3, 5, 7))),                                                   # h2 = 3 is not Immediate either
    ("Steady", path((2, 3, 5, None))),                                                # gaps 1, 2: ratio fails, max - min = 1 holds
    ("Steady", path((2, 6, 12, None))),                                               # gaps 4, 6: 6 = 1.5 x 4 holds, max - min = 2 fails
    ("Accelerating", path((2, 8, 12, 14))),                                           # gaps 6, 4, 2
    ("Decelerating", path((2, 4, 8, 14))),                                            # gaps 2, 4, 6
    ("Mixed", path((2, 6, 8, 14))),                                                   # gaps 4, 2, 6
])
def test_every_label_on_a_hand_built_path(cfg, label, r):
    _, _, got = cadence.ladder(r, cfg)
    assert got == label


def test_crossings_and_gaps_on_a_hand_built_path(cfg):
    hk, gaps, _ = cadence.ladder(path((2, 8, 12, 14)), cfg)
    assert hk == [2, 8, 12, 14] and gaps == [6, 4, 2]
    hk, gaps, _ = cadence.ladder(path((3, None, None, None)), cfg)
    assert hk == [3, None, None, None] and gaps == []


def test_crossing_on_an_exact_threshold_counts(cfg):
    # h_k = min{h : r >= k}: landing exactly on a level is a crossing (the values are exact binary floats).
    r = np.concatenate([[0.2, 1.0, 2.0, 3.0, 4.0], np.full(H - 5, 4.0)])
    assert cadence.ladder(r, cfg)[0] == [2, 3, 4, 5]


def test_sitting_exactly_at_k_minus_drop_is_not_falling_below(cfg):
    r = np.concatenate([np.linspace(0.2, 2.1, 5), np.full(H - 5, 1.5)])
    assert cadence.ladder(r, cfg)[2] == "Insufficient"


@pytest.mark.parametrize("order", [
    ["Holds", "Immediate", "Oscillating", "Jump", "Insufficient", "Accelerating", "Decelerating", "Steady", "Mixed"],
    ["Holds", "Immediate", "Oscillating", "Jump", "Insufficient", "Decelerating", "Accelerating", "Steady", "Mixed"],
])
def test_accelerating_and_decelerating_need_their_endpoint_clause_whatever_the_order(cfg, order):
    # Equal gaps are neither: with Accelerating and Decelerating ahead of Steady, the ladder still reaches Steady.
    assert cadence.ladder(path((2, 4, 6, 8)), dict(cfg, **{"cadence.labels": order}))[2] == "Steady"


def test_oscillation_respects_the_drop(cfg):
    # 2.1 then 1.6: below 2 but not below 2 - 0.5, so not Oscillating at drop 0.5; it is at drop 0.3.
    r = np.concatenate([np.linspace(0.2, 2.1, 5), np.full(H - 5, 1.6)])
    assert cadence.ladder(r, cfg)[2] != "Oscillating"
    assert cadence.ladder(r, dict(cfg, **{"cadence.oscillation_drop": 0.3}))[2] == "Oscillating"


def test_label_order_comes_from_config(cfg):
    # A ladder that fails at h = 1 and then falls back is both Immediate and Oscillating; the config's order decides.
    r = np.concatenate([[2.5], np.full(H - 1, 1.0)])
    assert cadence.ladder(r, cfg)[2] == "Immediate"
    order = ["Holds", "Oscillating", "Immediate", "Jump", "Insufficient", "Steady", "Accelerating", "Decelerating", "Mixed"]
    assert cadence.ladder(r, dict(cfg, **{"cadence.labels": order}))[2] == "Oscillating"


def test_gap_rules_need_two_gaps_whatever_the_order(cfg):
    # Steady ahead of Insufficient still cannot take a one-gap ladder.
    order = ["Holds", "Immediate", "Oscillating", "Jump", "Steady", "Insufficient", "Accelerating", "Decelerating", "Mixed"]
    assert cadence.ladder(path((2, 5, None, None)), dict(cfg, **{"cadence.labels": order}))[2] == "Insufficient"


@pytest.fixture(scope="module")
def built(cfg):
    series, _ = fixtures.six_regime(cfg)
    reg = register.run(cfg)
    states, cache = fit.run(series, reg, cfg)
    steps = forecast.run(series, reg, states, cfg, cache)["fixture_six_regime"]
    return series, reg, steps, cadence.run_series("fixture_six_regime", series, steps, cfg)


def test_one_row_per_ladder_at_eligible_origins(cfg, built):
    series, reg, steps, cad = built
    n = len(series)
    elig = sorted(o for o in steps["origin"].unique() if cfg["horizon.H"] + cfg["sigma.window"] <= o <= n - 1 - cfg["horizon.H"])
    assert sorted(cad["origin"].unique()) == elig
    assert len(cad) == len(elig) * int(reg["admissible"].sum())
    assert not cad.duplicated(["config_id", "origin"]).any()


def test_crossings_match_the_configured_scale(cfg, built):
    _, _, steps, cad = built
    fw = steps[steps["ladder"] == "forward"].set_index(["config_id", "origin", "h"]).sort_index()
    for col, scale in (("r_g", "training_growth"), ("r", "one_step")):
        c = cad if scale == "training_growth" else cadence.run_series("fixture_six_regime", built[0], steps, dict(cfg, **{"sigma.failure_scale": scale}))
        for _, row in c.sample(200, random_state=1).iterrows():
            r = fw.loc[(row["config_id"], row["origin"]), col].sort_index().to_numpy()
            for k, name in zip(cfg["thresholds"], ("h1", "h2", "h3", "h4")):
                hit = np.flatnonzero(r >= k)
                want = int(hit[0]) + 1 if hit.size else None
                got = None if pd.isna(row[name]) else int(row[name])
                assert got == want


def test_gaps_are_differences_of_the_reached_crossings(built):
    _, _, _, cad = built
    for _, row in cad.iterrows():
        hk = [int(row[c]) for c in ("h1", "h2", "h3", "h4") if not pd.isna(row[c])]
        assert row["gaps"].tolist() == np.diff(hk).tolist()


def test_no_ladder_is_pooled_with_another(cfg, built):
    # Scoring one configuration alone gives exactly its rows from the full run.
    series, reg, steps, cad = built
    cid = cad["config_id"].iloc[0]
    alone = cadence.run_series("fixture_six_regime", series, steps[steps["config_id"] == cid], cfg)
    full = cad[cad["config_id"] == cid].reset_index(drop=True)
    pd.testing.assert_frame_equal(alone.drop(columns=["gaps"]), full.drop(columns=["gaps"]))


def test_acceptance_check_fires_with_the_failing_rows(cfg, built):
    _, _, _, cad = built
    elig, ids = cad["origin"].unique(), cad["config_id"].unique()
    cadence.check("x", cad, elig, ids)  # the clean frame passes
    bad = cad.copy()
    i = bad.index[bad["h2"].notna()][0]
    bad.loc[i, "h1"] = int(bad.loc[i, "h2"]) + 1  # h1 after h2
    with pytest.raises(AcceptanceError, match="h1 <= h2") as err:
        cadence.check("x", bad, elig, ids)
    rows = err.value.rows
    assert len(rows) == 1 and (rows["config_id"].iloc[0], rows["origin"].iloc[0]) == (bad.loc[i, "config_id"], bad.loc[i, "origin"])
    with pytest.raises(AcceptanceError, match="rows, expected") as err:
        cadence.check("x", cad.iloc[:-1], elig, ids)
    assert err.value.rows["problem"].tolist() == ["missing ladder"]


def test_failed_cadence_check_writes_its_rows(cfg, tmp_path, monkeypatch):
    from rattractor.build import build
    from rattractor.runspec import load_run_spec

    real = cadence.ladder
    monkeypatch.setattr(cadence, "ladder", lambda r, c: ([5, 3, None, None], [-2], real(r, c)[2]))
    with pytest.raises(AcceptanceError, match="h1 <= h2"):
        build(load_run_spec("fixture_six_regime.yaml"), cfg, tmp_path)
    reports = list((tmp_path / "reports").glob("*/cadence.parquet"))
    assert len(reports) == 1 and len(pd.read_parquet(reports[0])) > 0
    assert not list((tmp_path / "builds").glob("*/manifest.json"))


def _labels_on(series_y, ts, cfg):
    n = series_y.size
    s = contracts.from_columns({"series_id": ["k"] * n, "t": np.arange(n), "y": series_y,
                                "split": np.where(np.arange(n) < ts, "train", "test")}, "series")
    reg = register.run(cfg)
    st, cache = fit.run(s, reg, cfg)
    steps = forecast.run(s, reg, st, cfg, cache)["k"]
    return cadence.run_series("k", s, steps, cfg).merge(reg[["config_id", "method", "params"]], on="config_id")


def test_known_answer_constant_series_holds(cfg):
    c = _labels_on(np.full(220, 10.0), 100, cfg)
    assert (c["label"] == "Holds").all()


def test_known_answer_holt_with_a_slope_holds_in_most_origins(cfg):
    y = 0.5 * np.arange(400) + np.random.default_rng(100).normal(0, 1, 400)
    c = _labels_on(y, 200, cfg)
    holt = c[(c["method"] == "holt") & ~c["params"].str.contains('"beta":0.0')]
    assert (holt["label"] == "Holds").mean() > 0.5


@pytest.mark.xfail(strict=True, reason="The spec's known answer 'trend + SES: cadence Steady in most origins' does not follow from "
                   "its own rule list: on r_g, Steady is 0.3-9.4% of SES ladders for slopes 0.25-1 (4.3% on r).")
def test_known_answer_trend_ses_steady_in_most_origins(cfg):
    y = 0.5 * np.arange(400) + np.random.default_rng(100).normal(0, 1, 400)
    c = _labels_on(y, 200, cfg)
    assert (c[c["method"] == "ses"]["label"] == "Steady").mean() > 0.5


def _cfg():
    return yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())


@pytest.mark.parametrize("key, value, match", [
    ("thresholds", [1, 2, 3], "four ascending"),
    ("thresholds", [1, 3, 2, 4], "four ascending"),
    ("cadence.fail_level", 2.5, "fail_level"),
    ("cadence.oscillation_levels", [2, 5], "oscillation_levels"),
    ("cadence.labels", ["Holds", "Immediate", "Oscillating", "Jump", "Insufficient", "Steady", "Accelerating", "Decelerating"], "labels"),
    ("cadence.labels", ["Mixed", "Holds", "Immediate", "Oscillating", "Jump", "Insufficient", "Steady", "Accelerating", "Decelerating"], "labels"),
    ("cadence.labels", ["Holds", "Holds", "Oscillating", "Jump", "Insufficient", "Steady", "Accelerating", "Decelerating", "Mixed"], "labels"),
])
def test_cadence_config_validation(key, value, match):
    c = _cfg()
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


def test_cadence_round_trip_with_nulls_and_empty_gaps(tmp_path, built):
    _, _, _, cad = built
    assert cad["h4"].isna().any() and (cad["gaps"].map(len) == 0).any()
    back = contracts.read(contracts.write(cad, "cadence", tmp_path / "c.parquet"), "cadence")
    pd.testing.assert_frame_equal(back.drop(columns=["gaps"]), cad.drop(columns=["gaps"]))
    assert all(np.array_equal(a, b) and a.dtype == np.int16 for a, b in zip(back["gaps"], cad["gaps"]))


def test_int16_columns_stored_as_another_type_are_refused(tmp_path, built):
    import pyarrow as pa
    import pyarrow.parquet as pq

    _, _, _, cad = built
    t = pq.read_table(contracts.write(cad, "cadence", tmp_path / "ok.parquet"))
    for typ in (pa.float64(), pa.int64()):
        i = t.schema.get_field_index("h1")
        bad = t.set_column(i, pa.field("h1", typ), t.column("h1").cast(typ)).replace_schema_metadata(None)
        pq.write_table(bad, tmp_path / "bad.parquet")
        with pytest.raises(ContractError, match="Arrow type"):
            contracts.read(tmp_path / "bad.parquet", "cadence")
