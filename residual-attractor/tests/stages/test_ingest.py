"""Stage 1 on synthetic extracts (no database needed) and the run-spec contract."""

import numpy as np
import pandas as pd
import pytest

from rattractor import ContractError
from rattractor.runspec import load_run_spec, validate_run_spec
from rattractor.stages import AcceptanceError, ingest

CAT = dict(dsn="dbname=x", series=["A"], as_of="2026-05-03", frequency="M", aggregate="mean",
           max_interpolate=0, missing="fail", transform="level", test_start="2025-01-01")


def raw_monthly(sid, start, n, values=None):
    d = pd.date_range(start, periods=n, freq="MS")
    v = np.arange(1.0, n + 1) if values is None else np.asarray(values, float)
    return pd.DataFrame({"series_id": sid, "observation_date": d, "value": v})


def test_monthly_passthrough_and_split():
    raw = raw_monthly("A", "2020-01-01", 72)
    s, cal = ingest.prepare(raw, {"A": "M"}, CAT)
    assert len(s) == 72 and s["t"].tolist() == list(range(72))
    assert (s["split"] == "test").sum() == 12  # 2025-01 .. 2025-12
    assert cal["period"].iloc[0] == "2020-01-01" and cal["period"].iloc[-1] == "2025-12-01"
    assert ingest.split_boundary(s) == {"A": 60}


def test_interior_gap_fail_and_longest_run():
    v = np.arange(1.0, 73)
    v[10] = np.nan
    raw = raw_monthly("A", "2020-01-01", 72, v)
    with pytest.raises(AcceptanceError, match="interior gaps"):
        ingest.prepare(raw, {"A": "M"}, CAT)
    s, cal = ingest.prepare(raw, {"A": "M"}, dict(CAT, missing="longest_run"))
    assert len(s) == 61 and cal["period"].iloc[0] == "2020-12-01"


def test_short_gaps_interpolated_and_flagged():  # needs a train/test split inside the kept run
    v = np.arange(1.0, 73)
    v[10:14] = np.nan   # 4-period gap: filled
    v[50:56] = np.nan   # 6-period gap: left for the missing policy
    raw = raw_monthly("A", "2020-01-01", 72, v)
    s, cal = ingest.prepare(raw, {"A": "M"}, dict(CAT, max_interpolate=4, missing="longest_run", test_start="2023-01-01"))
    assert cal["period"].iloc[0] == "2020-01-01" and len(s) == 50  # 2020-01 .. 2024-02, through the filled gap
    np.testing.assert_allclose(s["y"].to_numpy()[10:14], np.arange(11.0, 15.0))  # linear fill of a line
    assert cal["imputed"].tolist() == [False] * 10 + [True] * 4 + [False] * 36
    with pytest.raises(AcceptanceError, match="interior gaps"):
        ingest.prepare(raw, {"A": "M"}, dict(CAT, max_interpolate=4))


def test_diff_of_imputed_level_is_imputed():
    v = np.arange(1.0, 73)
    v[10] = np.nan
    s, cal = ingest.prepare(raw_monthly("A", "2020-01-01", 72, v), {"A": "M"}, dict(CAT, max_interpolate=1, transform="diff"))
    assert np.flatnonzero(cal["imputed"].to_numpy()).tolist() == [9, 10]  # diffs into and out of the filled level


def test_absent_period_is_a_gap():
    raw = raw_monthly("A", "2020-01-01", 72).drop(index=20)
    with pytest.raises(AcceptanceError, match="interior gaps"):
        ingest.prepare(raw, {"A": "M"}, CAT)


def test_leading_and_trailing_nulls_trimmed():
    v = np.arange(1.0, 73)
    v[:3] = np.nan
    v[-1] = np.nan
    s, cal = ingest.prepare(raw_monthly("A", "2020-01-01", 72, v), {"A": "M"}, CAT)
    assert len(s) == 68 and cal["period"].iloc[0] == "2020-04-01"


def test_weekly_aggregates_and_drops_open_month():
    d = pd.date_range("2023-01-06", "2026-05-01", freq="W-FRI")
    raw = pd.DataFrame({"series_id": "W", "observation_date": d, "value": np.arange(d.size, dtype=float)})
    s, cal = ingest.prepare(raw, {"W": "W"}, dict(CAT, series=["W"]))
    assert cal["period"].iloc[-1] == "2026-04-01"  # May 2026 is still open on as_of
    jan = raw[raw["observation_date"].dt.to_period("M") == pd.Period("2023-01")]["value"].mean()
    assert s["y"].iloc[0] == pytest.approx(jan)


def test_coarser_native_frequency_refused():
    with pytest.raises(AcceptanceError, match="coarser"):
        ingest.prepare(raw_monthly("A", "2020-01-01", 72), {"A": "Q"}, CAT)


@pytest.mark.parametrize("how", ["log", "diff", "log_diff"])
def test_transforms(how):
    raw = raw_monthly("A", "2020-01-01", 72)
    s, _ = ingest.prepare(raw, {"A": "M"}, dict(CAT, transform=how))
    v = np.arange(1.0, 73)
    want = {"log": np.log(v), "diff": np.diff(v), "log_diff": np.diff(np.log(v))}[how]
    np.testing.assert_allclose(s["y"].to_numpy(), want)


