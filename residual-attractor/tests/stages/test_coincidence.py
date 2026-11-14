"""Stage coincidence: rdiag's s3.coincidence under v2. Events of one series followed by events of another, inside a configuration."""

import re
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.common import surrogates
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, coincidence, events, tails
from tests.stages.test_tails import changed, fixture_build, grid_frames, three_series_grid

KEYS = ["k", "kind_a", "i_a", "kind_b", "i_b", "delta_min", "delta_max"]
SINGLE_LAGS = [[lag, lag] for lag in range(13)]


def flags(E, D=None, kinds=("residual",)):
    """(grid tables, {"events_flags": ...}) for event arrays E[k, i, t], or E[k, kind, i, t] with several kinds.

    D marks the months each series is defined on (all of them unless given)."""
    E = np.asarray(E, dtype=bool)
    if E.ndim == 3:
        E = E[:, None]
    D = np.ones(E.shape, dtype=bool) if D is None else np.asarray(D, dtype=bool).reshape(E.shape)
    K, F, N, P = E.shape
    frames = grid_frames(np.zeros((K, N, P)))
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    kk, ff, ii, tt = (x.reshape(-1) for x in np.meshgrid(np.arange(K), np.arange(F), np.arange(N), np.arange(P), indexing="ij"))
    ev = contracts.from_columns({"k": kk, "kind": np.array(kinds, dtype=object)[ff], "i": ii, "t": months[tt], "event": E.reshape(-1),
                                 "sign": E.reshape(-1).astype(np.int8), "defined": D.reshape(-1)}, "events_flags")
    return frames, {"events_flags": ev}


def run(E, cfg, D=None, kinds=("residual",)):
    frames, evented = flags(E, D, kinds)
    built, info = coincidence.run(frames, evented, {**cfg, "events.kinds": list(kinds)})
    return built["coincidence_precursor"], info


def row(co, k, i_a, i_b, lo, hi, kind_a="residual", kind_b="residual"):
    r = co[(co["k"] == k) & (co["i_a"] == i_a) & (co["i_b"] == i_b) & (co["delta_min"] == lo) & (co["delta_max"] == hi)
           & (co["kind_a"] == kind_a) & (co["kind_b"] == kind_b)]
    assert len(r) <= 1
    return r.iloc[0] if len(r) else None


def by_loops(Ea, Eb, Db, lo, hi, offsets):
    """One test by plain loops and exact fractions: (n_eligible, rate, n_surrogates, p), or None without an eligible event."""
    P = len(Ea)

    def counts(eb, db):
        eligible = hit = 0
        for t in range(P):
            window = range(t + lo, t + hi + 1)
            if Ea[t] and window[-1] <= P - 1 and all(db[m] for m in window):
                eligible += 1
                hit += any(eb[m] for m in window)
        return hit, eligible

    hit, eligible = counts(Eb, Db)
    if eligible == 0:
        return None
    rate, used, at_least = Fraction(hit, eligible), 0, 0
    for o in offsets:                                       # the follower shifted: b[(t + o) mod P]
        h, n = counts([Eb[(t + o) % P] for t in range(P)], [Db[(t + o) % P] for t in range(P)])
        if n:
            used += 1
            at_least += Fraction(h, n) >= rate
    return eligible, rate, used, Fraction(1 + at_least, 1 + used)


def all_offsets(cfg, P):
    m = cfg["surrogates.circular_shift_min_offset"]
    return list(range(m, P - m + 1))


def assert_matches_loops(co, E, D, windows, offsets_of, kinds=("residual",)):
    """Every row the loops say exists is in the table with the same numbers, and the table has no other row."""
    E, D = np.asarray(E, dtype=bool), np.asarray(D, dtype=bool)
    if E.ndim == 3:
        E, D = E[:, None], D[:, None]
    K, F, N, P = E.shape
    expected = 0
    for k in range(K):
        for fa in range(F):
            for a in range(N):
                for fb in range(F):
                    for b in range(N):
                        if (fa, a) == (fb, b):
                            continue
                        for lo, hi in windows:
                            want = by_loops(E[k, fa, a], E[k, fb, b], D[k, fb, b], lo, hi, offsets_of(k, b))
                            got = row(co, k, a, b, lo, hi, kinds[fa], kinds[fb])
                            if want is None:
                                assert got is None
                                continue
                            expected += 1
                            assert got is not None, (k, a, b, lo, hi)
                            assert got["n_events_a"] == E[k, fa, a].sum() and got["n_eligible_a"] == want[0]
                            assert got["rate"] == float(want[1]) and got["n_surrogates"] == want[2] and got["p_value"] == float(want[3])
    assert len(co) == expected


