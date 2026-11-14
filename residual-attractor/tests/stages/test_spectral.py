"""Stage spectral: global spectrum, data-driven bands, band power and dominant period, per configuration row (rdiag s2b under v2)."""

import re

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy import stats

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.common import wavelets
from rattractor.config import validate_config
from rattractor.stages import AcceptanceError, spectral, wavelet
from tests.stages.test_wavelet import (ar1_rows, assert_frames_equal_under_reindexing, assert_other_configurations_identical,
                                       fixture_build, make_grid, rows_of, subgrid, three_series_grid)


def staged(R, cfg):
    frames = make_grid(R)
    wav, _ = wavelet.run(frames, cfg)
    built, info = spectral.run(frames, wav, cfg)
    return frames, wav, built, info


# ---- the pieces ---------------------------------------------------------------------------------

def test_runs_are_maximal_and_at_least_the_minimum_length():
    above = np.array([[0, 1, 1, 0, 1, 0, 1, 1, 1],     # runs 1-2, 4 (too short), 6-8
                      [0, 0, 0, 0, 0, 0, 0, 0, 0],     # none
                      [1, 1, 1, 1, 1, 1, 1, 1, 1],     # one run over everything
                      [1, 0, 1, 1, 0, 0, 0, 1, 1]], dtype=bool)
    row, band, lo, hi = spectral.runs(above, 2)
    assert list(zip(row.tolist(), band.tolist(), lo.tolist(), hi.tolist())) == [(0, 0, 1, 2), (0, 1, 6, 8), (2, 0, 0, 8), (3, 0, 2, 3), (3, 1, 7, 8)]
    row, band, lo, hi = spectral.runs(above, 1)
    assert list(zip(row.tolist(), band.tolist(), lo.tolist(), hi.tolist()))[:3] == [(0, 0, 1, 2), (0, 1, 4, 4), (0, 2, 6, 8)]
    assert [x.size for x in spectral.runs(np.zeros((3, 5), bool), 2)] == [0, 0, 0, 0]
    assert [x.size for x in spectral.runs(np.zeros((0, 5), bool), 2)] == [0, 0, 0, 0]


def test_global_spectrum_dof_threshold_and_p_value(cfg, rng):
    R = ar1_rows(rng, (2, 2, 98), 0.5)
    frames, wav, b, _ = staged(R, cfg)
    cw, gl, sc, se = wav["wavelet_cwt"], b["spectral_global"], wav["wavelet_scale"], wav["wavelet_series"]
    want = cw[cw["in_coi"]].groupby(["k", "i", "j"])["power"].mean().reset_index()
    got = gl.merge(want, on=["k", "i", "j"])
    np.testing.assert_allclose(got["gws"], got["power"], rtol=1e-13)
    n_a = cw[(cw["k"] == 0) & (cw["i"] == 0)].groupby("j")["in_coi"].sum().to_numpy()
    s, per = sc["scale"].to_numpy(), sc["period"].to_numpy()
    row = rows_of(gl, k=1, i=0)
    dof = 2 * np.sqrt(1 + (n_a / (2.32 * s)) ** 2)
    np.testing.assert_allclose(row["dof"], dof, rtol=1e-13)
    assert dof[0] == pytest.approx(2 * np.sqrt(1 + (92 / (2.32 * s[0])) ** 2)) and 2.0 < dof[-1] < 2.1
    v, a = rows_of(se, k=1, i=0).iloc[0][["variance", "ar1"]]
    level = v * (1 - a * a) / (1 + a * a - 2 * a * np.cos(2 * np.pi / per))
    np.testing.assert_allclose(row["threshold"], level * stats.chi2.ppf(0.95, dof) / dof, rtol=1e-12)
    np.testing.assert_allclose(row["p_value"], stats.chi2.sf(dof * row["gws"] / level, dof), rtol=1e-10)
    np.testing.assert_array_equal(row["above"], row["gws"] > row["threshold"])
    np.testing.assert_array_equal(gl["above"], gl["p_value"] < 0.05)     # the flag and the raw p-value tell one story


