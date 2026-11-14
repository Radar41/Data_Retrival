"""The GDSS bridge without MATLAB: estimated registry rows, the Precomputed family, the cube checks, and a
fixture build whose estimated configuration reads a cube written here the way gdss.run_rattractor_request
writes it (a naive forecast, which the build must reproduce)."""

import json

import numpy as np
import pandas as pd
import pytest

from rattractor import gdss
from rattractor.build import build
from rattractor.config import load_config, load_registry_grids
from rattractor.methods import get_method, precomputed
from rattractor.registry import build_registry, config_id
from rattractor.runspec import load_run_spec
from rattractor.stages import AcceptanceError, register

POLICY = {"refit_every": 12, "window": "expanding", "min_train": 24}


def gdss_cfg(cfg, files):
    return {**cfg, "registry.files": list(files)}


def test_gdss_config_registers_every_family():
    cfg = load_config(load_config.__globals__["CONFIG_DIR"] / "gdss.yaml")
    reg = register.run(cfg)
    est = reg[reg["theta_spec"] == "estimated"]
    assert est.groupby("method").size().to_dict() == {
        "gdss.arima": 17, "gdss.damped_trend": 1, "gdss.ets": 6, "gdss.local_level": 1,
        "gdss.local_linear_trend": 1, "gdss.lsboost": 4, "gdss.naive": 1}
    assert est["admissible"].all() and (est["ell_status"] == "estimated").all() and est["ell"].isna().all()
    # The policy is part of the identity, and (0, 0, 0) is excluded.
    a = est[est["method"] == "gdss.arima"]
    ps = [json.loads(p) for p in a["params"]]
    assert all({**POLICY}.items() <= p.items() for p in ps)
    assert not any(p["arima_p"] == p["arima_d"] == p["arima_q"] == 0 for p in ps)
    theta = {"arima_p": 1, "arima_d": 1, "arima_q": 1, **POLICY}
    assert config_id("gdss.arima", "estimated", theta) in set(a["config_id"])
    assert config_id("gdss.arima", "estimated", {**theta, "refit_every": 1}) not in set(a["config_id"])


def test_precomputed_family_reads_the_cube():
    m = get_method("gdss.naive", {})
    y = np.arange(50.0) ** 1.1
    H1, i0 = 4, 23
    Y = np.full((50, H1), np.nan)
    S = np.full((50, H1), np.nan)
    Y[i0:] = np.c_[y[i0:], y[i0:] + 1, y[i0:] + 3, y[i0:] + 6]
    S[i0:] = np.c_[np.ones(27), 2 * np.ones(27), np.full(27, 3.0), np.full(27, 4.0)]
    cid = config_id("gdss.naive", "estimated", POLICY)
    precomputed.attach({precomputed.y_sha256(y): {cid: {"yhat": Y, "sd": S, "i0": i0}}})
    try:
        f = m.fit(y, POLICY)
        assert np.isnan(f.yhat1[: i0 + 1]).all() and np.array_equal(f.yhat1[i0 + 1:], y[i0:-1])
        assert np.array_equal(f.s1[i0:], y[i0:]) and np.allclose(f.s2[i0:], 1.0)
        s1, s2 = m.state_forward(f, 30, 3)
        np.testing.assert_allclose(s1, y[30] + np.array([0, 1, 3]))
        np.testing.assert_allclose(s2, [1, 2, 3])
        assert np.array_equal(m.forecast(f, 30, 3), s1)
        np.testing.assert_array_equal(m.sigma_h_factor_at(f, np.array([30, 30, 30]), np.array([1, 2, 3]), POLICY, 3), [1, 2, 3])
        assert m.first_issuance(f) == i0
        with pytest.raises(KeyError, match="not in the attached"):
            m.fit(y + 1, POLICY)
        with pytest.raises(ValueError, match="no forecast from issuance"):
            m.state_forward(f, 10, 3)
    finally:
        precomputed.detach()


