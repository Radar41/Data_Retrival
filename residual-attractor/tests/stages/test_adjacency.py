"""Stage adjacency: one edge decision per (k, pair, scope), taken inside one configuration (rdiag s3.adjacency under v2), and Benjamini-Yekutieli."""

import re

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy import stats

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.common import fdr, wavelets
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, adjacency, coherence, spectral, wavelet
from tests.stages.test_coherence import delayed_field
from tests.stages.test_coherence import staged as staged_coherence
from tests.stages.test_wavelet import (ar1_rows, assert_frames_equal_under_reindexing, assert_other_configurations_identical,
                                       fixture_build, subgrid, three_series_grid)

KEY = ["k", "i_a", "i_b", "band_a", "band_b"]


def on(frames, cfg):
    """(wav, coh, built, info) of the four track A stages on grid frames."""
    wav, _ = wavelet.run(frames, cfg)
    spec, _ = spectral.run(frames, wav, cfg)
    coh, _ = coherence.run(frames, wav, spec, cfg)
    built, info = adjacency.run(frames, wav, coh, cfg)
    return wav, coh, built, info


def staged(R, cfg):
    frames, wav, _, coh, _ = staged_coherence(R, cfg)
    built, info = adjacency.run(frames, wav, coh, cfg)
    return frames, wav, coh, built, info


@pytest.fixture(scope="module")
def planted(cfg):
    """The delayed field of the coherence tests: in each of 3 configurations series 0 and 1 share a cycle, series 2 is unrelated."""
    R = delayed_field()
    return (R,) + staged(R, cfg)


# ---- Benjamini-Yekutieli ------------------------------------------------------------------------

def _by_loop(p):
    """The same adjustment as plain loops over the sorted p-values."""
    m = len(p)
    c = sum(1 / l for l in range(1, m + 1))
    order = sorted(range(m), key=lambda i: p[i])
    q, running = [0.0] * m, 1.0
    for rank in range(m, 0, -1):
        running = min(running, p[order[rank - 1]] * m * c / rank)
        q[order[rank - 1]] = running
    return q


def test_benjamini_yekutieli_known_answers(rng):
    assert fdr.harmonic(1) == 1.0 and fdr.harmonic(4) == pytest.approx(25 / 12)
    c = 25 / 12
    np.testing.assert_allclose(fdr.benjamini_yekutieli([0.01, 0.04, 0.03, 0.005]), [0.02 * c, 0.04 * c, 0.04 * c, 0.02 * c], rtol=1e-13)
    assert fdr.benjamini_yekutieli([0.03]).tolist() == [0.03]                       # one test: nothing to correct
    np.testing.assert_allclose(fdr.benjamini_yekutieli([0.01, np.nan, 0.5]), [0.03, np.nan, 0.75], rtol=1e-13)    # a null is no test
    assert fdr.benjamini_yekutieli([0.9, 0.8]).tolist() == [1.0, 1.0]               # capped at 1
    assert fdr.benjamini_yekutieli([]).size == 0 and np.isnan(fdr.benjamini_yekutieli([np.nan, np.nan])).all()
    p = np.round(rng.random(200) ** 3, 3)                                           # many small values, many ties
    q = fdr.benjamini_yekutieli(p)
    np.testing.assert_allclose(q, _by_loop(p.tolist()), rtol=1e-12)
    order = np.argsort(p, kind="stable")
    assert (np.diff(q[order]) >= 0).all() and (q >= p).all() and all(len(set(q[p == v])) == 1 for v in np.unique(p))
    perm = rng.permutation(200)
    np.testing.assert_array_equal(fdr.benjamini_yekutieli(p[perm]), q[perm])
    level, m = 0.10, 200                                                            # q <= level is the step-up rule
    ranks = np.arange(1, m + 1)
    passing = np.nonzero(np.sort(p) <= ranks * level / (m * fdr.harmonic(m)))[0]
    n_reject = passing[-1] + 1 if passing.size else 0
    assert n_reject > 0 and (q <= level).sum() == n_reject and set(np.nonzero(q <= level)[0]) == set(order[:n_reject])


@pytest.mark.parametrize("m, need", [(4, 2), (14, 6), (91, 61)])
def test_what_a_p_value_floor_of_one_in_76_allows(m, need):
    # 75 shifts cannot give a p-value below 1 / 76: a family of m such tests has a discovery at q = 0.10 only if `need` of them sit at the floor
    for n_floor in (need - 1, need):
        q = fdr.benjamini_yekutieli([1 / 76] * n_floor + [1.0] * (m - n_floor))
        assert (q <= 0.10).any() == (n_floor == need)
    assert need == int(np.ceil(m * fdr.harmonic(m) / 76 / 0.10))