# ---- by hand and against plain loops -------------------------------------------------------------

def test_rate_eligibility_and_defined_by_hand(cfg):
    c = {**cfg, "surrogates.circular_shift_min_offset": 2, "coincidence.windows": [[2, 2], [0, 2], [19, 19], [20, 25]]}
    P = 20
    a, b = np.zeros(P, bool), np.zeros(P, bool)
    a[[3, 17, 19]], b[[5]] = True, True
    co, info = run(np.stack([a, b])[None], c)
    r = row(co, 0, 0, 1, 2, 2)
    # the events at 3 and 17 have month t + 2 inside the sample, the one at 19 does not; only 3 is followed (5)
    assert (r["n_events_a"], r["n_eligible_a"], r["rate"]) == (3, 2, 0.5)
    r = row(co, 0, 0, 1, 0, 2)                              # windows 3..5 and 17..19; 19..21 runs past the sample
    assert (r["n_eligible_a"], r["rate"]) == (2, 0.5)
    assert row(co, 0, 0, 1, 19, 19) is None                 # no event of a has month t + 19 inside the sample ...
    assert row(co, 0, 1, 0, 19, 19) is None and row(co, 0, 0, 1, 20, 25) is None   # ... and no window longer than the sample has rows
    r = row(co, 0, 1, 0, 2, 2)                              # the other direction: b's one event at 5, a has none at 7
    assert (r["n_events_a"], r["n_eligible_a"], r["rate"], r["p_value"]) == (1, 1, 0.0, 1.0)   # every shift does at least as well as 0
    assert info["null"]["mode"] == "enumerated" and info["null"]["n"] == 17 and set(co["n_surrogates"]) == {17}
    # the follower undefined on months 18 and 19: the window of a's event at 17 (month 19) is no longer wholly defined
    D = np.ones((1, 2, P), bool)
    D[0, 1, 18:] = False
    co, _ = run(np.stack([a, b])[None], c, D)
    r = row(co, 0, 0, 1, 2, 2)
    assert (r["n_events_a"], r["n_eligible_a"], r["rate"]) == (3, 1, 1.0)
    assert_matches_loops(co, np.stack([a, b])[None], D, c["coincidence.windows"], lambda k, b: all_offsets(c, P))


def test_every_row_matches_plain_loops(cfg):
    rng = np.random.default_rng(31)
    K, N, P = 2, 4, 40
    c = {**cfg, "surrogates.circular_shift_min_offset": 5, "coincidence.windows": [[0, 0], [1, 1], [3, 3], [0, 2], [2, 5], [30, 30]]}
    E = rng.random((K, N, P)) < 0.25
    E[1, 2] = False                                          # a series without events leads nothing
    D = np.ones((K, N, P), bool)
    D[:, 1, :9] = False                                      # a series undefined before its first full window
    D[0, 3, rng.choice(P, 6, replace=False)] = False         # and one with holes
    E &= D
    co, info = run(E, c, D)
    assert_matches_loops(co, E, D, c["coincidence.windows"], lambda k, b: all_offsets(c, P))
    assert row(co, 1, 2, 0, 0, 0) is None and row(co, 1, 0, 2, 0, 0)["rate"] == 0.0
    assert co["n_surrogates"].min() < info["null"]["n"] == 31   # some shifts leave a without an eligible event; they are not counted


