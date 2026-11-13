"""Load and validate the build config. No defaults: a missing or unknown key fails."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from . import CONFIG_DIR, SCHEMA_DIR, ContractError

_TYPES = {"int": int, "float": (int, float), "str": str, "bool": bool, "list": list}


def _key_spec() -> dict:
    return yaml.safe_load((SCHEMA_DIR / "config.yaml").read_text())


def validate_config(cfg: dict) -> dict:
    spec = _key_spec()
    missing = sorted(set(spec) - set(cfg))
    unknown = sorted(set(cfg) - set(spec))
    if missing:
        raise ContractError(f"config missing keys: {missing}")
    if unknown:
        raise ContractError(f"config has unknown keys: {unknown}")
    for key, rule in spec.items():
        value = cfg[key]
        want = _TYPES[rule["type"]]
        # bool is an int subclass; keep the two apart.
        if isinstance(value, bool) and rule["type"] != "bool":
            raise ContractError(f"config {key}: bool given, {rule['type']} required")
        if not isinstance(value, want):
            raise ContractError(f"config {key}: {type(value).__name__} given, {rule['type']} required")
        if "values" in rule and value not in rule["values"]:
            raise ContractError(f"config {key}: {value!r} not in {rule['values']}")
        if "min" in rule and value < rule["min"]:
            raise ContractError(f"config {key}: {value} < {rule['min']}")
        if "max" in rule and value > rule["max"]:
            raise ContractError(f"config {key}: {value} > {rule['max']}")
    mw = cfg["methods.ar.mean_window"]
    if mw != "expanding" and not (mw.isdigit() and int(mw) >= 2):
        raise ContractError(f"config methods.ar.mean_window: {mw!r} is not 'expanding' or an integer >= 2")
    _validate_cadence(cfg)
    if not 1 <= cfg["lagcorr.K"] <= 127:
        raise ContractError(f"config lagcorr.K: {cfg['lagcorr.K']} must lie in 1..127 (k is stored as int8)")
    if cfg["lagcorr.min_pairs"] > cfg["lagcorr.window"]:
        raise ContractError(f"config lagcorr.min_pairs: {cfg['lagcorr.min_pairs']} exceeds lagcorr.window {cfg['lagcorr.window']}")
    return cfg


def _validate_cadence(cfg: dict) -> None:
    from .stages.cadence import CADENCE_RULES  # the rule names live with the rules

    th = cfg["thresholds"]
    if len(th) != 4 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in th) \
            or not all(a < b for a, b in zip([0, *th[:-1]], th)):  # 0 < t1 < t2 < t3 < t4
        raise ContractError(f"config thresholds: {th} is not four ascending positive levels (h1..h4)")
    if not any(cfg["cadence.fail_level"] == x for x in th):
        raise ContractError(f"config cadence.fail_level: {cfg['cadence.fail_level']} is not one of thresholds {th}")
    osc = cfg["cadence.oscillation_levels"]
    if not osc or not all(any(k == x for x in th) for k in osc):
        raise ContractError(f"config cadence.oscillation_levels: {osc} is not a non-empty subset of thresholds {th}")
    labels = cfg["cadence.labels"]
    if sorted(labels) != sorted(CADENCE_RULES) or labels[-1] != "Mixed":
        raise ContractError(f"config cadence.labels: {labels} must name each of {list(CADENCE_RULES)} once, with Mixed (the catch-all) last")


def load_config(path: Path | None = None) -> dict:
    path = Path(path) if path else CONFIG_DIR / "default.yaml"
    cfg = yaml.safe_load(path.read_text())
    if not isinstance(cfg, dict):
        raise ContractError(f"{path}: not a mapping")
    return validate_config(cfg)


def config_sha256(cfg: dict) -> str:
    """Hash of the config's content, independent of key order and formatting."""
    canonical = yaml.safe_dump(cfg, sort_keys=True, default_flow_style=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_registry_grids(cfg: dict) -> list[dict]:
    grids = []
    for name in cfg["registry.files"]:
        path = CONFIG_DIR / "registry" / name
        grid = yaml.safe_load(path.read_text())
        for key in ("method", "grid_axes", "params"):
            if key not in grid:
                raise ContractError(f"{path}: missing {key}")
        if not set(grid["grid_axes"]) <= set(grid["params"]):
            raise ContractError(f"{path}: grid_axes not all in params")
        grids.append(grid)
    return grids