# ---- effective n and the p-value ----------------------------------------------------------------

def test_effective_n_is_the_kish_count_of_smoothing_footprints(cfg):
    P = 98
    s = wavelets.scales(wavelets.periods(P, cfg), cfg)
    n_a = wavelets.coi_mask(s, P).sum(axis=1)
    c = np.sqrt(2 * np.pi)

    def n_eff(lo, hi, cf=cfg, cells=n_a):
        return adjacency.effective_n(np.array([lo]), np.array([hi]), s, cells, cf)[0]

    assert n_eff(0, 0) == pytest.approx(92 / (c * s[0])) and 18.9 < n_eff(0, 0) < 19.1     # one scale: its in-cone months in footprints
    assert n_eff(16, 16) == pytest.approx(n_a[16] / (c * s[16]))
    assert n_eff(8, 9) == pytest.approx((n_a[8] + n_a[9]) ** 2 / (c * 2 * (n_a[8] * s[8] + n_a[9] * s[9])))    # no wider than the scope
    assert n_eff(0, 32) == pytest.approx(n_a.sum() ** 2 / (c * 4.8 * (n_a * s).sum())) and 23 < n_eff(0, 32) < 24.5
    assert n_eff(32, 32) == 1.0 and n_eff(28, 32) == 1.0                                    # never less than one observation
    narrow = {**cfg, "coherence.scale_smoothing_width": 0.05}                              # a boxcar under one scale still covers one
    assert n_eff(0, 4, narrow) == pytest.approx(n_a[:5].sum() ** 2 / (c * (n_a[:5] * s[:5]).sum()))
    assert np.isnan(n_eff(0, 1, cells=np.zeros_like(n_a)))
    many = adjacency.effective_n(np.array([0, 8, 0]), np.array([0, 9, 32]), s, n_a, cfg)
    np.testing.assert_allclose(many, [n_eff(0, 0), n_eff(8, 9), n_eff(0, 32)], rtol=1e-13)


def test_the_p_value_is_the_binomial_upper_tail():
    n, x = np.array([20.0, 20.0, 20.0, 7.0]), np.array([1.0, 3.0, 20.0, 7.0])
    p = adjacency.exceedance(x / n, n, 0.05)
    np.testing.assert_allclose(p, stats.binom.sf(x - 1, n, 0.05), rtol=1e-9)        # scipy's own tail at whole numbers
    assert p[2] == pytest.approx(0.05 ** 20) and p[3] == pytest.approx(0.05 ** 7)
    w = np.linspace(0, 1, 101)
    between = adjacency.exceedance(w, np.full(101, 23.6), 0.05)                     # real n: continuous and falling in the weight
    assert between[0] == 1.0 and (np.diff(between) < 0).all() and between[-1] == pytest.approx(0.05 ** 23.6)
    np.testing.assert_allclose(between[1:], stats.beta.cdf(0.05, w[1:] * 23.6, 23.6 - w[1:] * 23.6 + 1), rtol=1e-9)
    assert adjacency.exceedance(np.array([1.0]), np.array([1.0]), 0.05)[0] == pytest.approx(0.05)    # one footprint, all of it significant
    assert np.isnan(adjacency.exceedance(np.array([np.nan]), np.array([np.nan]), 0.05)[0])


# ---- known answers ------------------------------------------------------------------------------

def test_the_planted_pair_gets_its_edge_and_unrelated_pairs_do_not(planted):
    *_, b, info = planted
    ed = b["adjacency_edges"]
    assert (ed["i_a"] < ed["i_b"]).all()
    pair, rest = ed[(ed["i_a"] == 0) & (ed["i_b"] == 1)], ed[ed["i_b"] == 2]
    assert pair["edge"].all() and (pair["q_value"] < 1e-6).all() and set(pair["family"]) == {"all", "band"} and (pair["weight"] > 0.5).all()
    assert not rest["edge"].any() and (rest["q_value"] > 0.10).all() and (rest["weight"] < 0.2).all()
    assert info["families"] == {"all": {"tests": 9, "edges": 3}, "band": {"tests": 3, "edges": 3}}


