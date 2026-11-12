"""Autoregression about a running mean, AR(2)(phi1, phi2); AR(1) is the phi2 = 0 face.

State: s1 = running mean mu_t (expanding, or a trailing window from config),
s2 = predicted deviation for t+1: phi1 (y_t - mu_t) + phi2 (y_{t-1} - mu_t).
Forward from o: s1 = mu_o, s2 = d_{o+h} with d following the AR recursion,
forecast = s1 + s2. For AR(1) this is mu_o + phi^h (y_o - mu_o), as in the spec.
"""

from __future__ import annotations

import numpy as np

from .base import Fitted, Method


def _ar2_gamma(phi1: float, phi2: float) -> tuple[float, float]:
    """Autocovariances gamma0, gamma1 of a stationary AR(2) with unit innovation variance."""
    g0 = (1.0 - phi2) / ((1.0 + phi2) * ((1.0 - phi2) ** 2 - phi1**2))
    g1 = phi1 * g0 / (1.0 - phi2)
    return g0, g1


class AR(Method):
    name = "ar"
    param_names = ("phi1", "phi2")
    state_names = ("running_mean", "predicted_deviation")
    forecast_is = "s1_plus_s2"

    def admissible(self, theta: dict) -> bool:
        p1, p2 = theta["phi1"], theta["phi2"]
        # Stationarity triangle of AR(2), open.
        return abs(p2) < 1.0 and p1 + p2 < 1.0 and p2 - p1 < 1.0

    def stratum(self, theta: dict) -> str:
        return "ar1" if theta["phi2"] == 0.0 else "ar2"

    def fisher(self, theta: dict):
        p1, p2 = theta["phi1"], theta["phi2"]
        g0, g1 = _ar2_gamma(p1, p2)
        metric = np.array([[g0, g1], [g1, g0]])  # Fisher information per observation, unit variance
        F = float(np.arcsin(p1)) if p2 == 0.0 else None  # AR(1) face: g = 1/(1-phi^2), F = arcsin
        return metric, F

    def psi(self, theta, H):
        # psi_0 = 1, psi_1 = phi1, psi_j = phi1 psi_{j-1} + phi2 psi_{j-2}; the running mean is treated as known.
        p1, p2 = theta["phi1"], theta["phi2"]
        p = np.zeros(H)
        p[0] = 1.0
        if H > 1:
            p[1] = p1
        for j in range(2, H):
            p[j] = p1 * p[j - 1] + p2 * p[j - 2]
        return p

    def _running_mean(self, y: np.ndarray) -> np.ndarray:
        rule = self.cfg["methods.ar.mean_window"]
        c = np.cumsum(y)
        n = np.arange(1, y.size + 1)
        if rule == "expanding":
            return c / n
        w = int(rule)
        out = c / n
        if y.size > w:
            out[w:] = (c[w:] - c[:-w]) / w
        return out

    def fit(self, y, theta) -> Fitted:
        y = self._check(y, theta)
        p1, p2 = float(theta["phi1"]), float(theta["phi2"])
        mu = self._running_mean(y)
        y_lag = np.concatenate(([np.nan], y[:-1]))
        d0 = y - mu
        d1 = np.where(np.isnan(y_lag), 0.0, y_lag - mu)  # no lag before t = 0
        s2 = p1 * d0 + p2 * d1
        yhat1 = np.full(y.size, np.nan)
        yhat1[1:] = mu[:-1] + s2[:-1]
        return Fitted(self.name, dict(theta), y, mu, s2, yhat1)

    def state_forward(self, fitted, o, H):
        self._check_origin(fitted, o, H)
        p1, p2 = fitted.theta["phi1"], fitted.theta["phi2"]
        mu = fitted.s1[o]
        d_prev = fitted.y[o - 1] - mu if o >= 1 else 0.0
        d_cur = fitted.y[o] - mu
        dev = np.empty(H)
        for h in range(H):
            d_next = p1 * d_cur + p2 * d_prev
            dev[h] = d_next
            d_prev, d_cur = d_cur, d_next
        return np.full(H, mu), dev
