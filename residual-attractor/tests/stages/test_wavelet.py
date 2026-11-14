"""Stage wavelet: the Morlet transform of every configuration's own row (rdiag s2a.cwt under v2)."""

import atexit
import functools
import json
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy import stats

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.common import wavelets
from rattractor.config import load_config, validate_config
from rattractor.stages import AcceptanceError, wavelet


# ---- helpers the four track A test modules share ------------------------------------------------

def make_grid(R, start="2010-01-01"):
    """Grid frames (stage 9's tables) for a synthetic field R[k, i, t]."""
    R = np.asarray(R, dtype=np.float64)
    K, N, P = R.shape
    months = pd.date_range(start, periods=P, freq="MS").to_numpy().astype("datetime64[ns]")
    kk, ii, tt = wavelet.keys((K, N, P))
    return {
        "grid_resid": contracts.from_columns({"k": kk, "i": ii, "t": months[tt], "resid": R.reshape(-1)}, "grid_resid"),
        "grid_config": contracts.from_columns({"k": np.arange(K), "core_spec_id": [f"core-{k}" for k in range(K)], "exog_set": [[]] * K}, "grid_config"),
        "grid_series": contracts.from_columns({"i": np.arange(N)}, "grid_series"),
        "grid_month": contracts.from_columns({"t": months}, "grid_month"),
    }


def ar1_rows(rng, shape, phi, burn=200):
    """Independent AR(1) rows along the last axis, unit innovations."""
    e = rng.standard_normal(shape[:-1] + (shape[-1] + burn,))
    x = np.zeros_like(e)
    for t in range(1, e.shape[-1]):
        x[..., t] = phi * x[..., t - 1] + e[..., t]
    return x[..., burn:]


def subgrid(frames, ks=None, iis=None):
    """The grid restricted to some configurations and series, re-indexed 0.. in the order given."""
    r = frames["grid_resid"]
    ks = list(range(len(frames["grid_config"]))) if ks is None else list(ks)
    iis = list(range(len(frames["grid_series"]))) if iis is None else list(iis)
    r = r[r["k"].isin(ks) & r["i"].isin(iis)]
    r = r.assign(k=r["k"].map({k: n for n, k in enumerate(ks)}).astype(np.int32), i=r["i"].map({i: n for n, i in enumerate(iis)}).astype(np.int32))
    c = frames["grid_config"].set_index("k").loc[ks].reset_index().assign(k=np.arange(len(ks), dtype=np.int32))
    return {**frames, "grid_resid": contracts.validate(r.sort_values(["k", "i", "t"]).reset_index(drop=True), "grid_resid"),
            "grid_config": contracts.validate(c, "grid_config"),
            "grid_series": contracts.from_columns({"i": np.arange(len(iis))}, "grid_series")}


def rows_of(frame, **where):
    """The rows of a frame at the given key values, index dropped."""
    m = np.ones(len(frame), bool)
    for col, val in where.items():
        m &= (frame[col] == val).to_numpy()
    return frame[m].reset_index(drop=True)


def assert_other_configurations_identical(a, b, changed):
    """The archive rule: every row with k != changed is bit-identical between two runs; tables without k are identical."""
    for name in a:
        x, y = a[name], b[name]
        if "k" in x.columns:
            x, y = x[x["k"] != changed].reset_index(drop=True), y[y["k"] != changed].reset_index(drop=True)
        assert len(x) > 0 or len(a[name]) == 0 or set(a[name]["k"]) == {changed}
        pd.testing.assert_frame_equal(x, y, check_exact=True)