def test_every_column_follows_from_coherence_scope_inside_one_configuration(planted, cfg):
    _, frames, wav, coh, b, _ = planted
    ed = b["adjacency_edges"]
    j = ed.merge(coh["coherence_scope"][KEY + ["j_lo", "j_hi", "n_cells", "n_significant"]], on=KEY)
    assert len(j) == len(ed) == len(coh["coherence_scope"])
    np.testing.assert_allclose(j["weight"], j["n_significant"] / j["n_cells"], rtol=1e-15)
    assert (ed["expected"] == 1.0 - cfg["coherence.quantile"]).all()
    s = wav["wavelet_scale"]["scale"].to_numpy()
    cone = wavelets.coi_mask(s, len(frames["grid_month"]))
    for row in j.itertuples():                                   # effective n and p-value from the cells of the scope, one cell at a time
        cells = [(jj, t) for jj in range(row.j_lo, row.j_hi + 1) for t in np.nonzero(cone[jj])[0]]
        footprint = [np.sqrt(2 * np.pi) * s[jj] * min(4.8, row.j_hi - row.j_lo + 1) for jj, _ in cells]
        n = max(1.0, len(cells) ** 2 / sum(footprint))
        assert row.n_cells == len(cells) and row.n_eff == pytest.approx(n, rel=1e-12)
        want = stats.beta.cdf(0.05, row.weight * n, n - row.weight * n + 1) if row.weight > 0 else 1.0
        assert row.p_value == pytest.approx(max(want, np.finfo(float).tiny), rel=1e-9)
    assert ((ed["family"] == "all") == (ed["band_a"] == -1)).all()
    for _, g in ed.groupby(["k", "family"], observed=True):      # the decision never leaves the configuration
        assert (g["family_size"] == len(g)).all()
        np.testing.assert_allclose(g["q_value"], _by_loop(g["p_value"].tolist()), rtol=1e-12)
    np.testing.assert_array_equal(ed["edge"], ed["q_value"] <= cfg["inference.q"])


def test_without_per_band_only_the_all_scales_rows_are_written(planted, cfg):
    _, frames, wav, coh, b, _ = planted
    only, info = adjacency.run(frames, wav, coh, {**cfg, "adjacency.per_band": False})
    ed = b["adjacency_edges"]
    pd.testing.assert_frame_equal(only["adjacency_edges"], ed[ed["family"] == "all"].reset_index(drop=True), check_exact=True)
    assert info["families"]["band"] == {"tests": 0, "edges": 0} and info["per_band"] is False


def test_unrelated_rows_rarely_get_an_edge(cfg):
    R = ar1_rows(np.random.default_rng(307), (6, 8, 98), 0.5)                     # 6 configurations x 28 unrelated pairs
    *_, b, _ = staged(R, cfg)
    ed = b["adjacency_edges"]
    every = ed[ed["family"] == "all"]
    assert 0.05 < every["weight"].mean() < 0.11                                    # above the expected 0.05: see the coherence stage
    assert (every["p_value"] <= 0.05).mean() < 0.15 and every["edge"].sum() <= 1 and ed["edge"].sum() <= 2


# ---- the archive rule and count independence ----------------------------------------------------

def test_changing_one_configuration_leaves_every_other_row_bit_identical(planted, cfg):
    R, *_, built, _ = planted
    R2 = R.copy()
    R2[1] = ar1_rows(np.random.default_rng(8), R[1].shape, 0.8) * 3.0
    *_, other, _ = staged(R2, cfg)
    assert_other_configurations_identical(built, other, changed=1)
    one, two = built["adjacency_edges"], other["adjacency_edges"]
    assert not one[one["k"] == 1].reset_index(drop=True).equals(two[two["k"] == 1].reset_index(drop=True))


def test_only_the_family_decision_depends_on_which_series_a_configuration_holds(planted, cfg):
    _, frames, _, _, built, _ = planted
    full = built["adjacency_edges"]
    small = on(subgrid(frames, ks=[2, 0]), cfg)[2]["adjacency_edges"]              # fewer configurations: every column of the others stays
    assert_frames_equal_under_reindexing(small, full, kmap=[2, 0], pair=True)
    small = on(subgrid(frames, iis=[0, 2]), cfg)[2]["adjacency_edges"]             # fewer series: the tests stay, their family shrinks
    assert_frames_equal_under_reindexing(small, full, imap=[0, 2], pair=True, columns=KEY + ["weight", "expected", "n_eff", "p_value", "family"])
    assert (small.loc[small["family"] == "all", "family_size"] == 1).all() and (full.loc[full["family"] == "all", "family_size"] == 3).all()
    assert (small.loc[small["family"] == "all", "q_value"] == small.loc[small["family"] == "all", "p_value"]).all()


# ---- acceptance ---------------------------------------------------------------------------------

def _with(b, **cols):
    return {"adjacency_edges": b["adjacency_edges"].assign(**cols)}


def _at(b, row, col, value):
    f = b["adjacency_edges"].copy()
    f.loc[row, col] = value
    return {"adjacency_edges": f}


