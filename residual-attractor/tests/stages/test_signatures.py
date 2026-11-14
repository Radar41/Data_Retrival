"""Signatures: rdiag's Stage 3 signatures under v2, inside each configuration. Consolidation only."""

import json
import re

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, common_mode, signatures
from tests.stages.test_common_mode import grid_of, staged  # noqa: F401  (staged is a fixture)

NAN = np.nan
PERSIST = "signatures.persistence_months"
REQUIRES = "signatures.consolidation_requires"


def month_table(lambda1, band, absorption, start="2015-01-01"):
    """A common_mode_month table from arrays over (k, month), NaN where a month is undefined."""
    lambda1, band, absorption = (np.atleast_2d(np.asarray(a, dtype=np.float64)) for a in (lambda1, band, absorption))
    K, P = lambda1.shape
    months = pd.date_range(start, periods=P, freq="MS").to_numpy()
    d = np.isfinite(lambda1).reshape(-1)
    return {"common_mode_month": contracts.from_columns({
        "k": np.repeat(np.arange(K), P), "t": np.tile(months, K), "lambda1": lambda1.reshape(-1), "lambda1_q": band.reshape(-1),
        "p_value": np.where(d, 0.5, NAN), "n_surrogates": np.where(d, 10, 0), "mp_edge": np.full(K * P, 2.0),
        "absorption_ratio": absorption.reshape(-1), "vector_turnover": np.full(K * P, NAN),
    }, "common_mode_month")}