def test_red_noise_rows_clear_their_own_spectrum_at_about_the_nominal_rate(cfg):
    R = ar1_rows(np.random.default_rng(201), (2, 200, 128), 0.6)
    _, _, b, _ = staged(R, cfg)
    gl = b["spectral_global"]
    assert 0.03 < gl["above"].mean() < 0.08, gl["above"].mean()
    assert 0.03 < (gl["p_value"] < 0.05).mean() < 0.08 and 0.4 < gl["p_value"].mean() < 0.6
    assert ((gl["p_value"] > 0) & (gl["p_value"] <= 1)).all()
    by_scale = gl.groupby("j")["above"].mean()
    assert by_scale.max() < 0.14, by_scale.to_dict()


def test_scale_average_reconstructs_the_variance(cfg):
    # Torrence and Compo eq. 14: (dj / (C_delta P)) sum_t sum_j |W|^2 / s_j is the variance, when the scales cover the signal
    P = 256
    t = np.arange(P)
    x = 3.0 * np.sin(2 * np.pi * t / 9.0)
    s = wavelets.scales(wavelets.periods(P, cfg), cfg)
    W = wavelets.transform(x - x.mean(), s, cfg)
    sap = spectral.scale_average(np.abs(W) ** 2, s, 0, s.size - 1, cfg)
    coi = wavelets.coi_mask(s, P)[-1]
    assert sap[coi].mean() == pytest.approx(4.5, rel=0.02)
    assert sap[coi].min() > 4.2 and sap[coi].max() < 4.8


def test_scale_average_threshold_is_exceeded_at_about_the_nominal_rate(cfg):
    R = ar1_rows(np.random.default_rng(202), (300, 128), 0.5)
    per = wavelets.periods(128, cfg)
    s = wavelets.scales(per, cfg)
    coi = wavelets.coi_mask(s, 128)
    xc, _, variance, ar1 = wavelet.moments(R)
    power = np.abs(wavelets.transform(xc, s, cfg)) ** 2
    level = wavelet.red_noise_level(variance, ar1, per)
    for lo, hi in ((4, 9), (12, 19), (20, 23)):
        sap = spectral.scale_average(power, s, lo, hi, cfg)
        thr = spectral.scale_average_threshold(level, s, lo, hi, cfg)
        rate = (sap > thr[:, None])[:, coi[hi]].mean()
        assert 0.025 < rate < 0.08, (lo, hi, rate)
    # the formula, written out (Torrence and Compo eqs. 25 to 28)
    lo, hi = 12, 19
    sj = s[lo : hi + 1]
    nu = 2 * 8 * (1 / (1 / sj).sum()) / np.sqrt(sj[0] * sj[-1]) * np.sqrt(1 + (8 * 0.125 / 0.6) ** 2)
    want = 0.125 / 0.776 * (level[0, lo : hi + 1] / sj).sum() * stats.chi2.ppf(0.95, nu) / nu
    assert spectral.scale_average_threshold(level, s, lo, hi, cfg)[0] == pytest.approx(want, rel=1e-13)


# ---- known answers on planted rows --------------------------------------------------------------

@pytest.fixture(scope="module")
def planted(cfg):
    """K = 3 configurations x 4 series x 128 months: series 0 one cycle, series 1 two cycles, series 2 and 3 noise."""
    rng = np.random.default_rng(203)
    P = 128
    t = np.arange(P)
    R = rng.standard_normal((3, 4, P))
    per = wavelets.periods(P, cfg)
    R[:, 0] += 2.0 * np.sin(2 * np.pi * t / per[20])                                       # period 11.3
    R[:, 1] += 2.0 * np.sin(2 * np.pi * t / per[10]) + 2.0 * np.cos(2 * np.pi * t / per[26])  # periods 4.76 and 19.0
    return (R,) + staged(R, cfg)


def test_a_planted_cycle_gives_one_band_around_its_period(planted, cfg):
    R, frames, wav, b, _ = planted
    bd, bc = b["spectral_bands"], b["spectral_band_count"]
    per = wav["wavelet_scale"]["period"].to_numpy()
    for k in range(3):
        one = rows_of(bd, k=k, i=0)
        assert len(one) == 1 and rows_of(bc, k=k, i=0)["band_count"].iloc[0] == 1
        r = one.iloc[0]
        lo, hi, centre = int(r["j_lo"]), int(r["j_hi"]), int(r["j_center"])
        assert r["band"] == 0 and lo <= 20 <= hi and abs(centre - 20) <= 1
        assert r["period_lo"] == per[lo] and r["period_hi"] == per[hi] and r["period_lo"] <= per[20] <= r["period_hi"]
        gl = rows_of(b["spectral_global"], k=k, i=0)
        assert gl["above"].iloc[lo : hi + 1].all()
        assert lo == 0 or not gl["above"].iloc[lo - 1]                                        # maximal on both sides
        assert not gl["above"].iloc[hi + 1]
        assert centre == lo + int(np.argmax(gl["gws"].to_numpy()[lo : hi + 1]))