def fake_cube(d, series, est, cfg, *, leak=False, gap=None):
    """What gdss.run_rattractor_request writes, for the naive adapter: yhat(i, h) = y_i, no forecast sd."""
    H1 = cfg["horizon.H"] + 1
    req = json.loads((d / "request.json").read_text())
    (d / "cube").mkdir(exist_ok=True)
    fits = []
    for sid, g in series.groupby("series_id", sort=False, observed=True):
        y = g["y"].to_numpy()
        rows = []
        for c in req["configurations"]:
            R, i0 = c["params"]["refit_every"], c["params"]["min_train"] - 1
            iss = np.arange(i0, y.size)
            ft = i0 + R * ((iss - i0) // R)
            if leak:
                ft = ft + 1
            T = pd.DataFrame({"series_id": str(sid), "config_id": c["config_id"], "issuance": iss.astype(np.int32),
                              "fit_through": ft.astype(np.int32), "status": np.where(iss == ft, "REFIT", "FILTERED")})
            for h in range(1, H1 + 1):
                T[f"yhat_{h:02d}"] = y[iss]
            for h in range(1, H1 + 1):
                T[f"sd_{h:02d}"] = np.nan
            if gap is not None:
                T.loc[T["issuance"] == gap, [f"yhat_{h:02d}" for h in range(1, H1 + 1)]] = np.nan
            rows.append(T)
            for i in iss[iss == ft]:
                fits.append({"series_id": str(sid), "config_id": c["config_id"], "issuance": int(i), "fit_through": int(i),
                             "status": "COMPLETE", "reason": "", "warnings": "", "log_likelihood": np.nan, "params_json": "",
                             "seconds": 0.0, "convergence_status": "NOT_APPLICABLE"})
        pd.concat(rows).to_parquet(d / "cube" / f"{sid}.parquet", index=False)
    pd.DataFrame(fits).astype({"issuance": np.int32, "fit_through": np.int32}).to_parquet(d / "fit_status.parquet", index=False)
    (d / "done.json").write_text(json.dumps({
        "request_id": req["request_id"], "matlab_version": "fake", "wall_seconds": 0, "workers": 1, "refits": len(fits),
        "refits_failed": 0, "refits_with_warnings": 0, "issuances_without_forecast": 0, "created": "test",
        "leakage": [{"config_id": c["config_id"], "cut": 0, "issuances_compared": 1, "identical": True} for c in req["configurations"]]}))


def test_fixture_build_with_an_estimated_family(cfg, tmp_path):
    spec = load_run_spec("fixture_six_regime.yaml")
    c = gdss_cfg(cfg, ["ses.yaml", "gdss_naive.yaml"])
    with pytest.raises(AcceptanceError, match="sbatch src/gdss_bridge.sbatch"):
        build(spec, c, tmp_path)
    (d,) = list((tmp_path / "external").iterdir())
    req = json.loads((d / "request.json").read_text())
    assert [x["adapter_id"] for x in req["configurations"]] == ["analytical.naive_random_walk"]
    series = pd.read_parquet(d / "series.parquet")
    reg = build_registry(load_registry_grids(c), c)
    fake_cube(d, series.assign(split="train"), gdss.estimated(reg), c)
    out = build(spec, c, tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    assert m["stages_passed"][:4] == ["ingest", "register", "gdss", "fit"]
    assert m["configurations"]["estimated"] == 1 and m["gdss"]["not_admissible"] == {}
    cid = req["configurations"][0]["config_id"]
    st = pd.read_parquet(out / "steps" / "SIX.parquet") if (out / "steps" / "SIX.parquet").exists() else \
        pd.concat(pd.read_parquet(p) for p in (out / "steps").glob("*.parquet"))
    nv = st[st["config_id"] == cid]
    ser = pd.read_parquet(out / "series.parquet")
    y = ser["y"].to_numpy()
    # The naive forecast from every issuance is y at the issuance, at every h; the scales follow the same rules.
    np.testing.assert_array_equal(nv["yhat"].to_numpy(), y[nv["issuance"].to_numpy()])
    assert (nv["sigma"] > 0).all() and (nv["sigma_h"] > 0).all()
    np.testing.assert_allclose(nv["sigma_h"], nv["sigma_g"].clip(lower=0), rtol=1e-12)  # no model sd: sigma_h = sigma x g_c(h)
    states = pd.read_parquet(out / "states.parquet")
    e1 = states[states["config_id"] == cid].sort_values("t")["e1"].to_numpy()
    assert np.isnan(e1[:24]).all() and np.allclose(e1[24:], np.diff(y)[23:])
    resid = pd.read_parquet(out / "grid" / "resid.parquet")
    assert resid["k"].nunique() == m["fiber"]["coordinates"] == 10   # 9 SES + 1 estimated
    assert (out / "gdss" / "fit_status.parquet").exists()


def test_cube_checks(cfg, tmp_path):
    spec = load_run_spec("fixture_six_regime.yaml")
    c = gdss_cfg(cfg, ["ses.yaml", "gdss_naive.yaml"])
    with pytest.raises(AcceptanceError):
        build(spec, c, tmp_path)
    (d,) = list((tmp_path / "external").iterdir())
    series = pd.read_parquet(d / "series.parquet")
    reg = build_registry(load_registry_grids(c), c)
    fake_cube(d, series, gdss.estimated(reg), c, leak=True)
    with pytest.raises(AcceptanceError, match="estimated on data after their issuance"):
        build(spec, c, tmp_path)
    fake_cube(d, series, gdss.estimated(reg), c, gap=100)   # one issuance without a forecast: not admissible for the run
    out = build(spec, c, tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    (why,) = m["gdss"]["not_admissible"].values()
    assert "no forecast from 1 issuances" in why and m["fiber"]["coordinates"] == 9
