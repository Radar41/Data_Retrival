"""Stage 2, register: config grids -> registry artifact, with its acceptance checks."""

from __future__ import annotations

import pandas as pd

from ..config import load_registry_grids
from ..methods import get_method
from ..registry import build_registry
from . import AcceptanceError


def run(cfg: dict) -> pd.DataFrame:
    reg = build_registry(load_registry_grids(cfg), cfg)
    check(reg, cfg)
    return reg


def check(reg: pd.DataFrame, cfg: dict) -> None:
    if not reg["config_id"].is_unique:
        raise AcceptanceError("register", "config_id not unique", reg[reg["config_id"].duplicated(keep=False)])
    for m in reg["method"].unique():
        names = get_method(str(m), cfg).state_names
        if len(names) != 2 or not all(names):
            raise AcceptanceError("register", f"{m} does not declare s1 and s2")
    ell = reg["ell"].dropna()
    if not ell.between(0.0, 1.0).all():
        raise AcceptanceError("register", "ell outside [0, 1]", reg[~reg["ell"].between(0.0, 1.0) & reg["ell"].notna()])
    if not reg["admissible"].any():
        raise AcceptanceError("register", "no admissible configuration")
