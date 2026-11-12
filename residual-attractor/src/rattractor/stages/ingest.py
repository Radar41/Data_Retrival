"""Stage 1, ingest: series as of a vintage date -> series + calendar artifacts.

Works on any list of FRED series. The extract is one query against the
catalog's observation table: the value current on `as_of` is the row with
realtime_start <= as_of <= realtime_end. Everything after the query is a pure
function of the extracted rows (prepare), so it is tested without a database.

Preprocessing, every step declared in the run spec:
  1. put each series on the target frequency (aggregate finer series by period;
     coarser ones are refused; an aggregated period not yet over on as_of is dropped),
  2. reindex to the full period range, trim leading and trailing gaps, fill
     interior gaps of at most max_interpolate periods linearly (flagged in
     calendar.imputed), then refuse any gap left (missing = fail) or keep the
     longest gap-free run,
  3. transform (level, log, diff, log_diff),
  4. split: periods on or after test_start are test.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError

# FRED frequency codes, finest first. A series can be put on any target at or above its own rank.
_RANK = {"D": 0, "W": 1, "BW": 2, "M": 3, "Q": 4, "SA": 5, "A": 6}
_PANDAS = {"M": "M", "Q": "Q", "A": "Y"}

EXTRACT_SQL = """
SELECT o.series_id, o.observation_date, o.value::float8 AS value
FROM observation o
WHERE o.series_id = ANY(%(ids)s)
  AND o.realtime_start <= %(as_of)s AND o.realtime_end >= %(as_of)s
