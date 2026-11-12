"""Residual attractor space: the upstream of the residual diagnostic pipeline.

Builds configurations, forecast steps and residual fibers over any set of series,
per the Residual Attractor Space Architecture Specification (Oct 1, 2026).
"""

from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PKG_ROOT / "schemas"
CONFIG_DIR = PKG_ROOT / "configs"


class ContractError(ValueError):
    """An artifact or config does not satisfy its schema."""


__all__ = ["PKG_ROOT", "SCHEMA_DIR", "CONFIG_DIR", "ContractError"]
