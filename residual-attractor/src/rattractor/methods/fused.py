"""The fused configuration: the equal-weight mean of its members' forecasts.

theta = {"members": [{"method": ..., "params": {...}}, ...]}, every member a
registered parameter configuration (never another fused one), stored sorted by
config_id. The registry builds one fused row over every admissible parameter
configuration (configs/registry/fused.yaml),
so its config_id and core_spec_id are its own: rdiag compares members against it
with Diebold-Mariano, not Clark-West (reconciliation issue 5).

State: s1 = consensus, the mean of the members' forecasts for t+1 made at t;
s2 = dispersion, the standard deviation (ddof 0) of those member forecasts.
Forward from o: s1 = mean, s2 = sd of the members' h-step forecasts; forecast = s1.
psi: the mean of the members' psi weights, which is exact when every member's
h-step error is its own psi-filter of one shared innovation sequence.
It has no parameter space, so ell does not apply.
"""

from __future__ import annotations

import numpy as np

from .base import Fitted, Method


class Fused(Method):
    name = "fused"
    param_names = ("members",)
    state_names = ("consensus", "dispersion")
    forecast_is = "s1"
    is_fusion = True

    def _members(self, theta: dict) -> list[tuple[Method, dict]]:
        from . import get_method  # the package registers this class, so import late

        return [(get_method(m["method"], self.cfg), m["params"]) for m in theta["members"]]

    def admissible(self, theta: dict) -> bool:
        members = theta["members"]
        if not isinstance(members, list) or len(members) < 2:
            return False
        try:
            pairs = self._members(theta)
        except (KeyError, TypeError):
            return False
        return all(not m.is_fusion and set(th) == set(m.param_names) and m.admissible(th) for m, th in pairs)

    def fisher(self, theta: dict):
        return None, None

    def stratum(self, theta: dict) -> str:
        return self.name

    def psi(self, theta, H):
        return np.mean([m.psi(th, H) for m, th in self._members(theta)], axis=0)

    def fit(self, y, theta) -> Fitted:
        y = self._check(y, theta)
        members = [(m, m.fit(y, th)) for m, th in self._members(theta)]
        n = y.size
        # Member one-step forecasts made at t for t + 1: yhat1[t + 1], and at the last t the forecast itself.
        F = np.empty((len(members), n))
        for i, (m, f) in enumerate(members):
            F[i, :-1] = f.yhat1[1:]
            F[i, -1] = m.forecast(f, n - 1, 1)[0]
        consensus, dispersion = F.mean(axis=0), F.std(axis=0)
        yhat1 = np.full(n, np.nan)
        yhat1[1:] = consensus[:-1]
        return Fitted(self.name, dict(theta), y, consensus, dispersion, yhat1, aux={"members": members})

    def state_forward(self, fitted, o, H):
        self._check_origin(fitted, o, H)
        F = np.stack([m.forecast(f, o, H) for m, f in fitted.aux["members"]])
        return F.mean(axis=0), F.std(axis=0)
