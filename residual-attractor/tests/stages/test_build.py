"""The build driver: reproducible build_id, manifest hashes, reports on failure."""

import json

import pytest

from rattractor import contracts
from rattractor.build import build
from rattractor.manifest import file_sha256
from rattractor.runspec import load_run_spec
from rattractor.stages import AcceptanceError


def test_fixture_build_and_manifest(cfg, tmp_path):
    spec = load_run_spec("fixture_six_regime.yaml")
    out = build(spec, cfg, tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    assert m["build_id"] == out.name
    for rel, a in m["artifacts"].items():
        p = out / rel
        assert file_sha256(p) == a["sha256"]
        assert len(contracts.read(p, a["artifact"])) == a["rows"]
    assert m["stages_passed"] == ["ingest", "register", "fit", "forecast"]
    assert build(spec, cfg, tmp_path).name == out.name  # same inputs, same build_id


def test_config_change_changes_build_id(cfg, tmp_path):
    spec = load_run_spec("fixture_six_regime.yaml")
    a = build(spec, cfg, tmp_path).name
    b = build(spec, dict(cfg, **{"horizon.H": 10}), tmp_path).name
    assert a != b


def test_failed_check_writes_no_manifest(cfg, tmp_path):
    spec = load_run_spec("fixture_six_regime.yaml")
    # Origins start past N: forecast has nothing to do and must stop the build.
    with pytest.raises(AcceptanceError, match="no origins"):
        build(spec, dict(cfg, **{"sigma.window": 400}), tmp_path)
    assert not list((tmp_path / "builds").glob("*/manifest.json"))