def test_two_kinds_pair_across_kinds_and_never_with_themselves(cfg):
    rng = np.random.default_rng(32)
    K, N, P = 1, 2, 36
    c = {**cfg, "surrogates.circular_shift_min_offset": 4, "coincidence.windows": [[0, 0], [1, 2]]}
    E = rng.random((K, 2, N, P)) < 0.3
    D = np.ones(E.shape, bool)
    D[0, 1, :, :11] = False                                  # the second kind starts later, as a windowed feature would
    E &= D
    kinds = ("residual", "persistence")
    co, info = run(E, c, D, kinds)
    assert info["event_series_per_configuration"] == 4 and info["ordered_pairs_per_configuration"] == 12
    assert_matches_loops(co, E, D, c["coincidence.windows"], lambda k, b: all_offsets(c, P), kinds)
    assert row(co, 0, 0, 0, 0, 0, "residual", "persistence") is not None    # one series, two kinds: a pair
    assert not ((co["kind_a"] == co["kind_b"]) & (co["i_a"] == co["i_b"])).any()
    # drawn: a follower's draws are keyed by its series, whatever its kind (rdiag: one recipe per series and draw)
    d = {**c, "surrogates.n_coincidence": 9}
    co, info = run(E, d, D, kinds)
    assert info["null"]["mode"] == "drawn" and info["null"]["n"] == 9
    assert_matches_loops(co, E, D, d["coincidence.windows"], lambda k, b: surrogates.offsets(d, "coincidence", P, 9, k, b).tolist(), kinds)


def test_drawn_surrogates_are_the_shared_recipes(cfg):
    rng = np.random.default_rng(33)
    K, N, P = 2, 3, 98
    E = rng.random((K, N, P)) < 0.2
    E[1] = E[0]                                              # two configurations with the same events
    c = {**cfg, "surrogates.n_coincidence": 20, "coincidence.windows": [[0, 0], [2, 2], [0, 2]]}   # fewer than the 75 offsets: drawn
    co, info = run(E, c)
    assert info["null"] == {"mode": "drawn", "n": 20, "requested": 20, "distinct_offsets": 75, "smallest_p_value": 1 / 21,
                            "shift": "the follower's events and defined, b[(t + o) mod P]"}
    drawn = lambda k, b: surrogates.offsets(c, "coincidence", P, 20, k, b).tolist()   # each follower row's own draws
    assert_matches_loops(co, E, np.ones(E.shape, bool), c["coincidence.windows"], drawn)
    p = co.pivot_table(index=KEYS[1:], columns="k", values="p_value")
    assert (p[0] != p[1]).any()                              # per configuration: their own draws
    shared, _ = run(E, {**c, "surrogates.scope": "shared"})
    p = shared.pivot_table(index=KEYS[1:], columns="k", values="p_value")
    assert (p[0] == p[1]).all()


# ---- known answers --------------------------------------------------------------------------------

@pytest.mark.parametrize("L", [0, 1, 3, 12])
def test_events_planted_L_months_after_another_series(cfg, L):
    # Forty planted pairs per lag, so that what is asserted about chance (the reverse direction, the other lags)
    # is a share over many draws and not the luck of one seed.
    P, n, seeds = 98, 16, 40
    c = {**cfg, "coincidence.windows": SINGLE_LAGS + [[0, 2]]}
    reverse = []
    for seed in range(seeds):
        rng = np.random.default_rng([40, L, seed])
        a = np.zeros(P, bool)
        a[rng.choice(P - 12, n, replace=False)] = True       # none in the last year, so every planted follower is in the sample
        b = np.roll(a, L)                                    # b's events are a's, L months later
        other = rng.random(P) < n / P                        # an unrelated series in the same field
        co, info = run(np.stack([a, b, other])[None], c)
        smallest = info["null"]["smallest_p_value"]
        assert smallest == 1 / 76 and info["null"]["mode"] == "enumerated"
        hit = row(co, 0, 0, 1, L, L)
        assert hit["rate"] == 1.0 and hit["p_value"] == smallest             # every event followed, and no shift of b does as well
        if L <= 2:
            wide = row(co, 0, 0, 1, 0, 2)
            assert wide["rate"] == 1.0 and wide["p_value"] == smallest
        if L > 0:
            reverse.append(row(co, 0, 1, 0, L, L))           # b's events followed by a's L months later: nothing planted
        base = b.mean()
        others = co[(co["i_a"] == 0) & (co["i_b"] == 1) & (co["delta_min"] == co["delta_max"]) & (co["delta_min"] != L)]
        assert len(others) == 12                             # the other lags sit near b's base rate
        assert (others["rate"] <= base + 4 * np.sqrt(base * (1 - base) / others["n_eligible_a"])).all()
        assert abs(others["rate"].mean() - base) < 0.12 and others["p_value"].median() > 0.05
        assert (co["p_value"] >= smallest).all()
    if L > 0:
        back = pd.DataFrame(reverse)
        assert (back["p_value"] <= 0.05).mean() <= 0.125 and back["rate"].mean() < 0.3   # the reverse direction is not significant