ORDER BY o.series_id, o.observation_date
"""
FREQ_SQL = "SELECT series_id, frequency_code FROM series WHERE series_id = ANY(%(ids)s)"


def extract(dsn: str, series: list[str], as_of: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """(raw rows: series_id, observation_date, value with NaN for FRED '.', {series_id: frequency_code})."""
    import psycopg

    args = {"ids": list(series), "as_of": dt.date.fromisoformat(as_of)}
    with psycopg.connect(dsn) as conn:
        freq = dict(conn.execute(FREQ_SQL, args).fetchall())
        rows = conn.execute(EXTRACT_SQL, args).fetchall()
    missing = sorted(set(series) - set(freq))
    if missing:
        raise AcceptanceError("ingest", f"series not in the catalog: {missing}")
    raw = pd.DataFrame(rows, columns=["series_id", "observation_date", "value"])
    raw["observation_date"] = pd.to_datetime(raw["observation_date"])
    raw["value"] = raw["value"].astype(np.float64)
    return raw, freq


def raw_sha256(raw: pd.DataFrame) -> str:
    """Content hash of the extract, independent of row order."""
    r = raw.sort_values(["series_id", "observation_date"])
    text = "\n".join(
        f"{s}|{d.date().isoformat()}|{'' if np.isnan(v) else repr(float(v))}"
        for s, d, v in zip(r["series_id"], r["observation_date"], r["value"])
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _to_frequency(sid: str, s: pd.Series, native: str, target: str, how: str, as_of: str) -> pd.Series:
    if native not in _RANK:
        raise AcceptanceError("ingest", f"{sid}: frequency {native!r} has no rank")
    if _RANK[native] > _RANK[target]:
        raise AcceptanceError("ingest", f"{sid}: frequency {native} is coarser than the target {target}")
    per = s.index.to_period(_PANDAS[target])
    if native == target:
        out = pd.Series(s.to_numpy(), index=per)
        if out.index.has_duplicates:
            raise AcceptanceError("ingest", f"{sid}: two observations in one {target} period")
        return out
    g = s.dropna().groupby(s.dropna().index.to_period(_PANDAS[target]))
    out = {"mean": g.mean, "last": g.last, "sum": g.sum}[how]()
    # A period still open on as_of would be an aggregate of part of it: drop it.
    return out[out.index.end_time.normalize() <= pd.Timestamp(as_of)]


def _runs(ok: np.ndarray) -> list[tuple[int, int]]:
    """[(start, stop)) of each run of True."""
    edges = np.diff(np.concatenate(([0], ok.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def _gaps(sid: str, s: pd.Series, policy: str, max_interp: int) -> tuple[pd.Series, np.ndarray]:
    """(gap-free series, imputed flags)."""
    full = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq=s.index.freq))
    ok = full.notna().to_numpy()
    if not ok.any():
        raise AcceptanceError("ingest", f"{sid}: no values in this vintage")
    first, last = np.argmax(ok), len(ok) - 1 - np.argmax(ok[::-1])
    full, ok = full.iloc[first : last + 1], ok[first : last + 1]
    imputed = np.zeros(len(full), dtype=bool)
    if max_interp > 0:
        vals = full.to_numpy(np.float64).copy()
        for a, b in _runs(~ok):  # interior only: the ends were trimmed above
            if b - a <= max_interp:
                vals[a:b] = np.interp(np.arange(a, b), [a - 1, b], [vals[a - 1], vals[b]])
                imputed[a:b] = True
        full = pd.Series(vals, index=full.index)
        ok = ok | imputed
    if ok.all():
        return full, imputed
    if policy == "fail":
        holes = [str(p) for p in full.index[~ok][:5]]
        raise AcceptanceError("ingest", f"{sid}: {int((~ok).sum())} interior gaps (first {holes}); missing = fail")
    # longest_run: the longest stretch with no gap left; earliest wins a tie.
    a, b = max(_runs(ok), key=lambda r: (r[1] - r[0], -r[0]))
    return full.iloc[a:b], imputed[a:b]


def _transform(sid: str, s: pd.Series, how: str) -> pd.Series:
    if how in ("log", "log_diff"):
        if (s <= 0).any():
            raise AcceptanceError("ingest", f"{sid}: {how} needs positive values")
        s = np.log(s)
    if how in ("diff", "log_diff"):
        s = s.diff().iloc[1:]
    return s


def prepare(raw: pd.DataFrame, freq: dict[str, str], cat: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw extract -> (series artifact, calendar artifact), in the run spec's series order."""
    test_start = pd.Period(cat["test_start"], freq=_PANDAS[cat["frequency"]])
    parts, cal = [], []
    for sid in cat["series"]:
        r = raw[raw["series_id"] == sid]
        if r.empty:
            raise AcceptanceError("ingest", f"{sid}: no observations current on {cat['as_of']}")
        s = pd.Series(r["value"].to_numpy(), index=pd.DatetimeIndex(r["observation_date"]))
        s = _to_frequency(sid, s, freq[sid], cat["frequency"], cat["aggregate"], cat["as_of"])
        s, imputed = _gaps(sid, s, cat["missing"], cat["max_interpolate"])
        s = _transform(sid, s, cat["transform"])
        if len(imputed) != len(s):  # diff drops the first period
            imputed = imputed[1:] | imputed[:-1]  # a difference touching an imputed level is imputed
        test = s.index >= test_start
        if test.all() or not test.any():
            raise AcceptanceError("ingest", f"{sid}: test_start {test_start} leaves an empty train or test split")
        n = len(s)
        parts.append({
            "series_id": [sid] * n,
            "t": np.arange(n),
            "y": s.to_numpy(np.float64),
            "split": np.where(test, "test", "train"),
        })
        cal.append({"series_id": [sid] * n, "t": np.arange(n), "period": [p.start_time.date().isoformat() for p in s.index],
                    "imputed": imputed})
    cat_cols = lambda ps: {k: np.concatenate([p[k] for p in ps]) for k in ps[0]}
    series = contracts.from_columns(cat_cols(parts), "series")
    calendar = contracts.from_columns(cat_cols(cal), "calendar")
    check(series)
    return series, calendar


def check(series: pd.DataFrame) -> None:
    """Spec acceptance: t contiguous per series, no NaN, one train -> test boundary."""
    bad = []
    for sid, g in series.groupby("series_id", sort=False, observed=True):
        t = g["t"].to_numpy()
        is_test = (g["split"] == "test").to_numpy()
        if not np.array_equal(t, np.arange(t.size)):
            bad.append((sid, "t not contiguous from 0"))
        if not np.isfinite(g["y"].to_numpy()).all():
            bad.append((sid, "non-finite y"))
        if is_test.any() and not is_test[np.argmax(is_test):].all():
            bad.append((sid, "test split is not one final block"))
    if bad:
        raise AcceptanceError("ingest", f"{len(bad)} series fail", pd.DataFrame(bad, columns=["series_id", "problem"]))


def split_boundary(series: pd.DataFrame) -> dict[str, int]:
    """{series_id: first test t}."""
    test = series[series["split"] == "test"]
    return {str(k): int(v) for k, v in test.groupby("series_id", observed=True)["t"].min().items()}
