"""Milestone 1 gate: every schema round-trips; bad frames and configs are refused."""

import numpy as np
import pandas as pd
import pytest
import yaml

from rattractor import CONFIG_DIR, ContractError, contracts
from rattractor.config import load_config, load_registry_grids, validate_config
from rattractor.fixtures import six_regime
from rattractor.registry import build_registry


def test_series_round_trip(cfg, tmp_path):
    df, _ = six_regime(cfg)
    path = contracts.write(df, "series", tmp_path / "series.parquet")
    back = contracts.read(path, "series")
    pd.testing.assert_frame_equal(df, back)


def test_registry_round_trip(cfg, tmp_path):
    reg = build_registry(load_registry_grids(cfg), cfg)
    back = contracts.read(contracts.write(reg, "registry", tmp_path / "r.parquet"), "registry")
    pd.testing.assert_frame_equal(reg, back)


def test_empty_frames_validate():
    for artifact in ("series", "registry", "states"):
        contracts.validate(contracts.empty_frame(artifact), artifact)


def test_extra_column_refused(cfg):
    df, _ = six_regime(cfg)
    with pytest.raises(ContractError, match="columns"):
        contracts.validate(df.assign(extra=1), "series")


def test_reordered_columns_refused(cfg):
    df, _ = six_regime(cfg)
    with pytest.raises(ContractError, match="columns"):
        contracts.validate(df[["t", "series_id", "y", "split"]], "series")


def test_no_coercion(cfg):
    df, _ = six_regime(cfg)
    with pytest.raises(ContractError, match="dtype"):
        contracts.validate(df.assign(t=df["t"].astype("int64")), "series")
    with pytest.raises(ContractError, match="dtype"):
        contracts.validate(df.assign(series_id=df["series_id"].astype(object)), "series")


def test_null_in_non_null_refused(cfg):
    df, _ = six_regime(cfg)
    y = df["y"].to_numpy().copy()
    y[3] = np.nan
    with pytest.raises(ContractError, match="null"):
        contracts.validate(df.assign(y=y), "series")


def test_duplicate_key_refused(cfg):
    df, _ = six_regime(cfg)
    with pytest.raises(ContractError, match="duplicate"):
        contracts.validate(pd.concat([df, df.iloc[:1]], ignore_index=True), "series")


def test_default_config_loads():
    load_config()


def test_missing_key_fails():
    cfg = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    del cfg["sigma.window"]
    with pytest.raises(ContractError, match="missing"):
        validate_config(cfg)


def test_unknown_key_fails():
    cfg = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    cfg["sigma.windw"] = 40
    with pytest.raises(ContractError, match="unknown"):
        validate_config(cfg)


def test_wrong_type_fails():
    cfg = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    cfg["horizon.H"] = True
    with pytest.raises(ContractError, match="bool"):
        validate_config(cfg)
