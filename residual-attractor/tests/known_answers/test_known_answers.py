"""Closed-form cases with exact expected values (spec: Validation and test plan)."""

import numpy as np
import pytest
from scipy.integrate import quad

from rattractor import fixtures
from rattractor.methods import AR, SES, Holt


def arima011_one_step(y: np.ndarray, m: float) -> np.ndarray:
    """Independent ARIMA(0,1,1) innovations recursion: yhat_{t+1} = y_t + m * e_t, e_0 = 0."""
    yhat = np.full(y.size, np.nan)
    e = 0.0
    for t in range(y.size - 1):
        yhat[t + 1] = y[t] + m * e
        e = y[t + 1] - yhat[t + 1]
    return yhat


@pytest.mark.parametrize("alpha", [0.1, 0.35, 0.8, 1.0])
def test_ses_equals_arima011(cfg, rng, alpha):
    y = fixtures.random_walk(300, rng) + fixtures.trend(300, rng)
    f = SES(cfg).fit(y, {"alpha": alpha})
    expected = arima011_one_step(y, alpha - 1.0)
    np.testing.assert_allclose(f.yhat1[1:], expected[1:], rtol=0, atol=1e-10)
    # Multi-step: both are flat at the one-step forecast.
    o = 200
    np.testing.assert_allclose(SES(cfg).forecast(f, o, 20), np.full(20, f.yhat1[o + 1]), atol=1e-10)


def test_ar1_fisher_length_is_pi(cfg):
    ar = AR(cfg)
    g11 = lambda p: ar.fisher({"phi1": p, "phi2": 0.0})[0][0, 0]
    length, _ = quad(lambda p: np.sqrt(g11(p)), -1.0, 1.0, limit=200)
    assert abs(length - np.pi) < 1e-6
    # And F = arcsin is that arc length's coordinate.
    assert ar.fisher({"phi1": 0.5, "phi2": 0.0})[1] == pytest.approx(np.arcsin(0.5))


@pytest.mark.parametrize("alpha", [0.2, 0.7])
def test_constant_series_ses(cfg, alpha):
    y = fixtures.constant(100)
    f = SES(cfg).fit(y, {"alpha": alpha})
    np.testing.assert_array_equal(f.e1[1:], 0.0)
    np.testing.assert_array_equal(SES(cfg).forecast(f, 50, 20), 10.0)


def test_trend_ses_error_grows_linearly(cfg, rng):
    # Noise-free trend so the claim is exact: SES's h-step error grows by the slope per step.
    y = 0.5 * np.arange(400.0)
    m = SES(cfg)
    f = m.fit(y, {"alpha": 0.5})
    o = 300
    err = y[o + 1 : o + 21] - m.forecast(f, o, 20)
    np.testing.assert_allclose(np.diff(err), 0.5, atol=1e-9)


def test_holt_with_true_slope_tracks_trend(cfg, rng):
    y = fixtures.trend(400, rng, slope=0.5, sd=1.0)
    m = Holt(cfg)
    f = m.fit(y, {"alpha": 0.2, "beta": 0.1})
    o = 300
    err = y[o + 1 : o + 21] - m.forecast(f, o, 20)
    sd1 = np.nanstd(f.e1[100:o])
    assert np.mean(np.abs(err) / sd1 < 2.5) > 0.8


def test_sinusoid_period8_lag4_anticorrelated(cfg):
    y = fixtures.sinusoid(400, period=8)
    r = np.corrcoef(y[4:], y[:-4])[0, 1]
    assert r < -0.99


def test_ar1_matched_forecast(cfg, rng):
    y = fixtures.ar1(2000, rng, phi=0.7)
    m = AR(cfg)
    f = m.fit(y, {"phi1": 0.7, "phi2": 0.0})
    o = 1500
    fc = m.forecast(f, o, 5)
    mu = f.s1[o]
    np.testing.assert_allclose(fc, mu + 0.7 ** np.arange(1, 6) * (y[o] - mu), atol=1e-12)
    # Matched model leaves one-step residuals nearly white.
    e = f.e1[200:]
    rho1 = np.corrcoef(e[1:], e[:-1])[0, 1]
    assert abs(rho1) < 2.0 / np.sqrt(e.size) * 2
