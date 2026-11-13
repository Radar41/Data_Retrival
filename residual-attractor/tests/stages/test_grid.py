"""Stage 9: the archive as rdiag's input field (reworked contract v2, no fused configuration)."""

import json

import numpy as np
import pandas as pd
import pytest

from rattractor import contracts, fixtures
from rattractor.build import build
from rattractor.runspec import load_run_spec
from rattractor.stages import AcceptanceError, fit, forecast, grid, register


def three_series(cfg, lengths=(360, 372, 348), test_from=180, start="2000-01-01", seed=0, ids=("S2", "S0", "S1")):
    """Three synthetic monthly series sharing a calendar start; their ends differ. ids are in run-spec order, not sorted."""
    rng = np.random.default_rng(seed)
    parts, cals = [], []
    for j, n in enumerate(lengths):
        sid = ids[j]
        y = np.cumsum(rng.normal(size=n)) + 10 * j
        per = pd.date_range(start, periods=n, freq="MS")
        parts.append({"series_id": [sid] * n, "t": np.arange(n), "y": y, "split": np.where(np.arange(n) < test_from, "train", "test")})
        cals.append({"series_id": [sid] * n, "t": np.arange(n), "period": [d.date().isoformat() for d in per],
                     "imputed": np.zeros(n, bool), "first_release": [(d + pd.offsets.MonthBegin(1)).date().isoformat() for d in per]})
    cat = lambda ps: {k: np.concatenate([p[k] for p in ps]) for k in ps[0]}
    return contracts.from_columns(cat(parts), "series"), contracts.from_columns(cat(cals), "calendar")


@pytest.fixture(scope="module")
def field(cfg):
    series, calendar = three_series(cfg)
    reg = register.run(cfg)
    states, cache = fit.run(series, reg, cfg)
    coords = list(reg.loc[reg["admissible"], "config_id"])
    months, t_of = grid.holdout(series, calendar)
    Z, ids, steps_by = [], [], {}
    for n, (sid, g) in enumerate(series.groupby("series_id", sort=False, observed=True)):
        steps = forecast.run_series(str(sid), g, reg, states, cfg, cache[str(sid)])
        steps_by[str(sid)] = steps
        Z.append(grid.series_rows(str(sid), n, g, states, coords, t_of[str(sid)], cfg, steps))
        ids.append(str(sid))
    frames = grid.assemble(Z, ids, reg, coords, months, t_of, calendar, cfg, "test:v1", "build-x")
    return series, calendar, reg, states, steps_by, months, t_of, frames


def test_holdout_is_the_months_every_series_covers(field):
    series, calendar, *_ = field
    months, t_of = grid.holdout(series, calendar)
    assert months[0] == pd.Timestamp("2015-01-01")              # every test split starts at t = 180
    assert months[-1] == pd.Timestamp("2000-01-01") + pd.offsets.MonthBegin(347)  # the shortest series ends first
    assert all(len(t) == len(months) for t in t_of.values())


def test_holdout_refuses_a_series_missing_a_month(cfg):
    series, calendar = three_series(cfg)
    cal = calendar.copy()
    cal.loc[(cal["series_id"] == "S0") & (cal["t"] == 200), "period"] = "2016-09-15"
    with pytest.raises(AcceptanceError, match="monthly"):
        grid.holdout(series, contracts.validate(cal, "calendar"))


def test_resid_is_each_configurations_e1_over_its_own_sigma_at_t_minus_1(cfg, field):
    series, calendar, reg, states, _, months, t_of, frames = field
    r = frames["grid_resid"]
    W, ddof = cfg["sigma.window"], cfg["sigma.ddof"]
    names = frames["grid_names"]
    kname = dict(zip(names.loc[names.axis == "k", "idx"], names.loc[names.axis == "k", "name"].str.split().str[0]))
    for _, row in r.sample(200, random_state=2).iterrows():
        sid = ["S2", "S0", "S1"][int(row["i"])]
        e1 = states[(states.series_id == sid) & (states.config_id == kname[int(row["k"])])].sort_values("t")["e1"].to_numpy()
        t = int(t_of[sid][list(months).index(row["t"])])
        y = series[series.series_id == sid]["y"].to_numpy()
        floor = forecast.series_floor(y[:180], cfg)
        sd = max(np.std(e1[t - W : t], ddof=ddof), floor)          # the W one-step residuals ending at t - 1
        assert row["resid"] == pytest.approx(e1[t] / sd, rel=1e-12)


