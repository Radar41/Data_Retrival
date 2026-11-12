"""Holt's linear trend, Holt(alpha, beta).

State: s1 = level l_t, s2 = trend b_t.
Forward from o: s1 = l_o + h b_o, s2 = b_o, forecast = s1.
With init b_0 = 0, beta = 0 keeps b at 0 and the family reduces to SES(alpha):
that is the nesting face, checked as an invariant.
"""

from __future__ import annotations

import numpy as np

from .base import Fitted, Method
from .ses import SES


class Holt(Method):
    name = "holt"
    param_names = ("alpha", "beta")
    state_names = ("level", "trend")
    forecast_is = "s1"

    def admissible(self, theta: dict) -> bool:
        return 0.0 < theta["alpha"] <= 1.0 and 0.0 <= theta["beta"] <= 1.0

    def stratum(self, theta: dict) -> str:
        return "ses" if theta["beta"] == 0.0 else "holt"

    def fisher(self, theta: dict):
        # On the beta = 0 face the configuration is SES(alpha), whose coordinate is closed form.
        if theta["beta"] == 0.0:
            _, F = SES(self.cfg).fisher({"alpha": theta["alpha"]})
            return None, F
        return None, None  # spec decision 12: numerical metric not yet implemented

    def fit(self, y, theta) -> Fitted:
        y = self._check(y, theta)
        if self.cfg["methods.holt.init"] != "first_value_zero_trend":
            raise ValueError("unsupported methods.holt.init")
        a, b_ = float(theta["alpha"]), float(theta["beta"])
        n = y.size
        level = np.empty(n)
        trend = np.empty(n)
        yhat1 = np.full(n, np.nan)
        level[0], trend[0] = y[0], 0.0
        for t in range(1, n):
            yhat1[t] = level[t - 1] + trend[t - 1]
            level[t] = a * y[t] + (1.0 - a) * (level[t - 1] + trend[t - 1])
            trend[t] = b_ * (level[t] - level[t - 1]) + (1.0 - b_) * trend[t - 1]
        return Fitted(self.name, dict(theta), y, level, trend, yhat1)

    def state_forward(self, fitted, o, H):
        self._check_origin(fitted, o, H)
        h = np.arange(1, H + 1)
        return fitted.s1[o] + h * fitted.s2[o], np.full(H, fitted.s2[o])
