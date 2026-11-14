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
    assert m["stages_passed"] == ["ingest", "register", "fit", "forecast", "fibers", "cadence", "lagcorr", "bundle_summary", "grid", "compare",
                                  "wavelet", "spectral", "coherence", "adjacency", "tails", "events", "coincidence", "common_mode", "signatures"]
    assert {"tails/hill_curve.parquet", "tails/mean_excess.parquet", "tails/rolling_hill.parquet", "tails/thresholds.parquet",
            "events/flags.parquet", "coincidence/precursor.parquet"} <= set(m["artifacts"])
    assert m["artifacts"]["coincidence/precursor.parquet"]["rows"] == 0   # the fixture has one series: no pair to test
    # The fixture has one series: nothing to correlate across series, so the common mode writes every row with null values
    # and no signature is available.
    K, P = m["grid"]["rdiag_minimums"]["K"], m["grid"]["rdiag_minimums"]["P"]
    cm = {name: contracts.read(out / f"common_mode/{name}.parquet", f"common_mode_{name}") for name in ("month", "eigen", "vector")}
    assert [len(cm[name]) for name in ("month", "eigen", "vector")] == [K * P, K * P, K * P]
    assert cm["month"][["lambda1", "lambda1_q", "p_value", "absorption_ratio", "vector_turnover"]].isna().all().all()
    assert cm["eigen"]["eigenvalue"].isna().all() and cm["vector"]["loading"].isna().all() and (cm["month"]["n_surrogates"] == 0).all()
    assert m["common_mode"]["undefined"]["fewer_than_two_series"] and m["common_mode"]["window"] == cfg["common_mode.window"]
    sig = contracts.read(out / "signatures/flag.parquet", "signatures_flag")
    assert len(sig) == K * P and not sig["available"].any() and not sig["flagged"].any() and (sig["i"] == -1).all()
    assert m["signatures"]["kinds"] == ["consolidation"] and set(m["signatures"]["not_built"]) == {"collapse", "collusion"}
    assert {"lagcorr/fixture_six_regime.parquet", "bundle_summary/fixture_six_regime.parquet"} <= set(m["artifacts"])
    assert m["artifacts"]["bundle_summary/fixture_six_regime.parquet"]["rows"] == m["configurations"]["admissible"]
    assert "cadence/fixture_six_regime.parquet" in m["artifacts"] and m["cadence"]["scale"] == "r_g"
    assert {"fiber_index.parquet", "steps/fixture_six_regime.parquet", "fibers/fixture_six_regime.parquet"} <= set(m["artifacts"])
    idx = contracts.read(out / "fiber_index.parquet", "fiber_index")
    assert m["fiber"] == {"coordinates": len(idx)} and len(idx) == m["configurations"]["admissible"]
    a = m["artifacts"]
    assert a["fibers/fixture_six_regime.parquet"]["rows"] * len(idx) == a["steps/fixture_six_regime.parquet"]["rows"]
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


def test_failed_fibers_check_writes_its_rows(cfg, tmp_path, monkeypatch):
    import pandas as pd

    from rattractor.stages import fibers

    # A huge floor in the stage's own sigma recomputation: every (issuance, configuration) pair disagrees with steps.
    monkeypatch.setattr(fibers, "series_floor", lambda y_train, cfg: 1e12)
    spec = load_run_spec("fixture_six_regime.yaml")
    with pytest.raises(AcceptanceError, match="sigma in steps disagrees"):
        build(spec, cfg, tmp_path)
    reports = list((tmp_path / "reports").glob("*/fibers.parquet"))
    assert len(reports) == 1
    rows = pd.read_parquet(reports[0])
    n_coords = int(rows["config_id"].nunique())
    assert n_coords == 54 and len(rows) == n_coords * rows["issuance"].nunique()
    assert not list((tmp_path / "builds").glob("*/manifest.json"))


def test_code_version_names_the_exact_tree():
    import re

    from rattractor.manifest import code_version

    v = code_version()
    assert v == "unknown" or re.fullmatch(r"[0-9a-f]{40}(\+dirty:[0-9a-f]{12})?", v)
    assert code_version() == v  # deterministic for one tree


def test_code_version_tells_dirty_states_apart(tmp_path, monkeypatch):
    import os
    import re
    import shutil
    import subprocess

    from rattractor import manifest

    if shutil.which("git") is None:
        pytest.skip("git not available")

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       check=True, capture_output=True)

    (tmp_path / "a.txt").write_text("one\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    monkeypatch.setattr(manifest, "PKG_ROOT", tmp_path)
    head = manifest.code_version()
    assert re.fullmatch(r"[0-9a-f]{40}", head)
    seen = []
    for text in ("two\n", "three\n"):
        (tmp_path / "a.txt").write_text(text)
        seen.append(manifest.code_version())
    (tmp_path / "a.txt").write_text("one\n")
    (tmp_path / "new.txt").write_text("x\n")
    seen.append(manifest.code_version())
    (tmp_path / "target").mkdir()
    os.symlink(tmp_path / "target", tmp_path / "builds")  # an untracked symlink to a directory
    os.symlink(tmp_path / "missing", tmp_path / "dangling")
    seen.append(manifest.code_version())
    assert all(re.fullmatch(re.escape(head) + r"\+dirty:[0-9a-f]{12}", v) for v in seen), seen
    assert len(set(seen)) == len(seen)
    git("status", "--porcelain")  # the real index still works and was not used for the hash
    os.remove(tmp_path / "builds")
    os.remove(tmp_path / "dangling")
    os.remove(tmp_path / "new.txt")
    os.rmdir(tmp_path / "target")
    assert manifest.code_version() == head  # back to the committed tree