def test_resid_matches_the_archive_where_they_overlap(cfg, field):
    series, calendar, reg, states, steps_by, months, t_of, _ = field
    sid = "S2"
    g = series[series.series_id == sid]
    coords = list(reg.loc[reg["admissible"], "config_id"])
    bad = steps_by[sid].copy()
    i = bad.index[(bad.ladder == "forward") & (bad.h == 1)][3]
    bad.loc[i, "e"] = bad.loc[i, "e"] * 1.001
    with pytest.raises(AcceptanceError, match="disagree with the archive") as err:
        grid.series_rows(sid, 0, g, states, coords, t_of[sid], cfg, bad)
    assert len(err.value.rows) == 1


def test_no_value_is_pooled_across_configurations(cfg, field):
    series, calendar, reg, states, _, months, t_of, frames = field
    coords = list(reg.loc[reg["admissible"], "config_id"])
    some = coords[::7][::-1]
    g = series[series.series_id == "S1"]
    full = grid.series_rows("S1", 2, g, states, coords, t_of["S1"], cfg)
    part = grid.series_rows("S1", 2, g, states, some, t_of["S1"], cfg)
    np.testing.assert_array_equal(part, full[[coords.index(c) for c in some]])


def test_provenance_rows(field):
    _, calendar, _, _, _, months, t_of, frames = field
    p, r = frames["grid_provenance"], frames["grid_resid"]
    assert len(p) == len(r) and not p.duplicated(["k", "i", "t", "vintage_id"]).any()
    assert (p["data_cutoff"] == p["t"] - pd.offsets.MonthBegin(1)).all() and (p["data_cutoff"] < p["t"]).all()
    assert (p["release_date"] == p["t"] + pd.offsets.MonthBegin(1)).all()  # the synthetic calendar's rule
    assert set(p["vintage_id"]) == {"test:v1"} and set(p["model_run_id"]) == {"build-x"}


def test_config_attrs_and_names(cfg, field):
    _, _, reg, _, _, months, _, frames = field
    adm = reg[reg["admissible"]].reset_index(drop=True)
    c = frames["grid_config"]
    assert c["k"].tolist() == list(range(len(adm))) and c["core_spec_id"].tolist() == adm["core_spec_id"].tolist()
    assert all(list(e) == [] for e in c["exog_set"])
    assert list(frames["grid_attrs"]["horizon"]) == [1]
    assert frames["grid_attrs"]["standardization_id"].iloc[0] == grid.standardization_id(cfg)
    n = frames["grid_names"]
    assert n.loc[n.axis == "i", "name"].tolist() == ["S2", "S0", "S1"]  # run-spec order, not sorted
    assert n.loc[n.axis == "k", "name"].str.split().str[0].tolist() == adm["config_id"].tolist()
    assert list(frames["grid_config"].columns) == ["k", "core_spec_id", "exog_set"]  # v2: no is_fused, no member_ks


def test_rdiag_input_checks_pass(field):
    # The checks rdiag's loader runs on its input tables, other than the fused ones.
    *_, frames = field
    r, m, c, s, p = (frames[x] for x in ("grid_resid", "grid_month", "grid_config", "grid_series", "grid_provenance"))
    K, N, P = len(c), len(s), len(m)
    assert K >= 2 and N >= 3 and P >= 60
    assert len(r) == K * N * P and not r.duplicated(["k", "i", "t"]).any()
    ords = (m["t"].dt.year * 12 + m["t"].dt.month).sort_values().to_numpy()
    assert (np.diff(ords) == 1).all() and (m["t"].dt.day == 1).all()
    assert np.isfinite(r["resid"]).all()
    cover = p.groupby(["k", "i", "t"]).size()
    assert len(cover) == len(r) and (p["data_cutoff"] < p["t"]).all()
    assert grid.minimums(frames) == {"K": K, "N": N, "P": P, "K>=2": True, "N>=3": True, "P>=60": True}


@pytest.mark.parametrize("corrupt, match", [
    (lambda f: {**f, "grid_resid": f["grid_resid"].iloc[1:].reset_index(drop=True)}, "not dense"),
    (lambda f: {**f, "grid_resid": f["grid_resid"].assign(resid=np.where(np.arange(len(f["grid_resid"])) == 5, np.inf, f["grid_resid"]["resid"]))}, "non-finite"),
    (lambda f: {**f, "grid_provenance": f["grid_provenance"].assign(data_cutoff=f["grid_provenance"]["t"])}, "data_cutoff before t"),
    (lambda f: {**f, "grid_month": f["grid_month"].iloc[::2].reset_index(drop=True)}, "contiguous"),
])
def test_grid_check_fires(field, corrupt, match):
    *_, frames = field
    grid.check(frames)
    with pytest.raises(AcceptanceError, match=match):
        grid.check(corrupt(frames))