def test_independent_event_series_reject_at_about_the_nominal_rate(cfg):
    rng = np.random.default_rng(50)
    N, P = 30, 300
    c = {**cfg, "coincidence.windows": [[0, 0], [1, 1], [6, 6], [0, 2]]}
    co, info = run((rng.random((1, N, P)) < 0.2), c)
    assert len(co) == N * (N - 1) * 4 and info["null"]["n"] == 277
    p = co["p_value"]
    assert ((p > 0) & (p <= 1)).all() and p.min() >= 1 / 278
    # At most the nominal rate, and below it by the ties: a rate is a count over about 60 events, so a shifted series
    # often gives exactly the observed rate, and ">=" counts those against the test.
    assert 0.02 < (p <= 0.05).mean() <= 0.05 and 0.05 < (p <= 0.10).mean() <= 0.10 and 0.50 < p.mean() < 0.57


def test_the_null_keeps_each_series_own_clustering(cfg):
    # Independent series whose events come in bursts. Shifting keeps the bursts, so they are not mistaken for procession;
    # judged against events scattered at the same rate, the same tests reject several times too often.
    rng = np.random.default_rng(51)
    N, P = 30, 300
    E = np.zeros((1, N, P), bool)
    for i in range(N):
        on = False
        for t in range(P):
            on = rng.random() < (0.8 if on else 0.06)
            E[0, i, t] = on
    c = {**cfg, "coincidence.windows": [[0, 0], [1, 1], [6, 6], [0, 2]]}
    co, _ = run(E, c)
    assert 0.03 < (co["p_value"] <= 0.05).mean() < 0.07
    single = co[co["delta_min"] == co["delta_max"]]
    base = E[0].mean(axis=1)[single["i_b"].to_numpy()]
    z = (single["rate"] - base) / np.sqrt(base * (1 - base) / single["n_eligible_a"])   # as if b's months were independent draws
    assert (z > 1.645).mean() > 0.12


# ---- inside one configuration ---------------------------------------------------------------------

@pytest.mark.parametrize("n_draws", [1000, 20])   # every offset once, and drawn
def test_changing_one_configuration_leaves_every_other_row_bit_identical(cfg, n_draws):
    rng = np.random.default_rng(60)
    c = {**cfg, "surrogates.n_coincidence": n_draws}
    E = rng.random((3, 4, 98)) < 0.2
    before, _ = run(E, c)
    E2 = E.copy()
    E2[1] = rng.random((4, 98)) < 0.3                         # configuration 1's events change
    after, _ = run(E2, c)
    keep_b, keep_a = (before["k"] != 1).to_numpy(), (after["k"] != 1).to_numpy()
    pd.testing.assert_frame_equal(before[keep_b].reset_index(drop=True), after[keep_a].reset_index(drop=True), check_exact=True)
    assert not before[~keep_b].reset_index(drop=True).equals(after[~keep_a].reset_index(drop=True))


@pytest.mark.parametrize("n_draws", [1000, 20])
def test_adding_a_series_or_a_configuration_leaves_the_existing_rows_unchanged(cfg, n_draws):
    rng = np.random.default_rng(61)
    c = {**cfg, "surrogates.n_coincidence": n_draws}
    E = rng.random((3, 5, 98)) < 0.2
    full, _ = run(E, c)
    fewer_series, _ = run(E[:, :4], c)
    sub = full[(full["i_a"] < 4) & (full["i_b"] < 4)].reset_index(drop=True)
    pd.testing.assert_frame_equal(fewer_series, sub, check_exact=True)
    fewer_configs, _ = run(E[:2], c)
    pd.testing.assert_frame_equal(fewer_configs, full[full["k"] < 2].reset_index(drop=True), check_exact=True)


