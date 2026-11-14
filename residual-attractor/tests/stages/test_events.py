"""Stage events: rdiag's s3.events under v2. Residual events, each row against its own threshold."""

import re

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, events, tails
from tests.stages.test_tails import changed, fixture_build, grid_frames, three_series_grid


def thresholds_frame(R, u):
    """A tails_thresholds table holding the thresholds u[k, i] (NaN: the row has none) for the field R."""
    K, N, _ = R.shape
    kk, ii = np.meshgrid(np.arange(K), np.arange(N), indexing="ij")
    with np.errstate(invalid="ignore"):
        n = (np.abs(R) > u[:, :, None]).sum(axis=2)
    return {"tails_thresholds": contracts.from_columns({
        "k": kk.ravel(), "i": ii.ravel(), "u": [None if np.isnan(x) else 0 for x in u.ravel()], "u_star": u.ravel(), "n_exceed": n.ravel(),
    }, "tails_thresholds")}


def as_arrays(ev, shape, kind="residual"):
    """(event, sign, defined) as (K, N, P) arrays, from the table's own keys."""
    f = ev[ev["kind"] == kind].sort_values(["k", "i", "t"])
    return tuple(f[c].to_numpy().reshape(shape) for c in ("event", "sign", "defined"))


@pytest.fixture(scope="module")
def staged(cfg):
    frames = three_series_grid(cfg)
    tailed, _ = tails.run(frames, cfg)
    built, info = events.run(frames, tailed, cfg)
    return frames, tailed, built, info


def test_events_by_hand(cfg):
    x = np.array([0.5, -2.0, 1.0, 0.0, -1.0, 3.0])
    R = np.stack([x, x, x])[:, None, :]                              # three configurations, the same residuals
    b, info = events.run(grid_frames(R), thresholds_frame(R, np.array([[1.0], [2.5], [np.nan]])), cfg)
    ev = b["events_flags"]
    assert list(ev.columns) == ["k", "kind", "i", "t", "event", "sign", "defined"] and set(ev["kind"]) == {"residual"}
    event, sign, defined = as_arrays(ev, R.shape)
    assert event[:, 0].tolist() == [[False, True, False, False, False, True],      # above 1.0; a value on the threshold is not above it
                                    [False, False, False, False, False, True],     # above 2.5: its own threshold, not the first row's
                                    [False] * 6]                                   # no threshold, no events
    assert sign[:, 0].tolist() == [[1, -1, 1, 0, -1, 1]] * 3                       # the residual's sign, at every month
    assert defined[:, 0].tolist() == [[True] * 6, [True] * 6, [False] * 6]
    assert info["rows"]["residual"] == {"units": 3, "without_a_threshold": 1, "events": 3, "events_per_unit": {"min": 0, "median": 1.0, "max": 2}}