def flags(common, cfg, **over):
    built, info = signatures.run(common, {**cfg, **over})
    f = built["signatures_flag"].sort_values(["k", "t"])
    K = f["k"].nunique()
    return f, {c: f[c].to_numpy().reshape(K, len(f) // max(K, 1)) for c in ("available", "held_months", "flagged")}, info


def rising_from(P, first, last, level=0.5, step=0.01):
    """An absorption path that is level, rises every month from `first` to `last`, then falls every month."""
    t = np.arange(P)
    return level + step * (np.clip(t, first - 1, last) - (first - 1)) - step * np.clip(t - last, 0, None)


# ---- the rule ------------------------------------------------------------------------------------

def test_a_flag_is_raised_after_persistence_months_in_a_row_and_not_before(cfg):
    P = 30
    lam = np.where(np.arange(P) >= 8, 3.0, 1.5)                 # above the band of 2 from month 8
    lam[:3] = NAN                                               # no full window yet
    A = rising_from(P, 10, 20)                                  # absorption rises in months 10..20
    A[:3] = NAN
    f, c, _ = flags(month_table(lam, np.where(np.isnan(lam), NAN, 2.0), A), cfg)
    n = cfg[PERSIST]                                            # 6
    assert c["held_months"][0].tolist() == [0] * 10 + list(range(1, 12)) + [0] * 9     # the rule holds in months 10..20
    assert c["flagged"][0].nonzero()[0].tolist() == list(range(10 + n - 1, 21))        # from the sixth month of the run
    assert not c["flagged"][0, : 10 + n - 1].any()                                     # five months in a row raise nothing
    assert set(f["mode"]) == {"consolidation"} and (f["i"] == -1).all()


def test_a_run_that_breaks_starts_again(cfg):
    P = 30
    lam, band = np.full(P, 3.0), np.full(P, 2.0)
    A = 0.5 + 0.01 * np.arange(P)                               # rising every month
    dip, below, gap = A.copy(), lam.copy(), A.copy()
    dip[8] = dip[7] - 0.005                                     # one month the absorption falls (and month 9 rises again from the dip)
    below[8] = 1.9                                              # one month below the band
    gap[8] = NAN                                                # one month undefined: months 8 and 9 cannot be read
    lam3 = np.stack([lam, below, lam])
    f, c, _ = flags(month_table(lam3, np.full((3, P), 2.0), np.stack([dip, A, gap])), cfg)
    assert c["held_months"][0].tolist() == [0] + list(range(1, 8)) + [0] + list(range(1, 22))
    assert c["held_months"][1].tolist() == [0] + list(range(1, 8)) + [0] + list(range(1, 22))
    assert c["held_months"][2].tolist() == [0] + list(range(1, 8)) + [0, 0] + list(range(1, 21))
    assert c["available"][2].tolist() == [False] + [True] * 7 + [False, False] + [True] * 20 and c["available"][0, 1:].all()
    for k, restart in ((0, 9), (1, 9), (2, 10)):
        assert c["flagged"][k].nonzero()[0].tolist() == [6, 7] + list(range(restart + 5, P))   # months 1..7, then six more from the restart


def test_equal_is_not_rising_and_touching_the_band_is_not_above(cfg):
    P = 12
    A = 0.5 + 0.01 * np.arange(P)
    level = A.copy()
    level[6] = level[5]                                         # month 6 equals month 5 (and month 7 still rises)
    lam = np.full(P, 3.0)
    touch = lam.copy()
    touch[6] = 2.0                                              # month 6 sits exactly on the band
    f, c, _ = flags(month_table(np.stack([lam, touch]), np.full((2, P), 2.0), np.stack([level, A])), cfg, **{PERSIST: 1})
    assert c["held_months"][0].tolist() == [0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5]
    assert c["held_months"][1].tolist() == [0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5]
    assert (c["flagged"] == (c["held_months"] >= 1)).all()      # persistence 1: every month the rule holds


def test_components_are_the_metrics_the_rule_read_by_name_and_value(cfg, rng):
    K, P = 3, 20
    lam, band, A = rng.uniform(1, 5, (K, P)), rng.uniform(1, 5, (K, P)), rng.uniform(0.2, 0.9, (K, P))
    lam[:, :4] = band[:, :4] = A[:, :4] = NAN
    common = month_table(lam, band, A)
    f, c, _ = flags(common, cfg)
    comp = [json.loads(s) for s in f["components"]]
    assert all(list(d) == ["absorption_ratio", "absorption_ratio_prev", "lambda1", "lambda1_q"] for d in comp)
    val = lambda name: np.array([NAN if d[name] is None else d[name] for d in comp]).reshape(K, P)
    np.testing.assert_array_equal(val("lambda1"), lam)          # the very numbers common_mode wrote, nulls where it has none
    np.testing.assert_array_equal(val("lambda1_q"), band)
    np.testing.assert_array_equal(val("absorption_ratio"), A)
    prev = np.concatenate([np.full((K, 1), NAN), A[:, :-1]], axis=1)   # the month before, of the same configuration
    np.testing.assert_array_equal(val("absorption_ratio_prev"), prev)
    assert f["components"].iloc[0] == '{"absorption_ratio":null,"absorption_ratio_prev":null,"lambda1":null,"lambda1_q":null}'
    assert (c["available"] == (np.arange(P) >= 5)).all()        # month 4 has no month before it to rise from
    with np.errstate(invalid="ignore"):
        holds = (lam > band) & (A > prev)
    assert ((c["held_months"] > 0) == holds).all() and not (c["flagged"] & ~c["available"]).any()


def test_the_requirements_the_kinds_and_the_persistence_come_from_the_config(cfg):
    P = 16
    lam, band = np.where(np.arange(P) >= 4, 3.0, 1.0), np.full(P, 2.0)   # above the band from month 4
    A = np.where(np.arange(P) % 2 == 0, 0.6, 0.5)                         # up, down, up, down
    common = month_table(lam, band, A)
    f, c, info = flags(common, cfg, **{REQUIRES: ["lambda1_above_band"]})
    assert c["held_months"][0].tolist() == [0] * 4 + list(range(1, 13)) and c["flagged"][0].nonzero()[0].tolist() == list(range(9, P))
    assert json.loads(f["components"].iloc[5]) == {"lambda1": 3.0, "lambda1_q": 2.0} and c["available"].all()
    assert info["consolidation"]["requires"] == ["lambda1_above_band"]
    f, c, _ = flags(common, cfg, **{REQUIRES: ["absorption_rising"], PERSIST: 1})
    assert c["flagged"][0].nonzero()[0].tolist() == [2, 4, 6, 8, 10, 12, 14]
    assert json.loads(f["components"].iloc[2]) == {"absorption_ratio": 0.6, "absorption_ratio_prev": 0.5}
    f, c, _ = flags(common, cfg)                                # both: above the band and rising never last two months
    assert c["held_months"][0].max() == 1 and not c["flagged"].any()
    f, _, info = flags(common, cfg, **{"signatures.kinds": []})  # no kind asked for: a valid empty table
    assert len(f) == 0 and info["kinds"] == [] and list(f.columns) == [x["name"] for x in contracts.load_schema("signatures_flag")["columns"]]


def test_the_order_of_the_rows_read_does_not_matter(cfg, rng):
    lam = rng.uniform(1.5, 4, (3, 25))
    A = 0.4 + np.cumsum(rng.choice([0.01, -0.01], (3, 25), p=[0.8, 0.2]), axis=1)
    common = month_table(lam, np.full((3, 25), 2.5), A)
    shuffled = {"common_mode_month": common["common_mode_month"].sample(frac=1.0, random_state=4).reset_index(drop=True)}
    a, b = signatures.run(common, cfg)[0]["signatures_flag"], signatures.run(shuffled, cfg)[0]["signatures_flag"]
    assert a["held_months"].max() >= 3
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    signatures.check({"signatures_flag": a.sample(frac=1.0, random_state=5)}, shuffled, cfg)   # nor the order of the rows checked


# ---- from the grid: a planted factor, the archive rule, one series ------------------------------

def test_a_common_factor_switched_on_is_flagged_after_persistence_months_and_not_before(cfg):
    K, N, P, T0, rho = 3, 10, 144, 72, 0.7
    rng = np.random.default_rng(1)
    R, factor = rng.standard_normal((K, N, P)), rng.standard_normal((K, 1, P))
    R[:, :, T0:] = np.sqrt(rho) * factor[:, :, T0:] + np.sqrt(1 - rho) * R[:, :, T0:]   # every series, from month T0
    small = {**cfg, "surrogates.n_common_mode": 200}
    common, _ = common_mode.run(grid_of(R), small)
    f, c, _ = flags(common, small)
    w, n = cfg["common_mode.window"], cfg[PERSIST]
    mo = common["common_mode_month"].sort_values(["k", "t"])
    lam, band, A = (mo[x].to_numpy().reshape(K, P) for x in ("lambda1", "lambda1_q", "absorption_ratio"))
    for k in range(K):
        assert lam[k, T0 + w - 1 :].mean() == pytest.approx(1 + (N - 1) * rho, rel=0.10)   # every series planted: 1 + (N - 1) rho
        first = int(np.argmax(c["flagged"][k]))
        assert c["flagged"][k].any() and T0 + n - 1 <= first < T0 + w                 # while the window fills with the factor
        assert c["held_months"][k, first - n + 1 : first + 1].tolist() == list(range(1, n + 1))
        run = slice(first - n + 1, first + 1)                                          # the six months that raised it
        assert (lam[k, run] > band[k, run]).all() and (np.diff(A[k, first - n : first + 1]) > 0).all()
        assert not c["flagged"][k, :first].any() and not c["flagged"][k, :T0].any()   # nothing before the sixth month, nothing before the factor
    assert (c["flagged"] == (c["held_months"] >= n)).all()


def test_changing_one_configuration_leaves_every_other_row_bit_identical(cfg, rng):
    K, N, P = 4, 6, 70
    R = rng.standard_normal((K, N, P)) + 0.6 * rng.standard_normal((K, 1, P))
    small = {**cfg, "surrogates.n_common_mode": 60}
    base = signatures.run(common_mode.run(grid_of(R), small)[0], small)[0]["signatures_flag"]
    R2 = R.copy()
    R2[1] = rng.standard_normal((N, P)) + 2.0 * rng.standard_normal((1, P))
    other = signatures.run(common_mode.run(grid_of(R2), small)[0], small)[0]["signatures_flag"]
    pd.testing.assert_frame_equal(base[base["k"] != 1].reset_index(drop=True), other[other["k"] != 1].reset_index(drop=True), check_exact=True)
    assert not base[base["k"] == 1].reset_index(drop=True).equals(other[other["k"] == 1].reset_index(drop=True))
    # and in the table itself: each configuration's month before is its own
    lam, A = rng.uniform(2.5, 4, (3, 20)), np.sort(rng.uniform(0.3, 0.9, (3, 20)), axis=1)
    one = flags(month_table(lam, np.full((3, 20), 2.0), A), cfg)[0]
    A2 = A.copy()
    A2[1] = A2[1][::-1]
    two = flags(month_table(lam, np.full((3, 20), 2.0), A2), cfg)[0]
    pd.testing.assert_frame_equal(one[one["k"] != 1].reset_index(drop=True), two[two["k"] != 1].reset_index(drop=True), check_exact=True)
    assert one[one["k"] == 2]["flagged"].sum() == 20 - 1 - 5 and two[two["k"] == 1]["flagged"].sum() == 0


def test_one_series_gives_rows_that_are_not_available(cfg, rng):
    K, P = 3, 40
    common, _ = common_mode.run(grid_of(rng.standard_normal((K, 1, P))), cfg)
    f, c, _ = flags(common, cfg)
    assert len(f) == K * P and not c["available"].any() and not c["flagged"].any() and (c["held_months"] == 0).all()
    assert set(f["components"]) == {'{"absorption_ratio":null,"absorption_ratio_prev":null,"lambda1":null,"lambda1_q":null}'}


def test_the_stage_on_a_three_series_grid(staged):  # noqa: F811
    frames, built, _, small = staged
    f, c, info = flags(built, small)
    K, P, w = len(frames["grid_config"]), len(frames["grid_month"]), small["common_mode.window"]
    assert len(f) == K * P and set(f["k"]) == set(range(K)) and set(f["t"]) == set(frames["grid_month"]["t"])
    assert (c["available"] == (np.arange(P) >= w)).all()         # from the month after the first full window
    assert (c["flagged"] == (c["held_months"] >= small[PERSIST])).all() and info["kinds"] == ["consolidation"]
    mo = built["common_mode_month"].sort_values(["k", "t"])
    lam, band, A = (mo[x].to_numpy().reshape(K, P) for x in ("lambda1", "lambda1_q", "absorption_ratio"))
    with np.errstate(invalid="ignore"):
        holds = (lam[:, 1:] > band[:, 1:]) & (A[:, 1:] > A[:, :-1])
    assert ((c["held_months"][:, 1:] > 0) == holds).all()


# ---- acceptance ----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clean(cfg):
    rng = np.random.default_rng(3)
    K, P = 3, 30
    lam, band = rng.uniform(1.5, 4.5, (K, P)), np.full((K, P), 2.5)
    A = 0.4 + np.cumsum(np.where(rng.random((K, P)) < 0.8, 0.01, -0.01), axis=1)
    lam[:, :5] = band[:, :5] = A[:, :5] = NAN
    lam[0, 10:] = 4.0                                            # configuration 0 stays above the band: it gets flagged
    A[0] = 0.4 + 0.01 * np.arange(P)
    A[0, :5] = NAN
    common = month_table(lam, band, A)
    built, _ = signatures.run(common, cfg)
    assert built["signatures_flag"]["flagged"].sum() > 0
    return common, built


def _flag(b, **cols):
    return {"signatures_flag": b["signatures_flag"].assign(**cols)}


def _edit_components(b, edit):
    f = b["signatures_flag"]
    return {"signatures_flag": f.assign(components=pd.array([json.dumps(edit(json.loads(s)), sort_keys=True, separators=(",", ":")) for s in f["components"]], dtype="string"))}


def _double_lambda1(d):
    return {**d, "lambda1": None if d["lambda1"] is None else 2.0 * d["lambda1"]}


@pytest.mark.parametrize("rule, corrupt", [
    ("components name every metric the rule read, and no other", lambda b: _edit_components(b, lambda d: {k: v for k, v in d.items() if k != "lambda1_q"})),
    ("components name every metric the rule read, and no other", lambda b: _edit_components(b, lambda d: {**d, "p_value": 0.5})),
    ("components carry the values common_mode wrote for the same configuration", lambda b: _edit_components(b, _double_lambda1)),
    ("consolidation is about all series together: i = -1", lambda b: _flag(b, i=np.int32(0))),
    ("available exactly where every metric the rule read is defined", lambda b: _flag(b, available=True)),
    ("held_months counts the months in a row on which the rule held", lambda b: _flag(b, held_months=b["signatures_flag"]["held_months"] + np.int32(1))),
    ("flagged exactly where the rule has held signatures.persistence_months months in a row", lambda b: _flag(b, flagged=b["signatures_flag"]["held_months"] >= 5)),
    ("a row that is not available is not flagged", lambda b: _flag(b, flagged=True, held_months=np.int32(6))),
])
def test_check_rules_fire_with_rows(clean, cfg, rule, corrupt):
    common, built = clean
    signatures.check(built, common, cfg)  # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        signatures.check(corrupt(built), common, cfg)
    rows = err.value.rows
    assert rows is not None and rows["problem"].str.contains(rule, regex=False).any() and {"k", "t", "mode", "i"} <= set(rows.columns)


def test_check_counts_the_rows_and_ties_them_to_common_mode(clean, cfg):
    common, built = clean
    with pytest.raises(AcceptanceError, match="signatures_flag has"):
        signatures.check({"signatures_flag": built["signatures_flag"].iloc[1:]}, common, cfg)
    with pytest.raises(AcceptanceError, match="signatures_flag has"):
        signatures.check({"signatures_flag": built["signatures_flag"].iloc[:0]}, common, cfg)   # the kind was asked for
    mo = common["common_mode_month"]
    moved = {"common_mode_month": mo.assign(absorption_ratio=mo["absorption_ratio"] * 1.5)}
    with pytest.raises(AcceptanceError, match="components carry the values common_mode wrote"):
        signatures.check(built, moved, cfg)
    with pytest.raises(AcceptanceError, match="not one per configuration and month"):
        signatures.run({"common_mode_month": mo.iloc[1:]}, cfg)


def test_artifact_round_trips(tmp_path, clean, cfg):
    _, built = clean
    f = built["signatures_flag"]
    pd.testing.assert_frame_equal(contracts.read(contracts.write(f, "signatures_flag", tmp_path / "flag.parquet"), "signatures_flag"), f)
    empty = signatures.run(clean[0], {**cfg, "signatures.kinds": []})[0]["signatures_flag"]
    back = contracts.read(contracts.write(empty, "signatures_flag", tmp_path / "empty.parquet"), "signatures_flag")
    assert len(back) == 0 and list(back.columns) == list(f.columns)


@pytest.mark.parametrize("key, value, match", [
    ("signatures.kinds", ["collapse"], "signatures.kinds"),                       # not built
    ("signatures.kinds", ["consolidation", "collusion"], "signatures.kinds"),     # not built
    ("signatures.kinds", ["consolidation", "consolidation"], "signatures.kinds"),
    ("signatures.kinds", [1], "signatures.kinds"),
    ("signatures.consolidation_requires", [], "at least one"),
    ("signatures.consolidation_requires", ["lambda1_above_q95"], "consolidation_requires"),   # rdiag's name; here the band is a key
    ("signatures.consolidation_requires", ["absorption_rising", "absorption_rising"], "consolidation_requires"),
    ("signatures.persistence_months", 0, "persistence_months"),
])
def test_signatures_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    assert validate_config(dict(c, **{"signatures.kinds": []}))["signatures.kinds"] == []   # an empty list of kinds is allowed
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


def test_a_failed_check_stops_the_build_and_writes_its_rows(cfg, tmp_path, monkeypatch):
    from rattractor.build import build
    from rattractor.runspec import load_run_spec

    def fail(common, cfg):
        raise AcceptanceError("signatures", "planted failure", pd.DataFrame({"k": [0], "problem": ["planted"]}))

    monkeypatch.setattr(signatures, "run", fail)
    with pytest.raises(AcceptanceError, match="signatures: planted failure"):
        build(load_run_spec("fixture_six_regime.yaml"), cfg, tmp_path)
    assert len(list((tmp_path / "reports").glob("*/signatures.parquet"))) == 1   # filed under this stage's name
    assert not list((tmp_path / "builds").glob("*/manifest.json"))