def test_two_cycles_give_two_bands_numbered_by_ascending_period(planted):
    _, _, wav, b, _ = planted
    for k in range(3):
        two = rows_of(b["spectral_bands"], k=k, i=1)
        assert two["band"].tolist() == [0, 1] and two["j_hi"].iloc[0] < two["j_lo"].iloc[1]
        assert two["j_lo"].iloc[0] <= 10 <= two["j_hi"].iloc[0] and two["j_lo"].iloc[1] <= 26 <= two["j_hi"].iloc[1]
        assert (two["period_lo"].iloc[0] < two["period_lo"].iloc[1]) and rows_of(b["spectral_band_count"], k=k, i=1)["band_count"].iloc[0] == 2


def test_rows_without_a_cycle_mostly_have_no_band_and_zero_is_recorded(cfg):
    R = ar1_rows(np.random.default_rng(204), (2, 100, 128), 0.3)
    _, _, b, _ = staged(R, cfg)
    bc, bd = b["spectral_band_count"], b["spectral_bands"]
    assert len(bc) == 200 and (bc["band_count"] == 0).mean() > 0.5       # about a third of pure-noise rows clear two adjacent scales by chance
    none = bc[bc["band_count"] == 0]
    assert len(none.merge(bd, on=["k", "i"])) == 0                 # no band rows, and the count row is still there
    assert bc["band_count"].sum() == len(bd)
    assert (bd["j_hi"] - bd["j_lo"] + 1 >= cfg["spectral_summary.min_band_scales"]).all()


def test_band_power_is_the_scale_average_over_the_rows_own_band(planted, cfg):
    R, frames, wav, b, _ = planted
    bd, bp, cw, sc = b["spectral_bands"], b["spectral_band_power"], wav["wavelet_cwt"], wav["wavelet_scale"]
    P = R.shape[2]
    assert len(bp) == len(bd) * P
    s = sc["scale"].to_numpy()
    for _, r in bd.iterrows():
        cells = cw[(cw["k"] == r["k"]) & (cw["i"] == r["i"]) & (cw["j"] >= r["j_lo"]) & (cw["j"] <= r["j_hi"])]
        want = (0.125 / 0.776) * (cells["power"] / s[cells["j"].to_numpy()]).groupby(cells["t"]).sum()
        got = rows_of(bp, k=r["k"], i=r["i"], band=r["band"]).set_index("t")
        np.testing.assert_allclose(got["sap"], want.reindex(got.index), rtol=1e-12)
        top = rows_of(cw, k=r["k"], i=r["i"], j=r["j_hi"]).set_index("t")["in_coi"]
        np.testing.assert_array_equal(got["in_coi"], top.reindex(got.index))
    # the planted cycle lifts its band's power above the band's red-noise level in most in-cone months
    r = rows_of(bd, k=0, i=0).iloc[0]
    got = rows_of(bp, k=0, i=0, band=0)
    assert (got.loc[got["in_coi"], "sap"] > r["sap_threshold"]).mean() > 0.8
    xc, _, variance, ar1 = wavelet.moments(R[0, 0][None])
    level = wavelet.red_noise_level(variance, ar1, sc["period"].to_numpy())
    assert r["sap_threshold"] == pytest.approx(spectral.scale_average_threshold(level, s, int(r["j_lo"]), int(r["j_hi"]), cfg)[0], rel=1e-13)


