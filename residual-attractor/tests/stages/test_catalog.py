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
    raw, freq = ingest.extract("dbname=fred", ["PCOPPUSDM"], as_of)
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