def assert_frames_equal_under_reindexing(small, full, kmap=None, imap=None, pair=False, columns=None):
    """Rows of a run on a sub-grid equal, bit for bit, the same rows of the full run (count independence)."""
    f = full
    icols = ("i_a", "i_b") if pair else ("i",)
    if kmap is not None:
        f = f[f["k"].isin(kmap)].assign(k=lambda d: d["k"].map({k: n for n, k in enumerate(kmap)}).astype(np.int32))
    if imap is not None:
        for c in icols:
            f = f[f[c].isin(imap)]
        f = f.assign(**{c: f[c].map({i: n for n, i in enumerate(imap)}).astype(np.int32) for c in icols})
    keys = [c for c in ("k", "i", "i_a", "i_b", "band", "band_a", "band_b", "j", "t") if c in f.columns]
    f, s = f.sort_values(keys).reset_index(drop=True), small.sort_values(keys).reset_index(drop=True)
    if columns is not None:
        f, s = f[columns], s[columns]
    pd.testing.assert_frame_equal(s, f, check_exact=True)


@functools.cache
def fixture_build():
    """(build directory, manifest) of the one-series fixture, built once for the track A test modules."""
    from rattractor.build import build
    from rattractor.runspec import load_run_spec

    root = Path(tempfile.mkdtemp(prefix="rattractor-track-a-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    out = build(load_run_spec("fixture_six_regime.yaml"), load_config(), root)
    return out, json.loads((out / "manifest.json").read_text())


@functools.cache
def three_series_grid(ks=(0, 4, 11, 23, 37, 42, 53)):
    """Stage 9's frames for three synthetic series, restricted to a few configurations of each method."""
    from rattractor.stages import fibers, fit, grid, register
    from tests.stages.test_grid import three_series

    cfg = load_config()
    series, calendar = three_series(cfg)
    reg = register.run(cfg)
    states, _ = fit.run(series, reg, cfg)
    coords = list(fibers.fiber_index(reg, cfg)["config_id"])
    months, t_of = grid.holdout(series, calendar)
    Z, ids = [], []
    for n, (sid, g) in enumerate(series.groupby("series_id", sort=False, observed=True)):
        Z.append(grid.series_rows(str(sid), n, g, states, coords, t_of[str(sid)], cfg))
        ids.append(str(sid))
    frames = grid.assemble(Z, ids, reg, coords, months, t_of, calendar, cfg, "test:v1", "build-x")
    return subgrid(frames, ks=ks)


# ---- the shared Morlet machinery ---------------------------------------------------------------

def test_period_grid_follows_the_rule(cfg):
    p = wavelets.periods(98, cfg)
    assert p.size == 33 and p[0] == 2.0 and p[-1] == pytest.approx(32.0) and p[-1] <= 98 / 3
    np.testing.assert_allclose(p[1:] / p[:-1], 2 ** (1 / 8), rtol=1e-12)
    assert wavelets.periods(96, cfg).size == 33          # 96 / 3 = 32 is itself on the grid and is kept
    assert wavelets.periods(95, cfg).size == 32
    assert wavelets.periods(5, cfg).size == 0            # 5 / 3 < the shortest period: no scale
    s = wavelets.scales(p, cfg)
    np.testing.assert_allclose(s, p * (6 + np.sqrt(38)) / (4 * np.pi), rtol=1e-12)
    assert wavelets.periods(98, {**cfg, "wavelet.period_max_rule": "P / 2"})[-1] == pytest.approx(2 * 2 ** (36 / 8))


def test_transform_is_the_stated_fourier_sum(cfg, rng):
    # W[j, t] = (1 / M) sum_k xhat[k] psihat_j[k] exp(2 pi i k t / M), written out without an FFT
    P = 24
    x = rng.standard_normal(P)
    s = wavelets.scales(wavelets.periods(P, cfg), cfg)
    M = wavelets.pad_length(P, s)
    assert M >= P + 6 * np.sqrt(2) * s.max() and M & (M - 1) == 0
    k = np.arange(1, M // 2 + 1)
    g = np.exp(-0.5 * (s[:, None] * 2 * np.pi * k / M - 6.0) ** 2)
    g *= np.sqrt(M / (g ** 2).sum(axis=1, keepdims=True))
    xhat = (x[None, :] * np.exp(-2j * np.pi * k[:, None] * np.arange(P)[None, :] / M)).sum(axis=1)
    want = (xhat[None, :, None] * g[:, :, None] * np.exp(2j * np.pi * k[None, :, None] * np.arange(P)[None, None, :] / M)).sum(axis=1) / M
    np.testing.assert_allclose(wavelets.transform(x, s, cfg), want, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(wavelets.transform(np.stack([x, 2 * x]), s, cfg)[0], wavelets.transform(x, s, cfg))  # rows on their own


def test_white_noise_has_mean_normalized_power_one_at_every_scale(cfg):
    rng = np.random.default_rng(101)
    P, rows = 128, 2400
    s = wavelets.scales(wavelets.periods(P, cfg), cfg)
    coi = wavelets.coi_mask(s, P)
    total = np.zeros(s.size)
    for _ in range(rows // 400):
        W = wavelets.transform(rng.standard_normal((400, P)), s, cfg)
        total += np.array([(np.abs(W[:, j, coi[j]]) ** 2).mean() for j in range(s.size)])
    mean_power = total / (rows // 400)
    assert np.abs(mean_power - 1.0).max() < 0.06, mean_power
    # Torrence and Compo's continuous factor would leave the shortest period at about half of that
    M = wavelets.pad_length(P, s)
    w = 2 * np.pi * np.arange(1, M // 2 + 1) / M
    tc = 2 * np.pi * s[0] / np.sqrt(np.pi) * np.exp(-(s[0] * w - 6.0) ** 2)
    assert 0.5 < tc.sum() / M < 0.6
    np.testing.assert_allclose((wavelets.daughters(s, M, 6.0) ** 2).sum(axis=1), M, rtol=1e-12)


def test_coi_mask_depends_on_scale_and_length_only(cfg):
    s = wavelets.scales(wavelets.periods(98, cfg), cfg)
    coi = wavelets.coi_mask(s, 98)
    for j in (0, 12, 32):
        inside = [t for t in range(98) if t >= np.sqrt(2) * s[j] and 97 - t >= np.sqrt(2) * s[j]]
        assert np.flatnonzero(coi[j]).tolist() == inside
    assert coi[0].sum() == 92 and coi[32].sum() == 10 and (np.diff(coi.sum(axis=1)) <= 0).all()


def test_ar1_spectrum_is_normalized():
    w = 2 * np.pi * (np.arange(4096) + 0.5) / 4096
    for a in (-0.5, 0.0, 0.3, 0.9):
        assert wavelets.ar1_spectrum(a, 2 * np.pi / w).mean() == pytest.approx(1.0, rel=1e-9)
    assert wavelets.ar1_spectrum(0.7, np.array([2.0, 200.0]))[1] > 5 > 1 > wavelets.ar1_spectrum(0.7, np.array([2.0]))[0]


# ---- known answers on planted rows --------------------------------------------------------------

def test_a_sinusoid_peaks_at_the_scale_of_its_fourier_period(cfg):
    P = 128
    per = wavelets.periods(P, cfg)
    js = [8, 16, 19, 24, 30]
    t = np.arange(P)
    R = np.stack([np.sin(2 * np.pi * t / per[j] + 0.4 * n) for n, j in enumerate(js)])[None]
    b, _ = wavelet.run(make_grid(R), cfg)
    cw = b["wavelet_cwt"]
    gws = cw[cw["in_coi"]].groupby(["i", "j"])["power"].mean().unstack()
    assert gws.to_numpy().argmax(axis=1).tolist() == js
    # the phase advances by 2 pi / period a month at that scale
    for n, j in enumerate(js):
        row = rows_of(cw, i=n, j=j)
        ph = row.loc[row["in_coi"], "phase"].to_numpy()
        step = np.angle(np.exp(1j * np.diff(ph)))
        np.testing.assert_allclose(step, 2 * np.pi / per[j], atol=0.02)


def test_red_noise_rows_exceed_their_own_level_at_about_the_nominal_rate(cfg):
    rng = np.random.default_rng(102)
    R = ar1_rows(rng, (2, 150, 128), 0.6)
    b, _ = wavelet.run(make_grid(R), cfg)
    cw = b["wavelet_cwt"]
    rate = cw.loc[cw["in_coi"], "significant"].mean()
    assert 0.035 < rate < 0.065, rate
    by_scale = cw[cw["in_coi"]].groupby("j")["significant"].mean()
    assert by_scale.max() < 0.10 and by_scale.min() > 0.02, by_scale.to_dict()


def test_series_moments_and_thresholds(cfg, rng):
    R = rng.standard_normal((2, 3, 72)) * np.array([1.0, 3.0, 0.2])[None, :, None] + np.array([0.0, 5.0, -2.0])[None, :, None]
    b, info = wavelet.run(make_grid(R), cfg)
    se = b["wavelet_series"]
    x = R[1, 2]
    xc = x - x.mean()
    row = rows_of(se, k=1, i=2).iloc[0]
    assert row["mean"] == pytest.approx(x.mean(), rel=1e-13) and row["variance"] == pytest.approx((xc ** 2).mean(), rel=1e-13)
    assert row["ar1"] == pytest.approx((xc[1:] * xc[:-1]).sum() / (xc ** 2).sum(), rel=1e-12)
    per = b["wavelet_scale"]["period"].to_numpy()
    thr = rows_of(b["wavelet_red_noise"], k=1, i=2)["threshold"].to_numpy()
    a = row["ar1"]
    want = row["variance"] * (1 - a * a) / (1 + a * a - 2 * a * np.cos(2 * np.pi / per)) * stats.chi2.ppf(0.95, 2) / 2
    np.testing.assert_allclose(thr, want, rtol=1e-12)
    assert stats.chi2.ppf(0.95, 2) / 2 == pytest.approx(-np.log(0.05))
    assert info["scales"] == per.size == 29 and info["padded_length"] == wavelets.pad_length(72, b["wavelet_scale"]["scale"].to_numpy())
    # the transform is of the centred row: adding a constant to a row changes its mean and nothing else
    b2, _ = wavelet.run(make_grid(R + 7.0), cfg)
    np.testing.assert_allclose(b2["wavelet_cwt"]["power"], b["wavelet_cwt"]["power"], rtol=0, atol=1e-9)
    np.testing.assert_allclose(b2["wavelet_series"]["mean"], b["wavelet_series"]["mean"] + 7.0, rtol=1e-12)


def test_cells_outside_the_cone_are_kept_flagged_and_never_counted(cfg, rng):
    P = 98
    R = rng.standard_normal((1, 2, P))
    R[0, 0, 0] += 40.0            # a spike in the first month: power far above the red-noise level at the left edge
    b, _ = wavelet.run(make_grid(R), cfg)
    cw, sc = b["wavelet_cwt"], b["wavelet_scale"]
    J = len(sc)
    assert len(cw) == 1 * 2 * J * P                                          # nothing is dropped
    edge = rows_of(cw, i=0, t=cw["t"].min())
    thr = rows_of(b["wavelet_red_noise"], i=0)["threshold"].to_numpy()
    assert (edge["power"].to_numpy() > thr).sum() >= 20 and not edge["in_coi"].any() and not edge["significant"].any()
    assert (cw.loc[~cw["in_coi"], "power"] > 0).all() and not cw.loc[~cw["in_coi"], "significant"].any()   # kept, not zeroed, not counted
    months = np.sort(cw["t"].unique())
    tidx = np.searchsorted(months, cw["t"].to_numpy())
    reach = np.sqrt(2) * sc["scale"].to_numpy()[cw["j"].to_numpy()]
    np.testing.assert_array_equal(cw["in_coi"].to_numpy(), (tidx >= reach) & (P - 1 - tidx >= reach))
    assert cw.groupby("j")["in_coi"].sum().tolist() == [2 * n for n in wavelets.coi_mask(sc["scale"].to_numpy(), P).sum(axis=1)]


def test_dense_reads_a_long_table_whatever_its_row_order(cfg, rng):
    R = rng.standard_normal((2, 3, 60))
    frames = make_grid(R)
    b, _ = wavelet.run(frames, cfg)
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    J = len(b["wavelet_scale"])
    cw = b["wavelet_cwt"]
    power = wavelet.dense(cw, "power", (2, 3, J, 60), months)
    np.testing.assert_array_equal(power, cw["power"].to_numpy().reshape(2, 3, J, 60))
    np.testing.assert_array_equal(wavelet.dense(cw.sample(frac=1.0, random_state=3), "power", (2, 3, J, 60), months), power)
    assert wavelet.dense(cw, "in_coi", (2, 3, J, 60), months).dtype == bool
    np.testing.assert_allclose(wavelet.dense(b["wavelet_series"], "variance", (2, 3)), R.var(axis=2), rtol=1e-13)
    with pytest.raises(AcceptanceError, match="not a dense field"):
        wavelet.dense(cw.iloc[1:], "power", (2, 3, J, 60), months)
    with pytest.raises(AcceptanceError, match="does not cover every cell"):
        wavelet.dense(pd.concat([cw.iloc[1:], cw.iloc[1:2]]), "power", (2, 3, J, 60), months)


# ---- the archive rule and count independence ----------------------------------------------------

@pytest.fixture(scope="module")
def planted(cfg):
    rng = np.random.default_rng(103)
    R = ar1_rows(rng, (4, 3, 96), 0.4)
    R[:, 1] += 2.0 * np.sin(2 * np.pi * np.arange(96) / 16.0)
    frames = make_grid(R)
    built, info = wavelet.run(frames, cfg)
    return R, frames, built, info


def test_changing_one_configuration_leaves_every_other_row_bit_identical(planted, cfg):
    R, _, built, _ = planted
    R2 = R.copy()
    R2[2] = np.random.default_rng(7).standard_normal(R[2].shape) * 5.0
    other, _ = wavelet.run(make_grid(R2), cfg)
    assert_other_configurations_identical(built, other, changed=2)
    assert not rows_of(built["wavelet_cwt"], k=2)["power"].equals(rows_of(other["wavelet_cwt"], k=2)["power"])


def test_rows_do_not_depend_on_how_many_series_or_configurations_there_are(planted, cfg):
    _, frames, built, _ = planted
    ks, iis = [3, 1], [2, 0]
    small, _ = wavelet.run(subgrid(frames, ks=ks, iis=iis), cfg)
    for name in ("wavelet_series", "wavelet_red_noise", "wavelet_cwt"):
        assert_frames_equal_under_reindexing(small[name], built[name], kmap=ks, imap=iis)
    pd.testing.assert_frame_equal(small["wavelet_scale"], built["wavelet_scale"], check_exact=True)


# ---- acceptance ---------------------------------------------------------------------------------

def _with(b, name, **cols):
    return {**b, name: b[name].assign(**cols)}


@pytest.mark.parametrize("rule, corrupt", [
    ("periods start at wavelet.period_min", lambda b: _with(b, "wavelet_scale", period=b["wavelet_scale"]["period"] * 1.01)),
    ("scale equals period over the Morlet Fourier factor", lambda b: _with(b, "wavelet_scale", scale=b["wavelet_scale"]["scale"] * 1.01)),
    ("variance > 0 and |ar1| < 1", lambda b: _with(b, "wavelet_series", ar1=1.0)),
    ("threshold equals variance x P_ar1", lambda b: _with(b, "wavelet_red_noise", threshold=b["wavelet_red_noise"]["threshold"] * 1.001)),
    ("in_coi follows from the scale and P alone", lambda b: _with(b, "wavelet_cwt", in_coi=True)),
    ("power equals w_re^2 + w_im^2", lambda b: _with(b, "wavelet_cwt", power=b["wavelet_cwt"]["power"] * 1.0001)),
    ("amplitude and phase are the polar form", lambda b: _with(b, "wavelet_cwt", phase=b["wavelet_cwt"]["phase"] * 0.5)),
    ("amplitude and phase are the polar form", lambda b: _with(b, "wavelet_cwt", amplitude=b["wavelet_cwt"]["amplitude"] * 1.001)),
    ("significant equals in_coi and power > threshold", lambda b: _with(b, "wavelet_cwt", significant=True)),
    ("significant equals in_coi and power > threshold", lambda b: _with(b, "wavelet_cwt", significant=False)),
])
def test_check_rules_fire_with_rows(planted, cfg, rule, corrupt):
    _, frames, built, _ = planted
    wavelet.check(built, frames, cfg)  # the clean output passes
    with pytest.raises(AcceptanceError, match=re.escape(rule)) as err:
        wavelet.check(corrupt(built), frames, cfg)
    assert err.value.rows is not None and err.value.rows["problem"].str.contains(rule, regex=False).any()


def test_check_counts_rows(planted, cfg):
    _, frames, built, _ = planted
    with pytest.raises(AcceptanceError, match="wavelet_cwt has"):
        wavelet.check({**built, "wavelet_cwt": built["wavelet_cwt"].iloc[1:].reset_index(drop=True)}, frames, cfg)


def test_a_constant_row_is_refused_with_its_keys(cfg, rng):
    R = rng.standard_normal((2, 2, 60))
    R[1, 0] = 3.25
    with pytest.raises(AcceptanceError, match="constant rows") as err:
        wavelet.run(make_grid(R), cfg)
    assert err.value.rows[["k", "i"]].values.tolist() == [[1, 0]]


def test_too_few_months_for_any_scale_is_refused(cfg, rng):
    with pytest.raises(AcceptanceError, match="no scale"):
        wavelet.run(make_grid(rng.standard_normal((1, 1, 5))), cfg)


def test_artifacts_round_trip(tmp_path, planted):
    *_, built, _ = planted
    for name, f in built.items():
        back = contracts.read(contracts.write(f, name, tmp_path / f"{name}.parquet"), name)
        pd.testing.assert_frame_equal(back, f)


@pytest.mark.parametrize("key, value, match", [
    ("wavelet.period_max_rule", "P / 0.5", "period_max_rule"),
    ("wavelet.period_max_rule", "a third", "period_max_rule"),
    ("wavelet.significance", 1.0, "strictly between"),
    ("wavelet.family", "paul", "not in"),
    ("wavelet.omega0", 2.0, "< 5.0"),
    ("wavelet.period_min", 1.0, "< 2.0"),
])
def test_wavelet_config_validation(key, value, match):
    c = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    c[key] = value
    with pytest.raises(ContractError, match=match):
        validate_config(c)


# ---- on built grids -----------------------------------------------------------------------------

def test_three_series_grid(cfg):
    frames = three_series_grid()
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    built, info = wavelet.run(frames, cfg)
    J = info["scales"]
    assert (K, N, P) == (7, 3, 168) and J == len(wavelets.periods(P, cfg)) == 39
    assert len(built["wavelet_cwt"]) == K * N * J * P and len(built["wavelet_series"]) == K * N
    r = frames["grid_resid"]
    x = rows_of(r, k=4, i=1).sort_values("t")["resid"].to_numpy()
    s = built["wavelet_scale"]["scale"].to_numpy()
    W = wavelets.transform(x - x.mean(), s, cfg)
    got = rows_of(built["wavelet_cwt"], k=4, i=1).sort_values(["j", "t"])
    np.testing.assert_array_equal(got["w_re"].to_numpy().reshape(J, P), W.real)
    np.testing.assert_array_equal(got["w_im"].to_numpy().reshape(J, P), W.imag)


def test_one_series_fixture_build_writes_the_transform(cfg):
    out, m = fixture_build()
    assert "wavelet" in m["stages_passed"] and m["stages_passed"].index("wavelet") == m["stages_passed"].index("compare") + 1
    K, P, J = m["configurations"]["admissible"], m["grid"]["rdiag_minimums"]["P"], m["wavelet"]["scales"]
    rows = {rel: a["rows"] for rel, a in m["artifacts"].items() if rel.startswith("wavelet/")}
    assert rows == {"wavelet/scale.parquet": J, "wavelet/series.parquet": K, "wavelet/red_noise.parquet": K * J, "wavelet/cwt.parquet": K * J * P}
    cw = contracts.read(out / "wavelet/cwt.parquet", "wavelet_cwt")
    assert set(cw["i"]) == {0} and cw["k"].nunique() == K and m["wavelet"]["padded_length"] >= P