def test_dominant_period_is_the_planted_cycle_and_null_where_no_scale_is_in_the_cone(planted):
    R, frames, wav, b, _ = planted
    dm, per = b["spectral_dominant"], wav["wavelet_scale"]["period"].to_numpy()
    one = rows_of(dm, k=0, i=0).sort_values("t").reset_index(drop=True)
    assert one["period"].isna().tolist()[:4] == [True, True, True, False] and one["period"].isna().tolist()[-4:] == [False, True, True, True]
    assert one["j"].isna().equals(one["period"].isna())
    mid = one.iloc[20:108]
    assert (np.abs(mid["j"].astype(int) - 20) <= 1).mean() > 0.9
    np.testing.assert_array_equal(mid["period"].to_numpy(), per[mid["j"].astype(int).to_numpy()])
    # the largest power among the in-cone scales, written out
    cw = rows_of(wav["wavelet_cwt"], k=1, i=3)
    best = cw[cw["in_coi"]].sort_values(["t", "power"], ascending=[True, False]).drop_duplicates("t").set_index("t")["j"]
    got = rows_of(dm, k=1, i=3).dropna(subset=["period"]).set_index("t")["j"].astype(int)
    assert got.equals(best.reindex(got.index).astype(int))


# ---- the archive rule and count independence ----------------------------------------------------

def test_changing_one_configuration_leaves_every_other_row_bit_identical(planted, cfg):
    R, _, _, built, _ = planted
    R2 = R.copy()
    R2[1] = ar1_rows(np.random.default_rng(8), R[1].shape, 0.8) * 3.0
    _, _, other, _ = staged(R2, cfg)
    assert_other_configurations_identical(built, other, changed=1)
    assert not rows_of(built["spectral_global"], k=1)["gws"].equals(rows_of(other["spectral_global"], k=1)["gws"])


def test_rows_do_not_depend_on_how_many_series_or_configurations_there_are(planted, cfg):
    _, frames, _, built, _ = planted
    ks, iis = [2, 0], [1, 3, 0]
    sub = subgrid(frames, ks=ks, iis=iis)
    wav, _ = wavelet.run(sub, cfg)
    small, _ = spectral.run(sub, wav, cfg)
    for name in built:
        assert_frames_equal_under_reindexing(small[name], built[name], kmap=ks, imap=iis)


# ---- acceptance ---------------------------------------------------------------------------------

def _with(b, name, **cols):
    return {**b, name: b[name].assign(**cols)}


def _drop_band(b):
    bd = b["spectral_bands"]
    return {**b, "spectral_bands": bd.iloc[1:].reset_index(drop=True)}


def _shift_band(b):
    bd = b["spectral_bands"].copy()
    bd.loc[0, "j_hi"] = bd.loc[0, "j_hi"] + 1
    return {**b, "spectral_bands": bd}


@pytest.mark.parametrize("rule, corrupt", [
    ("gws is null exactly where the scale has no in-cone month", lambda b: _with(b, "spectral_global", gws=np.where(b["spectral_global"]["j"] == 3, np.nan, b["spectral_global"]["gws"]))),
    ("above equals gws > threshold", lambda b: _with(b, "spectral_global", above=~b["spectral_global"]["above"])),
    ("dof equals 2 sqrt(1 + (n_a / (gamma s))^2)", lambda b: _with(b, "spectral_global", dof=b["spectral_global"]["dof"] * 1.01)),
    ("p_value in (0, 1], null exactly where gws is null", lambda b: _with(b, "spectral_global", p_value=b["spectral_global"]["p_value"] + 1.0)),
    ("bands are the maximal runs of above", _drop_band),
    ("bands are the maximal runs of above", _shift_band),
    ("bands are the maximal runs of above", lambda b: _with(b, "spectral_bands", band=b["spectral_bands"]["band"] + np.int16(1))),
    ("j_center is the scale of largest gws in the band", lambda b: _with(b, "spectral_bands", j_center=b["spectral_bands"]["j_lo"] - np.int16(1))),
    ("j_center is the scale of largest gws in the band", lambda b: _with(b, "spectral_bands", period_hi=b["spectral_bands"]["period_hi"] * 1.5)),
    ("sap_threshold is positive", lambda b: _with(b, "spectral_bands", sap_threshold=0.0)),
    ("band_count equals the row's number of bands", lambda b: _with(b, "spectral_band_count", band_count=np.int16(1))),
    ("every band has a scale-averaged power for every month", lambda b: {**b, "spectral_band_power": b["spectral_band_power"].iloc[5:].reset_index(drop=True)}),
    ("sap is non-negative and in_coi is the cone at the band's longest scale", lambda b: _with(b, "spectral_band_power", in_coi=True)),
    ("period is null exactly where no scale is in the cone", lambda b: _with(b, "spectral_dominant", period=b["spectral_dominant"]["period"].fillna(2.0))),
    ("period is null exactly where no scale is in the cone", lambda b: _with(b, "spectral_dominant", period=b["spectral_dominant"]["period"] * 2.0)),
])
def test_check_rules_fire_with_rows(planted, cfg, rule, corrupt):
    _, frames, wav, built, _ = planted
    spectral.check(built, frames, wav, cfg)  # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        spectral.check(corrupt(built), frames, wav, cfg)
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_check_counts_rows(planted, cfg):
    _, frames, wav, built, _ = planted
    with pytest.raises(AcceptanceError, match="spectral_global has"):
        spectral.check({**built, "spectral_global": built["spectral_global"].iloc[1:].reset_index(drop=True)}, frames, wav, cfg)