def test_log_needs_positive():
    with pytest.raises(AcceptanceError, match="positive"):
        ingest.prepare(raw_monthly("A", "2020-01-01", 72, np.zeros(72)), {"A": "M"}, dict(CAT, transform="log"))


def test_empty_split_refused():
    with pytest.raises(AcceptanceError, match="empty train or test"):
        ingest.prepare(raw_monthly("A", "2020-01-01", 12), {"A": "M"}, CAT)


def test_raw_hash_ignores_row_order():
    raw = raw_monthly("A", "2020-01-01", 24)
    assert ingest.raw_sha256(raw) == ingest.raw_sha256(raw.iloc[::-1])


def test_run_specs_in_repo_validate():
    assert load_run_spec("fixture_six_regime.yaml")["source"] == "fixture"
    spec = load_run_spec("spec0_spring_adan7406.yaml")
    assert spec["catalog"]["frequency"] == "M"


@pytest.mark.parametrize("bad", [
    {"name": "x", "source": "fixture", "catalog": {}},           # catalog keys refused for fixture
    {"name": "x", "source": "catalog"},                         # catalog block missing
    {"name": "x", "source": "catalog", "catalog": dict(CAT, as_of="May 3")},
    {"name": "x", "source": "catalog", "catalog": dict(CAT, series=["A", "A"])},
    {"name": "x", "source": "catalog", "catalog": {k: v for k, v in CAT.items() if k != "missing"}},
    {"name": "x", "source": "catalog", "catalog": dict(CAT, frequency="D")},
    {"name": "x", "source": "catalog", "catalog": dict(CAT, max_interpolate=-1)},
])
def test_run_spec_rejections(bad):
    with pytest.raises(ContractError):
        validate_run_spec(bad)


def releases_for(raw, lag_days=40):
    r = raw[raw["value"].notna()][["series_id", "observation_date"]].copy()
    r["first_release"] = r["observation_date"] + pd.Timedelta(days=lag_days)
    return r


def test_first_release_monthly_and_interpolated(cfg=None):
    v = np.arange(1.0, 73)
    v[10] = np.nan
    raw = raw_monthly("A", "2020-01-01", 72, v)
    s, cal = ingest.prepare(raw, {"A": "M"}, dict(CAT, max_interpolate=1), releases_for(raw))
    assert cal["first_release"].iloc[0] == "2020-02-10"
    assert pd.isna(cal["first_release"].iloc[10]) and cal["imputed"].iloc[10]   # an interpolated month was never released
    assert cal["first_release"].iloc[11] == (pd.Timestamp("2020-12-01") + pd.Timedelta(days=40)).date().isoformat()


def test_first_release_of_an_aggregated_month_is_its_last_observation(cfg=None):
    d = pd.date_range("2023-01-06", "2026-05-01", freq="W-FRI")
    raw = pd.DataFrame({"series_id": "W", "observation_date": d, "value": np.arange(d.size, dtype=float)})
    rel = raw[["series_id", "observation_date"]].copy()
    rel["first_release"] = rel["observation_date"] + pd.Timedelta(days=4)
    s, cal = ingest.prepare(raw, {"W": "W"}, dict(CAT, series=["W"]), rel)
    jan = d[(d.year == 2023) & (d.month == 1)]
    assert cal["first_release"].iloc[0] == (jan.max() + pd.Timedelta(days=4)).date().isoformat()


def test_first_release_of_a_difference_is_the_later_level(cfg=None):
    raw = raw_monthly("A", "2020-01-01", 72)
    rel = releases_for(raw)
    rel.loc[rel["observation_date"] == pd.Timestamp("2020-03-01"), "first_release"] = pd.Timestamp("2021-01-01")  # a late first release
    s, cal = ingest.prepare(raw, {"A": "M"}, dict(CAT, transform="diff"), rel)
    # diff at 2020-03 needs 2020-02 and 2020-03; diff at 2020-04 needs 2020-03 and 2020-04: both wait for 2021-01-01
    assert cal.set_index("period").loc["2020-03-01", "first_release"] == "2021-01-01"
    assert cal.set_index("period").loc["2020-04-01", "first_release"] == "2021-01-01"
    assert cal.set_index("period").loc["2020-05-01", "first_release"] == "2020-06-10"


def test_no_releases_gives_null_first_release():
    s, cal = ingest.prepare(raw_monthly("A", "2020-01-01", 72), {"A": "M"}, CAT)
    assert cal["first_release"].isna().all()


def test_interpolated_month_has_no_release_under_differencing():
    v = np.arange(1.0, 73)
    v[10] = np.nan
    raw = raw_monthly("A", "2020-01-01", 72, v)
    s, cal = ingest.prepare(raw, {"A": "M"}, dict(CAT, max_interpolate=1, transform="diff"), releases_for(raw))
    assert cal["imputed"].to_numpy().nonzero()[0].tolist() == [9, 10]
    assert cal.loc[cal["imputed"], "first_release"].isna().all()
