"""Families estimated at the origin by the GDSS adapters (MATLAB), read from their forecast cube.

The cube (rattractor.gdss.load) holds, per series and configuration, the forecasts yhat(i, h) and the
model's own forecast sd sd_m(i, h) issued at every issuance i = i0 .. N-1, h = 1..H+1, each from
parameters estimated on y(0..fit_through) with fit_through <= i and data through i only. A Precomputed
family turns that into the same Fitted the fixed families give, so every stage runs unchanged and
standardizes these configurations exactly as the fixed ones:

    yhat1(t)   = yhat(t - 1, 1)                       NaN for t <= i0
    s1(i)      = yhat(i, 1)                           forecast level
    s2(i)      = yhat(i, 2) - yhat(i, 1)              forecast slope
    state_forward(i, h) = (yhat(i, h), yhat(i, h + 1) - yhat(i, h)),   forecast = s1
    sigma_h factor at (i, h) = sd_m(i, h) / sd_m(i, 1)   NaN where the adapter has no forecast sd

The store is attached by the build for the length of one build (attach / detach); a series is found
by the SHA-256 of its values, so a cube made from other data is never read.
"""

from __future__ import annotations

import hashlib

import numpy as np

from .base import Fitted, Method

_STORE: dict[str, dict[str, dict]] = {}


def y_sha256(y: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(y, dtype=np.float64).tobytes()).hexdigest()


def attach(store: dict[str, dict[str, dict]]) -> None:
    """{y_sha256: {config_id: {"yhat": (N, H+1), "sd": (N, H+1), "i0": int}}} for the current build."""
    _STORE.clear()
    _STORE.update(store)


def detach() -> None:
    _STORE.clear()


class Precomputed(Method):
    theta_spec = "estimated"
    precomputed = True
    adapter_id: str = ""
    param_names: tuple[str, ...] = ()
    state_names = ("forecast_level", "forecast_slope")
    forecast_is = "s1"

    def admissible(self, theta: dict) -> bool:
        return True  # decided per run from the cube (rattractor.gdss.load)

    def fisher(self, theta: dict):
        return None, None  # parameters change with the origin: no fixed point carries a metric

    def psi(self, theta: dict, H: int) -> np.ndarray:
        raise NotImplementedError(f"{self.name}: the h-step shape comes from the model's own sd (sigma_h_factor_at)")

    def _record(self, y: np.ndarray, theta: dict) -> dict:
        from ..registry import config_id  # registry imports methods

        cid = config_id(self.name, self.theta_spec, theta)
        try:
            return _STORE[y_sha256(y)][cid]
        except KeyError:
            raise KeyError(f"{self.name} {cid}: not in the attached GDSS cube (series values or configuration differ)") from None

    def fit(self, y: np.ndarray, theta: dict) -> Fitted:
        y = np.asarray(y, dtype=np.float64)
        rec = self._record(y, theta)
        Y = rec["yhat"]
        if Y.shape[0] != y.size:
            raise ValueError(f"{self.name}: cube has {Y.shape[0]} issuances, series has {y.size}")
        yhat1 = np.full(y.size, np.nan)
        yhat1[1:] = Y[:-1, 0]
        return Fitted(self.name, dict(theta), y, Y[:, 0].copy(), Y[:, 1] - Y[:, 0], yhat1,
                      aux={"yhat": Y, "sd": rec["sd"], "i0": int(rec["i0"])})

    def state_forward(self, fitted: Fitted, o: int, H: int) -> tuple[np.ndarray, np.ndarray]:
        self._check_origin(fitted, o, H)
        row = fitted.aux["yhat"][o]
        if row.size < H + 1 or not np.isfinite(row[: H + 1]).all():
            raise ValueError(f"{self.name}: no forecast from issuance {o}")
        return row[:H].copy(), row[1 : H + 1] - row[:H]

    def first_issuance(self, fitted: Fitted) -> int:
        return fitted.aux["i0"]

    def sigma_h_factor_at(self, fitted: Fitted, issuance: np.ndarray, hh: np.ndarray, theta: dict, H: int) -> np.ndarray:
        sd = fitted.aux["sd"]
        with np.errstate(divide="ignore", invalid="ignore"):
            return sd[issuance, hh - 1] / sd[issuance, 0]


# family name in the registry -> GDSS adapter_id (gdss.create_model_adapter)
GDSS_ADAPTERS = {
    "gdss.naive": "analytical.naive_random_walk",
    "gdss.local_level": "matlab.ssm.local_level",
    "gdss.local_linear_trend": "matlab.ssm.local_linear_trend",
    "gdss.damped_trend": "matlab.ssm.damped_trend",
    "gdss.arima": "matlab.arima",
    "gdss.ets": "analytical.ets",
    "gdss.lsboost": "matlab.ml.lsboost",
}

FAMILIES = {
    name: type("Precomputed_" + name.split(".", 1)[1], (Precomputed,), {"name": name, "adapter_id": adapter})
    for name, adapter in GDSS_ADAPTERS.items()
}