def test_a_cone_that_differs_between_rows_is_refused(planted, cfg):
    _, frames, wav, _, _ = planted
    cw = wav["wavelet_cwt"].copy()
    cw.loc[0, "in_coi"] = ~cw.loc[0, "in_coi"]
    with pytest.raises(AcceptanceError, match="in_coi differs between rows"):
        spectral.run(frames, {**wav, "wavelet_cwt": cw}, cfg)


def test_artifacts_round_trip_with_and_without_bands(tmp_path, planted, cfg):
    *_, built, _ = planted
    flat = staged(np.random.default_rng(205).standard_normal((1, 1, 60)), {**cfg, "spectral_summary.min_band_scales": 40})[2]
    assert len(flat["spectral_bands"]) == 0 and len(flat["spectral_band_power"]) == 0 and flat["spectral_band_count"]["band_count"].tolist() == [0]
    for tag, frames in (("planted", built), ("flat", flat)):
        for name, f in frames.items():
            back = contracts.read(contracts.write(f, name, tmp_path / f"{tag}_{name}.parquet"), name)
            pd.testing.assert_frame_equal(back, f)


@pytest.mark.parametrize("key, value, match", [
    ("spectral_summary.c_delta", 0.0, "must be positive"),
    ("spectral_summary.gamma_decorrelation", 0, "must be positive"),
    ("spectral_summary.dj0_decorrelation", 0.0, "must be positive"),
    ("spectral_summary.min_band_scales", 0, "< 1"),
    ("spectral_summary.band_rule", "preset_ranges", "not in"),
])
def test_spectral_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


# ---- on built grids -----------------------------------------------------------------------------

def test_three_series_grid(cfg):
    frames = three_series_grid()
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    wav, _ = wavelet.run(frames, cfg)
    built, _ = spectral.run(frames, wav, cfg)
    J = len(wav["wavelet_scale"])
    assert len(built["spectral_global"]) == K * N * J and len(built["spectral_dominant"]) == K * N * P
    assert len(built["spectral_band_count"]) == K * N and built["spectral_band_count"]["band_count"].sum() == len(built["spectral_bands"])
    assert len(built["spectral_band_power"]) == len(built["spectral_bands"]) * P
    assert built["spectral_global"]["gws"].notna().all()                # P / 3 leaves every scale some in-cone months


def test_one_series_fixture_build_writes_the_summary(cfg):
    out, m = fixture_build()
    assert m["stages_passed"].index("spectral") == m["stages_passed"].index("wavelet") + 1
    K, P, J = m["configurations"]["admissible"], m["grid"]["rdiag_minimums"]["P"], m["wavelet"]["scales"]
    rows = {rel: a["rows"] for rel, a in m["artifacts"].items() if rel.startswith("spectral/")}
    bands = rows["spectral/bands.parquet"]
    assert rows == {"spectral/global.parquet": K * J, "spectral/bands.parquet": bands, "spectral/band_count.parquet": K,
                    "spectral/band_power.parquet": bands * P, "spectral/dominant.parquet": K * P}
    bc = contracts.read(out / "spectral/band_count.parquet", "spectral_band_count")
    assert bc["band_count"].sum() == bands and set(bc["i"]) == {0}