def test_one_series_gives_a_valid_empty_table(cfg, tmp_path):
    co, info = run(np.random.default_rng(62).random((2, 1, 98)) < 0.2, cfg)
    assert len(co) == 0 and list(co.columns) == KEYS + ["n_events_a", "n_eligible_a", "rate", "n_surrogates", "p_value"]
    assert info["tests"] == 0 and info["ordered_pairs_per_configuration"] == 0 and info["null"].startswith("no pair")
    back = contracts.read(contracts.write(co, "coincidence_precursor", tmp_path / "precursor.parquet"), "coincidence_precursor")
    pd.testing.assert_frame_equal(back, co)
    short, _ = run(np.zeros((1, 1, 10), bool), cfg)           # too short for any shift, but nothing to test either
    assert len(short) == 0


def test_a_sample_too_short_for_any_shift_stops_the_stage(cfg):
    with pytest.raises(AcceptanceError, match="coincidence: no circular shift exists"):
        run(np.random.default_rng(63).random((1, 2, 20)) < 0.3, cfg)      # 20 months, offsets must lie in [12, 8]


# ---- the stage after tails and events -------------------------------------------------------------

@pytest.fixture(scope="module")
def staged(cfg):
    frames = three_series_grid(cfg)
    tailed, _ = tails.run(frames, cfg)
    evented, _ = events.run(frames, tailed, cfg)
    built, info = coincidence.run(frames, evented, cfg)
    return frames, evented, built, info


def test_tests_on_three_series(staged, cfg):
    frames, evented, built, info = staged
    co = built["coincidence_precursor"]
    K, N, P = len(frames["grid_config"]), 3, len(frames["grid_month"])
    assert len(co) == info["tests"] == info["tests_possible"] == K * N * (N - 1) * 14
    assert set(map(tuple, co[["delta_min", "delta_max"]].drop_duplicates().to_numpy().tolist())) == {(lag, lag) for lag in range(13)} | {(0, 2)}
    assert info["null"]["n"] == P - 2 * cfg["surrogates.circular_shift_min_offset"] + 1 == 145 and set(co["n_surrogates"]) == {145}
    assert ((co["p_value"] > 0) & (co["p_value"] <= 1)).all() and co["p_value"].min() >= 1 / 146
    ev = evented["events_flags"]
    counts = ev[ev["event"]].groupby(["k", "i"]).size()
    assert (co["n_events_a"].to_numpy() == counts.reindex(list(zip(co["k"], co["i_a"]))).to_numpy()).all()
    months = np.sort(ev["t"].unique())
    E = ev.sort_values(["k", "i", "t"])["event"].to_numpy().reshape(K, N, P)
    for r in co.sample(40, random_state=64).itertuples():     # a sample of rows against the loops
        want = by_loops(E[r.k, r.i_a], E[r.k, r.i_b], np.ones(P, bool), r.delta_min, r.delta_max, all_offsets(cfg, P))
        assert (r.n_eligible_a, r.rate, r.n_surrogates, r.p_value) == (want[0], float(want[1]), want[2], float(want[3]))
    assert months.size == P


def test_changing_one_configurations_residuals_leaves_every_other_row_bit_identical(staged, cfg):
    # The archive rule through all three stages: other residuals for configuration 7 give it other thresholds, other events
    # and other tests, and leave every row of every other configuration as it was.
    frames, _, built, _ = staged
    other = changed(frames, 7, 1.7)
    again, _ = coincidence.run(other, events.run(other, tails.run(other, cfg)[0], cfg)[0], cfg)
    x, y = built["coincidence_precursor"], again["coincidence_precursor"]
    pd.testing.assert_frame_equal(x[x["k"] != 7].reset_index(drop=True), y[y["k"] != 7].reset_index(drop=True), check_exact=True)
    assert not x[x["k"] == 7].reset_index(drop=True).equals(y[y["k"] == 7].reset_index(drop=True))


def _first(frame, **values):
    out = frame.copy()
    for col, value in values.items():
        out.loc[out.index[0], col] = value
    return out


