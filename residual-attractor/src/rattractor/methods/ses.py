"""Simple exponential smoothing, SES(alpha).

State: s1 = level l_t, s2 = the update alpha * (y_t - l_{t-1}).
Forward from o: s1 = l_o, s2 = 0, forecast = l_o.
Equivalent to ARIMA(0,1,1) with MA coefficient alpha - 1 (known-answer test).
"""

from __future__ import annotations

import numpy as np

from .base import Fitted, Method


class SES(Method):
    name = "ses"
    param_names = ("alpha",)
    state_names = ("level", "update")
    forecast_is = "s1"

    def admissible(self, theta: dict) -> bool:
        return 0.0 < theta["alpha"] <= 1.0

    def fisher(self, theta: dict):
        # ARIMA(0,1,1) form: MA coefficient m = alpha - 1; MA(1) Fisher information
        # per unit innovation variance is 1 / (1 - m^2); its arc-length coordinate is arcsin(m).
        m = theta["alpha"] - 1.0
        if abs(m) >= 1.0:
            return None, None
        return np.array([[1.0 / (1.0 - m * m)]]), float(np.arcsin(m))

    def fit(self, y, theta) -> Fitted:
        y = self._check(y, theta)
        if self.cfg["methods.ses.init"] != "first_value":
            raise ValueError("unsupported methods.ses.init")
        a = float(theta["alpha"])
        n = y.size
        level = np.empty(n)
        update = np.empty(n)
        yhat1 = np.full(n, np.nan)
        level[0] = y[0]
        update[0] = 0.0
        for t in range(1, n):
            yhat1[t] = level[t - 1]
            update[t] = a * (y[t] - level[t - 1])
            level[t] = level[t - 1] + update[t]
        return Fitted(self.name, dict(theta), y, level, update, yhat1)

    def state_forward(self, fitted, o, H):
        self._check_origin(fitted, o, H)
        return np.full(H, fitted.s1[o]), np.zeros(H)
