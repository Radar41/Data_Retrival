"""Against the local FRED catalog (skipped when it is not reachable)."""

import numpy as np
import pandas as pd
import pytest

from rattractor.stages import ingest

psycopg = pytest.importorskip("psycopg")
try:
    psycopg.connect("dbname=fred").close()
except psycopg.OperationalError:
    pytest.skip("no local fred catalog", allow_module_level=True)


@pytest.mark.parametrize("as_of, want", [
    ("2015-11-10", 2365.556991),    # first published value
    ("2020-01-01", 2365.55699088),  # revised 2015-12-07
    ("2026-05-03", np.nan),         # withdrawn 2026-01-22
])
def test_vintage_rule_picks_the_value_current_on_as_of(as_of, want):
    raw, freq, _ = ingest.extract("dbname=fred", ["PCOPPUSDM"], as_of)
    v = raw.loc[raw["observation_date"] == pd.Timestamp("1990-01-01"), "value"]
    assert len(v) == 1 and freq == {"PCOPPUSDM": "M"}
    if np.isnan(want):
        assert np.isnan(v.iloc[0])
    else:
        assert v.iloc[0] == pytest.approx(want, abs=1e-8)
    assert raw["observation_date"].max() <= pd.Timestamp(as_of)


def test_unknown_series_refused():
    with pytest.raises(Exception, match="not in the catalog"):
        ingest.extract("dbname=fred", ["NOT_A_SERIES_XYZ"], "2026-05-03")


def test_first_release_comes_from_the_earliest_vintage_holding_a_value():
    raw, freq, rel = ingest.extract("dbname=fred", ["PCOPPUSDM"], "2026-05-03")
    got = rel.set_index("observation_date")["first_release"]
    # ALFRED's history for this series has a vintage gap: its 2018-01 value first appears in 2019-06.
    assert got[pd.Timestamp("2018-01-01")] == pd.Timestamp("2019-06-18")
    assert got[pd.Timestamp("2026-02-01")] == pd.Timestamp("2026-03-24")
    assert (rel["first_release"] <= pd.Timestamp("2026-05-03")).all()


def test_first_release_skips_vintages_where_the_value_was_blank():
    # WPU1197's 2019-04 value was blank ('.') in its first vintage; the first release is the first vintage with a value.
    raw, freq, rel = ingest.extract("dbname=fred", ["WPU1197"], "2026-05-03")
    got = rel.set_index("observation_date")["first_release"]
    assert got[pd.Timestamp("2019-04-01")] == pd.Timestamp("2019-09-11")


def test_three_series_catalog_build_grid(tmp_path):
    from rattractor.build import build
    from rattractor.config import load_config
    from rattractor.runspec import validate_run_spec
    from tests.stages.test_grid import assert_build_grid

    order = ["PNICKUSDM", "PALUMUSDM", "PCOPPUSDM"]  # run-spec order, not sorted
    spec = validate_run_spec({"name": "three", "source": "catalog", "catalog": {
        "dsn": "dbname=fred", "series": order, "as_of": "2026-05-03", "frequency": "M", "aggregate": "mean",
        "max_interpolate": 0, "missing": "longest_run", "transform": "level", "test_start": "2018-01-01"}})
    cfg = load_config()
    out = build(spec, cfg, tmp_path)
    import json
    m = json.loads((out / "manifest.json").read_text())
    names = __import__("rattractor").contracts.read(out / "grid/names.parquet", "grid_names")
    assert names.loc[names.axis == "i", "name"].tolist() == order
    assert m["grid"]["vintage_id"] == "fred:2026-05-03" and m["grid"]["rdiag_minimums"]["N>=3"]
    assert_build_grid(out, m, cfg)