@pytest.mark.parametrize("rule, corrupt", [
    ("a series is never paired with itself", lambda f: _first(f, i_b=f["i_a"].iloc[0])),
    ("n_events_a counts the events of the leading series", lambda f: f.assign(n_events_a=f["n_events_a"] + np.int32(1))),
    ("n_eligible_a counts the leading events whose whole window is inside the sample", lambda f: _first(f, n_eligible_a=f["n_eligible_a"].iloc[0] + 1)),
    ("a row exists only where the leading series has an eligible event", lambda f: _first(f, n_eligible_a=0)),
    ("rate is a share of the eligible events, between 0 and 1", lambda f: _first(f, rate=1.5)),
    ("rate is a share of the eligible events, between 0 and 1", lambda f: f.assign(rate=f["rate"] * 0.999 + 0.0004)),
    ("n_surrogates lies between 1 and the surrogates the null holds", lambda f: f.assign(n_surrogates=np.int32(1000))),
    ("n_surrogates lies between 1 and the surrogates the null holds", lambda f: _first(f, n_surrogates=0, p_value=1.0)),
    ("p_value is (1 + a count) / (1 + n_surrogates), in (0, 1]", lambda f: f.assign(p_value=f["p_value"] / 3)),
    ("p_value is (1 + a count) / (1 + n_surrogates), in (0, 1]", lambda f: _first(f, p_value=0.0)),
    ("does not exist", lambda f: _first(f, delta_max=99)),
    ("does not exist", lambda f: _first(f, k=999)),
    ("1 tests with eligible events have no row", lambda f: f.iloc[1:].reset_index(drop=True)),
])
def test_check_rules_fire(staged, cfg, rule, corrupt):
    frames, evented, built, _ = staged
    coincidence.check(built, frames, evented, cfg)            # the clean output passes
    bad = {"coincidence_precursor": contracts.validate(corrupt(built["coincidence_precursor"]), "coincidence_precursor")}
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        coincidence.check(bad, frames, evented, cfg)
    if "have no row" not in rule:
        rows = err.value.rows
        assert rows is not None and set(KEYS) <= set(rows.columns) and len(rows) >= 1


def test_the_events_table_must_cover_the_field(staged, cfg):
    frames, evented, _, _ = staged
    short = {"events_flags": evented["events_flags"].iloc[1:].reset_index(drop=True)}
    with pytest.raises(AcceptanceError, match=r"one per \(k, kind, i, t\)"):
        coincidence.run(frames, short, cfg)


def test_artifact_round_trip(tmp_path, staged):
    *_, built, _ = staged
    f = built["coincidence_precursor"]
    pd.testing.assert_frame_equal(contracts.read(contracts.write(f, "coincidence_precursor", tmp_path / "precursor.parquet"), "coincidence_precursor"), f)


def test_one_series_fixture_build(cfg):
    out, m = fixture_build(cfg)
    assert m["stages_passed"][-3:] == ["tails", "events", "coincidence"]
    a = m["artifacts"]["coincidence/precursor.parquet"]
    co = contracts.read(out / "coincidence/precursor.parquet", a["artifact"])
    assert a["rows"] == len(co) == 0 and m["coincidence"]["tests"] == 0 and m["coincidence"]["event_series_per_configuration"] == 1
    assert m["coincidence"]["windows"] == SINGLE_LAGS + [[0, 2]]


@pytest.mark.parametrize("key, value, match", [
    ("coincidence.windows", [], "coincidence.windows"),
    ("coincidence.windows", [[0, 0], [0, 0]], "coincidence.windows"),
    ("coincidence.windows", [[2, 1]], "coincidence.windows"),
    ("coincidence.windows", [[0]], "coincidence.windows"),
    ("coincidence.windows", [[-1, 0]], "coincidence.windows"),
    ("coincidence.windows", [[0, 1.5]], "coincidence.windows"),
    ("coincidence.windows", [0, 2], "coincidence.windows"),
    ("coincidence.direction", "trigger", "not in"),
    ("surrogates.n_coincidence", 0, "surrogates.n_coincidence"),
])
def test_coincidence_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    assert validate_config(dict(c))["coincidence.windows"] == SINGLE_LAGS + [[0, 2]]   # the default: lags 0 to 12 and rdiag's [0, 2]
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)
