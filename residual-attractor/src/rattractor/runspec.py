"""Run specifications: which series a build runs on and how they are read.

A run spec is data, not code: the machinery is the same for any series list,
and the spec only records the choice (plan section 0). Keys are fixed by
schemas/run_spec.yaml; nothing is defaulted.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import yaml

from . import PKG_ROOT, SCHEMA_DIR, ContractError
from .config import _TYPES

RUNS_DIR = PKG_ROOT / "runs"


def _check(key: str, value, rule: dict) -> None:
    want = _TYPES[rule["type"]]
    if isinstance(value, bool) and rule["type"] != "bool":
        raise ContractError(f"run spec {key}: bool given, {rule['type']} required")
    if not isinstance(value, want):
        raise ContractError(f"run spec {key}: {type(value).__name__} given, {rule['type']} required")
    if "values" in rule and value not in rule["values"]:
        raise ContractError(f"run spec {key}: {value!r} not in {rule['values']}")


def _date(key: str, value: str) -> None:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise ContractError(f"run spec {key}: {value!r} is not YYYY-MM-DD") from None


def validate_run_spec(spec: dict) -> dict:
    rules = yaml.safe_load((SCHEMA_DIR / "run_spec.yaml").read_text())
    catalog_rules = rules.pop("catalog")
    top = set(rules) | ({"catalog"} if spec.get("source") == "catalog" else set())
    missing, unknown = sorted(top - set(spec)), sorted(set(spec) - top)
    if missing or unknown:
        raise ContractError(f"run spec: missing {missing}, unknown {unknown}")
    for k, rule in rules.items():
        _check(k, spec[k], rule)
    if spec["source"] == "catalog":
        cat = spec["catalog"]
        if not isinstance(cat, dict):
            raise ContractError("run spec catalog: not a mapping")
        missing, unknown = sorted(set(catalog_rules) - set(cat)), sorted(set(cat) - set(catalog_rules))
        if missing or unknown:
            raise ContractError(f"run spec catalog: missing {missing}, unknown {unknown}")
        for k, rule in catalog_rules.items():
            _check(f"catalog.{k}", cat[k], rule)
        if cat["max_interpolate"] < 0:
            raise ContractError("run spec catalog.max_interpolate: must be >= 0")
        _date("catalog.as_of", cat["as_of"])
        _date("catalog.test_start", cat["test_start"])
        s = cat["series"]
        if not s or not all(isinstance(x, str) and x for x in s) or len(set(s)) != len(s):
            raise ContractError("run spec catalog.series: need a non-empty list of distinct series_id strings")
    return spec


def load_run_spec(path: Path) -> dict:
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = RUNS_DIR / path
    spec = yaml.safe_load(path.read_text())
    if not isinstance(spec, dict):
        raise ContractError(f"{path}: not a mapping")
    return validate_run_spec(spec)


def run_spec_sha256(spec: dict) -> str:
    return hashlib.sha256(yaml.safe_dump(spec, sort_keys=True, default_flow_style=True).encode()).hexdigest()