def test_events_are_exactly_the_months_beyond_each_rows_own_threshold(staged):
    frames, tailed, built, _ = staged
    R, months = tails.dense(frames)
    K, N, P = R.shape
    th = tailed["tails_thresholds"].sort_values(["k", "i"])
    u = th["u_star"].to_numpy().reshape(K, N)
    event, sign, defined = as_arrays(built["events_flags"], R.shape)
    np.testing.assert_array_equal(event, np.abs(R) > u[:, :, None])
    np.testing.assert_array_equal(event.sum(axis=2), th["n_exceed"].to_numpy().reshape(K, N))
    np.testing.assert_array_equal(sign, np.sign(R).astype(np.int8))
    assert defined.all() and len(built["events_flags"]) == K * N * P and sorted(np.unique(sign)) == [-1, 1]
    # "own" matters: within a series the thresholds differ by configuration, and another row's threshold gives other events
    assert (th.groupby("i")["u_star"].nunique() > K // 2).all()
    assert not np.array_equal(event, np.abs(R) > np.roll(u, 1, axis=0)[:, :, None])
    assert not np.array_equal(event, np.abs(R) > u.mean(axis=0)[None, :, None])


def test_a_row_without_a_threshold_is_undefined_and_has_no_events(cfg):
    rng = np.random.default_rng(21)
    R = np.stack([np.zeros(98), rng.standard_t(4, 98)])[None, :, :]
    frames = grid_frames(R)
    tailed, _ = tails.run(frames, cfg)
    b, info = events.run(frames, tailed, cfg)                         # the stage's own check passes
    event, sign, defined = as_arrays(b["events_flags"], R.shape)
    assert not defined[0, 0].any() and not event[0, 0].any() and (sign[0, 0] == 0).all()
    assert defined[0, 1].all() and event[0, 1].sum() == tailed["tails_thresholds"]["n_exceed"].iloc[1] > 0
    assert info["rows"]["residual"]["without_a_threshold"] == 1


def test_changing_one_configuration_leaves_every_other_row_bit_identical(staged, cfg):
    # The archive rule, through both stages: configuration 7's residuals change, so do its thresholds and its events, and nothing else.
    frames, _, built, _ = staged
    other = changed(frames, 7, 1.7)
    again, _ = events.run(other, tails.run(other, cfg)[0], cfg)
    x, y = built["events_flags"], again["events_flags"]
    keep = (x["k"] != 7).to_numpy()
    pd.testing.assert_frame_equal(x[keep].reset_index(drop=True), y[keep].reset_index(drop=True), check_exact=True)
    assert not np.array_equal(x.loc[~keep, "event"].to_numpy(), y.loc[~keep, "event"].to_numpy())


def test_rows_do_not_depend_on_which_configurations_and_series_are_present(staged, cfg):
    frames, _, built, _ = staged
    R, months = tails.dense(frames)
    keep_k, keep_i = [30, 3, 17], [2, 0]
    sub = grid_frames(R[np.ix_(keep_k, keep_i)], start=str(months[0])[:10])
    small, _ = events.run(sub, tails.run(sub, cfg)[0], cfg)
    full = built["events_flags"]
    for nk, k in enumerate(keep_k):
        for ni, i in enumerate(keep_i):
            x = small["events_flags"].query("k == @nk and i == @ni").drop(columns=["k", "i"]).reset_index(drop=True)
            y = full[(full["k"] == k) & (full["i"] == i)].drop(columns=["k", "i"]).reset_index(drop=True)
            pd.testing.assert_frame_equal(x, y, check_exact=True)


def _one(frame, col, value):
    out = frame.copy()
    out.loc[out.index[3], col] = value
    return out


@pytest.mark.parametrize("rule, corrupt", [
    ("an event implies defined", lambda f: f.assign(defined=False)),
    ("a residual event is |resid| above the row's own threshold", lambda f: _one(f, "event", not f["event"].iloc[3])),
    ("sign is the sign of the residual", lambda f: f.assign(sign=-f["sign"])),
    ("sign is the sign of the residual", lambda f: f.assign(sign=np.where(f["event"], f["sign"], np.int8(0)))),   # the sign is kept off events too
    ("defined is false exactly where the row has no threshold", lambda f: _one(f, "defined", False)),
])
def test_check_rules_fire_with_rows(staged, cfg, rule, corrupt):
    frames, tailed, built, _ = staged
    events.check(built, frames, tailed, cfg)                          # the clean output passes
    bad = {"events_flags": contracts.validate(corrupt(built["events_flags"]), "events_flags")}
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        events.check(bad, frames, tailed, cfg)
    rows = err.value.rows
    assert rows is not None and rows["problem"].str.contains(rule, regex=False).any() and {"k", "kind", "i", "t"} <= set(rows.columns)


def test_check_counts_events_against_the_thresholds_table_and_rows_against_the_grid(staged, cfg):
    frames, tailed, built, _ = staged
    th = tailed["tails_thresholds"]
    more = {"tails_thresholds": contracts.validate(th.assign(n_exceed=th["n_exceed"] + np.int32(1)), "tails_thresholds")}
    with pytest.raises(AcceptanceError, match="as many residual events as its threshold has exceedances"):
        events.check(built, frames, more, cfg)
    with pytest.raises(AcceptanceError, match=r"events_flags has \d+ rows"):
        events.check({"events_flags": built["events_flags"].iloc[1:].reset_index(drop=True)}, frames, tailed, cfg)


def test_the_thresholds_table_must_cover_the_field(staged, cfg):
    frames, tailed, _, _ = staged
    short = {"tails_thresholds": tailed["tails_thresholds"].iloc[1:].reset_index(drop=True)}
    with pytest.raises(AcceptanceError, match=r"one row per \(k, i\)"):
        events.run(frames, short, cfg)


def test_artifacts_round_trip(tmp_path, staged):
    *_, built, _ = staged
    f = built["events_flags"]
    pd.testing.assert_frame_equal(contracts.read(contracts.write(f, "events_flags", tmp_path / "flags.parquet"), "events_flags"), f)


def test_one_series_fixture_build(cfg):
    out, m = fixture_build(cfg)
    assert m["stages_passed"].index("events") == m["stages_passed"].index("tails") + 1
    K, P = m["configurations"]["admissible"], m["grid"]["rdiag_minimums"]["P"]
    a = m["artifacts"]["events/flags.parquet"]
    ev = contracts.read(out / "events/flags.parquet", a["artifact"])
    th = contracts.read(out / "tails/thresholds.parquet", "tails_thresholds")
    assert a["rows"] == len(ev) == K * P and m["events"]["kinds"] == ["residual"]
    assert ev["event"].sum() == th["n_exceed"].sum() == m["events"]["rows"]["residual"]["events"]
    assert set(m["events"]["not_built"]) == {"band_power", "persistence"}


@pytest.mark.parametrize("key, value, match", [
    ("events.kinds", [], "at least one"),
    ("events.kinds", ["residual", "residual"], "each once"),
    ("events.kinds", ["resid"], "events.kinds"),
    ("events.kinds", ["residual", "band_power"], "band_power is not built yet"),
    ("events.kinds", ["persistence"], r"waits for s2c\.summaries"),
    ("events.residual", "two_sigma", "not in"),
])
def test_events_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    validate_config(dict(c))
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)