@pytest.mark.parametrize("rule, corrupt", [
    ("the rows are coherence_scope's (k, pair, scope) rows", lambda b: _at(b, 1, "band_b", 5)),
    ("weight is n_significant / n_cells, null where the scope has no in-cone cell", lambda b: _with(b, weight=b["adjacency_edges"]["weight"] * 0.5)),
    ("weight is n_significant / n_cells, null where the scope has no in-cone cell", lambda b: _at(b, 3, "weight", np.nan)),
    ("expected is 1 - coherence.quantile", lambda b: _with(b, expected=0.10)),
    ("n_eff is the Kish count of smoothing footprints, at least 1", lambda b: _at(b, 0, "n_eff", b["adjacency_edges"].loc[0, "n_eff"] + 1.0)),
    ("p_value is the binomial exceedance of weight x n_eff, in (0, 1]", lambda b: _at(b, 3, "p_value", b["adjacency_edges"].loc[3, "p_value"] * 0.5)),
    ("p_value is the binomial exceedance of weight x n_eff, in (0, 1]", lambda b: _at(b, 3, "p_value", 0.0)),
    ("family is all for the all-scales rows and band for the overlaps", lambda b: _at(b, 0, "family", "band")),
    ("family is all for the all-scales rows and band for the overlaps", lambda b: _with(b, family_size=b["adjacency_edges"]["family_size"] + np.int32(1))),
    ("q_value is Benjamini-Yekutieli within the configuration's family", lambda b: _at(b, 3, "q_value", b["adjacency_edges"].loc[3, "p_value"])),
    ("q_value is Benjamini-Yekutieli within the configuration's family", lambda b: _with(b, q_value=fdr.benjamini_yekutieli(b["adjacency_edges"]["p_value"]))),   # one family across configurations
    ("edge equals q_value <= inference.q", lambda b: _with(b, edge=~b["adjacency_edges"]["edge"])),
    ("edge equals q_value <= inference.q", lambda b: _with(b, edge=b["adjacency_edges"]["p_value"] <= 0.10)),
])
def test_check_rules_fire_with_rows(planted, cfg, rule, corrupt):
    _, frames, wav, coh, built, _ = planted
    adjacency.check(built, frames, wav, coh, cfg)  # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        adjacency.check(corrupt(built), frames, wav, coh, cfg)
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_check_counts_rows(planted, cfg):
    _, frames, wav, coh, built, _ = planted
    with pytest.raises(AcceptanceError, match="adjacency_edges has 11 rows, expected 12"):
        adjacency.check({"adjacency_edges": built["adjacency_edges"].iloc[1:].reset_index(drop=True)}, frames, wav, coh, cfg)


def test_artifact_round_trips_with_and_without_rows(tmp_path, planted, cfg, rng):
    built = planted[4]
    empty = staged(rng.standard_normal((2, 1, 60)), cfg)[3]                        # one series: no pair, no edge
    assert len(empty["adjacency_edges"]) == 0
    for tag, frames in (("planted", built), ("empty", empty)):
        f = frames["adjacency_edges"]
        pd.testing.assert_frame_equal(contracts.read(contracts.write(f, "adjacency_edges", tmp_path / f"{tag}.parquet"), "adjacency_edges"), f)


@pytest.mark.parametrize("key, value, match", [
    ("inference.q", 0.0, "strictly between 0 and 1"),
    ("inference.q", 1.0, "strictly between 0 and 1"),
    ("inference.cooccurrence_family_method", "bonferroni", "not in"),
    ("adjacency.edge_rule", "threshold", "not in"),
    ("adjacency.edge_weight", "mean_coherence", "not in"),
])
def test_adjacency_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


# ---- on built grids -----------------------------------------------------------------------------

def test_three_series_grid(cfg):
    frames = three_series_grid()
    _, coh, built, info = on(frames, cfg)
    ed = built["adjacency_edges"]
    K = len(frames["grid_config"])
    assert len(ed) == len(coh["coherence_scope"]) and (ed["family"] == "all").sum() == K * 3
    assert ed["p_value"].between(0, 1, inclusive="right").all() and (ed["q_value"] >= ed["p_value"]).all()
    assert info["families"]["all"]["tests"] == K * 3 and sum(f["edges"] for f in info["families"].values()) == int(ed["edge"].sum())


def test_one_series_fixture_build_writes_an_empty_table(cfg):
    out, m = fixture_build()
    start = m["stages_passed"].index("wavelet")  # other tracks' stages may follow
    assert m["stages_passed"][start:start + 4] == ["wavelet", "spectral", "coherence", "adjacency"]
    assert m["artifacts"]["adjacency/edges.parquet"]["rows"] == 0
    assert m["adjacency"]["families"] == {"all": {"tests": 0, "edges": 0}, "band": {"tests": 0, "edges": 0}}
    assert len(contracts.read(out / "adjacency/edges.parquet", "adjacency_edges")) == 0