def test_artifacts_round_trip(tmp_path, field):
    *_, frames = field
    for name, f in frames.items():
        back = contracts.read(contracts.write(f, name, tmp_path / f"{name}.parquet"), name)
        if name == "grid_config":
            assert [list(x) for x in back["exog_set"]] == [list(x) for x in f["exog_set"]]
            back, f = back.drop(columns=["exog_set"]), f.drop(columns=["exog_set"])
        pd.testing.assert_frame_equal(back, f)


def test_fixture_build_writes_the_grid_and_reports_rdiag_minimums(cfg, tmp_path):
    out = build(load_run_spec("fixture_six_regime.yaml"), cfg, tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    g = m["grid"]
    assert m["stages_passed"][-2:] == ["grid", "compare"] and g["contract"].startswith("rdiag input v2")
    assert g["rdiag_minimums"]["N"] == 1 and g["rdiag_minimums"]["N>=3"] is False
    for name, rel in g["files"].items():
        assert rel in m["artifacts"] and len(contracts.read(out / rel, name)) == m["artifacts"][rel]["rows"]
    assert_build_grid(out, m, cfg)


def assert_build_grid(out, m, cfg):
    """Every k of a built grid holds the configuration its name says, and provenance names this build and vintage."""
    r = contracts.read(out / "grid/resid.parquet", "grid_resid")
    names = contracts.read(out / "grid/names.parquet", "grid_names")
    states = contracts.read(out / "states.parquet", "states")
    series = contracts.read(out / "series.parquet", "series")
    cal = contracts.read(out / "calendar.parquet", "calendar")
    kname = dict(zip(names.loc[names.axis == "k", "idx"], names.loc[names.axis == "k", "name"].str.split().str[0]))
    iname = dict(zip(names.loc[names.axis == "i", "idx"], names.loc[names.axis == "i", "name"]))
    W, ddof = cfg["sigma.window"], cfg["sigma.ddof"]
    first = r[r["t"] == r["t"].min()]
    for _, row in first.iterrows():
        sid, cid = iname[int(row["i"])], kname[int(row["k"])]
        s = series[series.series_id == sid].sort_values("t")
        ts = int((s["split"] == "test").to_numpy().argmax())
        e1 = states[(states.series_id == sid) & (states.config_id == cid)].sort_values("t")["e1"].to_numpy()
        c = cal[cal.series_id == sid]
        t = int(c.loc[pd.to_datetime(c["period"]) == row["t"], "t"].iloc[0])
        sd = max(np.std(e1[t - W : t], ddof=ddof), forecast.series_floor(s["y"].to_numpy()[:ts], cfg))
        assert row["resid"] == pytest.approx(e1[t] / sd, rel=1e-12)
    p = contracts.read(out / "grid/provenance.parquet", "grid_provenance")
    assert set(p["vintage_id"]) == {m["grid"]["vintage_id"]} and set(p["model_run_id"]) == {m["build_id"]}


def test_failed_grid_overlap_check_stops_the_build(cfg, tmp_path, monkeypatch):
    # A different floor in the grid's own sigma: its residuals disagree with stage 4's, and the build must stop there.
    monkeypatch.setattr(grid, "series_floor", lambda y_train, cfg: 1e12)
    with pytest.raises(AcceptanceError, match="disagree with the archive"):
        build(load_run_spec("fixture_six_regime.yaml"), cfg, tmp_path)
    assert list((tmp_path / "reports").glob("*/grid.parquet"))
    assert not list((tmp_path / "builds").glob("*/manifest.json"))


def test_the_sigma_floor_applies_where_a_window_is_flat(cfg, field):
    series, calendar, reg, states, _, months, t_of, _ = field
    sid, cid = "S2", reg.loc[reg["admissible"], "config_id"].iloc[0]
    W, t0 = cfg["sigma.window"], int(t_of["S2"][0])
    st = states.copy()
    sel = (st.series_id == sid) & (st.config_id == cid)
    st.loc[sel & (st.t >= t0 - W) & (st.t < t0), "e1"] = 0.0
    st.loc[sel & (st.t == t0), "e1"] = 0.25
    g = series[series.series_id == sid]
    Z = grid.series_rows(sid, 0, g, st, [cid], t_of[sid], cfg)
    floor = forecast.series_floor(g.sort_values("t")["y"].to_numpy()[:180], cfg)
    assert np.isfinite(Z[0, 0]) and Z[0, 0] == pytest.approx(0.25 / floor, rel=1e-12)


def test_datetime_columns_are_not_coerced(field):
    *_, frames = field
    with pytest.raises(contracts.ContractError, match="dtype"):
        contracts.validate(frames["grid_month"].astype({"t": "datetime64[us]"}), "grid_month")
