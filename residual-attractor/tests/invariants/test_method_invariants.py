"""Conformance suite every Method passes, plus nesting faces and leakage."""

import numpy as np
import pytest

from rattractor.config import load_registry_grids
from rattractor.fixtures import six_regime
from rattractor.methods import AR, FAMILIES, SES, Holt, get_method
from rattractor.registry import build_registry

THETAS = {
    "ses": {"alpha": 0.4},
    "ar": {"phi1": 0.6, "phi2": -0.3},
    "holt": {"alpha": 0.4, "beta": 0.2},
}
FIXED = sorted(n for n, c in FAMILIES.items() if c.theta_spec == "fixed")  # estimated families: tests/unit/test_gdss.py


@pytest.fixture(scope="module")
def y(cfg):
    df, _ = six_regime(cfg)
    return df["y"].to_numpy()


@pytest.mark.parametrize("name", FIXED)
def test_conformance(cfg, y, name):
    m = get_method(name, cfg)
    assert len(m.state_names) == 2 and all(m.state_names)
    f = m.fit(y, THETAS[name])
    n = y.size
    for arr in (f.s1, f.s2, f.yhat1):
        assert arr.shape == (n,)
    assert np.isnan(f.yhat1[0]) and np.isfinite(f.yhat1[1:]).all()
    o, H = 200, 20
    s1, s2 = m.state_forward(f, o, H)
    fc = m.forecast(f, o, H)
    assert s1.shape == s2.shape == fc.shape == (H,)
    expected = s1 if m.forecast_is == "s1" else s1 + s2
    np.testing.assert_array_equal(fc, expected)
    # The one-step forecast from o equals the in-sample yhat1 at o + 1.
    assert fc[0] == pytest.approx(f.yhat1[o + 1], abs=1e-12)


@pytest.mark.parametrize("name", FIXED)
def test_no_leakage(cfg, y, name):
    m = get_method(name, cfg)
    o, H = 180, 20
    base = m.fit(y, THETAS[name])
    y2 = y.copy()
    y2[o + 1 :] += np.random.default_rng(0).normal(0, 50, y.size - o - 1)
    pert = m.fit(y2, THETAS[name])
    np.testing.assert_array_equal(base.s1[: o + 1], pert.s1[: o + 1])
    np.testing.assert_array_equal(base.s2[: o + 1], pert.s2[: o + 1])
    np.testing.assert_array_equal(m.forecast(base, o, H), m.forecast(pert, o, H))


@pytest.mark.parametrize("alpha", [0.2, 0.6, 1.0])
def test_holt_beta0_is_ses(cfg, y, alpha):
    h = Holt(cfg).fit(y, {"alpha": alpha, "beta": 0.0})
    s = SES(cfg).fit(y, {"alpha": alpha})
    np.testing.assert_allclose(h.yhat1[1:], s.yhat1[1:], atol=1e-12)
    np.testing.assert_allclose(Holt(cfg).forecast(h, 250, 20), SES(cfg).forecast(s, 250, 20), atol=1e-12)


def test_ar_phi2_zero_is_ar1(cfg, y):
    m = AR(cfg)
    f = m.fit(y, {"phi1": 0.7, "phi2": 0.0})
    o = 250
    mu = f.s1[o]
    np.testing.assert_allclose(m.forecast(f, o, 10), mu + 0.7 ** np.arange(1, 11) * (y[o] - mu), atol=1e-12)


def test_inadmissible_refused(cfg, y):
    with pytest.raises(ValueError, match="admissible"):
        AR(cfg).fit(y, {"phi1": 0.9, "phi2": 0.3})


def test_registry_identity_and_ell(cfg):
    reg = build_registry(load_registry_grids(cfg), cfg)
    assert reg["config_id"].is_unique
    ok = reg[reg["ell_status"] == "closed_form"]["ell"]
    assert ok.between(0.0, 1.0).all()
    # Every SES config, the AR(1) face and Holt's beta = 0 face have a closed-form ell.
    ar = reg[reg["method"] == "ar"]
    import json
    face = ar[ar["params"].map(lambda p: json.loads(p)["phi2"] == 0.0)]
    assert (face["ell_status"] == "closed_form").all()
    assert (reg[reg["method"] == "ses"]["ell_status"] == "closed_form").all()
    # Inadmissible AR(2) cells are registered, flagged, never fitted.
    assert (~ar["admissible"]).any()
    assert (ar.loc[~ar["admissible"], "ell_status"] == "not_admissible").all()
