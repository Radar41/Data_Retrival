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
    inst = cfg["compare.cpa_instruments"]
    if not inst or len(set(inst)) != len(inst) or not set(inst) <= {"const", "d_lag1"}:
        raise ContractError(f"config compare.cpa_instruments: {inst} must be distinct names from [const, d_lag1]")
    if cfg["lagcorr.min_pairs"] > cfg["lagcorr.window"]:
        raise ContractError(f"config lagcorr.min_pairs: {cfg['lagcorr.min_pairs']} exceeds lagcorr.window {cfg['lagcorr.window']}")
    # Track A (wavelet, spectral, coherence, adjacency): levels strictly inside (0, 1), and the period rule's form.
    from .common.wavelets import period_max_divisor  # the rule's form lives with the code that reads it

    for key in ("wavelet.significance", "coherence.quantile", "inference.q"):
        if not 0.0 < cfg[key] < 1.0:
            raise ContractError(f"config {key}: {cfg[key]} must lie strictly between 0 and 1")
    try:
        period_max_divisor(cfg["wavelet.period_max_rule"])
    except ValueError as err:
        raise ContractError(f"config {err}") from None
    for key in ("spectral_summary.c_delta", "spectral_summary.gamma_decorrelation", "spectral_summary.dj0_decorrelation"):
        if not cfg[key] > 0:
            raise ContractError(f"config {key}: {cfg[key]} must be positive")
    # tails, events, coincidence (rdiag s2d, s3.events, s3.coincidence): the rules that span keys or list entries
    from .stages.tails import COUNT_RULE  # the rule a count may follow lives with the stage that resolves it

    whole = lambda x: isinstance(x, int) and not isinstance(x, bool)
    number = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    ng = cfg["tails.n_tail_grid"]
    if len(ng) != 2 or not all((whole(x) and x >= 1) or (isinstance(x, str) and COUNT_RULE.fullmatch(x)) for x in ng) \
            or (whole(ng[0]) and whole(ng[1]) and ng[0] > ng[1]):
        raise ContractError(f"config tails.n_tail_grid: {ng} is not [lowest, highest], each an integer >= 1 or the text 'floor(P / d)'")
    tq = cfg["tails.threshold_grid_quantiles"]
    if len(tq) != 3 or not all(number(x) for x in tq) or not (0 < tq[0] <= tq[1] < 1 and tq[2] > 0):
        raise ContractError(f"config tails.threshold_grid_quantiles: {tq} is not [first, last, step] with 0 < first <= last < 1 and step > 0")
    if cfg["tails.rolling_n_tail"] >= cfg["tails.rolling_window"]:
        raise ContractError(f"config tails.rolling_n_tail: {cfg['tails.rolling_n_tail']} must be below tails.rolling_window {cfg['tails.rolling_window']}")
    if not cfg["tails.gpd_shape_min"] < 0:
        raise ContractError(f"config tails.gpd_shape_min: {cfg['tails.gpd_shape_min']} must lie in [-0.5, 0)")
    from .stages.events import KINDS, RULES, WAITS_FOR

    kinds = cfg["events.kinds"]
    if not kinds or len(set(kinds)) != len(kinds) or not set(kinds) <= set(KINDS):
        raise ContractError(f"config events.kinds: {kinds} must name at least one of {list(KINDS)}, each once")
    if set(kinds) - set(RULES):
        raise ContractError("config events.kinds: " + "; ".join(f"{k} is not built yet, it waits for {WAITS_FOR[k]}" for k in kinds if k not in RULES))
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
