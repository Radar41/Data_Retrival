"""The Method interface every forecasting family implements.

Nothing in the stages branches on method name. A family is a filtering
recursion: fit() runs it over the whole series once, and the state stored at t
uses observations at or before t only, so slicing at an origin o never sees
data after o (checked by the leakage test).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Fitted:
    method: str
    theta: dict
    y: np.ndarray        # the series the recursion ran over, length N
    s1: np.ndarray       # state after observing y_t, series units
    s2: np.ndarray       # second state component, method units
    yhat1: np.ndarray    # one-step forecast of y_t made at t-1; NaN at t = 0
    aux: dict = field(default_factory=dict)  # family-specific arrays the forecast needs

    @property
    def e1(self) -> np.ndarray:
        return self.y - self.yhat1


class Method(ABC):
    name: str
    param_names: tuple[str, ...]
    state_names: tuple[str, str]
    forecast_is: str  # "s1" or "s1_plus_s2": how forecast relates to state_forward

    def __init__(self, cfg: dict):
        self.cfg = cfg

    # ---- parameter space -------------------------------------------------
    @abstractmethod
    def admissible(self, theta: dict) -> bool: ...

    @abstractmethod
    def fisher(self, theta: dict) -> tuple[np.ndarray | None, float | None]:
        """(Fisher metric in params order or None, stratum coordinate F or None).

        F is defined where the configuration sits on a one-parameter stratum
        (a nesting face such as AR(1) inside AR(2)); elsewhere it is None and
        ell is reported as not defined.
        """

    def stratum(self, theta: dict) -> str:
        return self.name

    # ---- recursion ---------------------------------------------------------
    @abstractmethod
    def fit(self, y: np.ndarray, theta: dict) -> Fitted: ...

    def state(self, fitted: Fitted, t: int) -> tuple[float, float]:
        return float(fitted.s1[t]), float(fitted.s2[t])

    @abstractmethod
    def state_forward(self, fitted: Fitted, o: int, H: int) -> tuple[np.ndarray, np.ndarray]:
        """(s1, s2) the forecast equation carries at steps h = 1..H from origin o."""

    def forecast(self, fitted: Fitted, o: int, H: int) -> np.ndarray:
        s1, s2 = self.state_forward(fitted, o, H)
        if self.forecast_is == "s1":
            return s1
        if self.forecast_is == "s1_plus_s2":
            return s1 + s2
        raise ValueError(f"{self.name}: unknown forecast_is {self.forecast_is!r}")

    # ---- helpers -----------------------------------------------------------
    def _check(self, y: np.ndarray, theta: dict) -> np.ndarray:
        y = np.asarray(y, dtype=np.float64)
        if y.ndim != 1 or y.size < 2:
            raise ValueError(f"{self.name}: y must be a 1-D array of length >= 2")
        if not np.isfinite(y).all():
            raise ValueError(f"{self.name}: y has non-finite values")
        if set(theta) != set(self.param_names):
            raise ValueError(f"{self.name}: theta keys {sorted(theta)} != {sorted(self.param_names)}")
        if not self.admissible(theta):
            raise ValueError(f"{self.name}: theta {theta} outside the admissible region")
        return y

    @staticmethod
    def _check_origin(fitted: Fitted, o: int, H: int) -> None:
        if not (0 <= o < fitted.y.size):
            raise IndexError(f"origin {o} outside 0..{fitted.y.size - 1}")
        if H < 1:
            raise ValueError("H must be >= 1")
