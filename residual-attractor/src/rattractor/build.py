"""One build: run spec + config -> builds/<build_id>/ with every artifact and manifest.json.

Stages run in order (ingest, register, fit, then forecast, fibers, cadence, lagcorr and bundle summary per series,
then the grid: rdiag's input field over every series, and compare: rdiag's Stage 1 on it)
and each one's acceptance checks pass before the next starts. A failed check writes its failing rows to reports/<build_id>/<stage>.parquet
and stops the build; the manifest is written last, only when everything passed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import re
import shutil
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

from . import PKG_ROOT, contracts, fixtures
from .config import config_sha256
from .manifest import build_id as make_build_id, code_version, file_sha256
from .runspec import run_spec_sha256
from .stages import AcceptanceError, bundle, cadence, compare, fibers, fit, forecast, grid, ingest, lagcorr, register


def _safe(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError(f"series_id {name!r} is not safe as a file name")
    return name


def _frame_sha256(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes()).hexdigest()


def _inputs(spec: dict, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    """(series, calendar, {input: sha256}, provenance) for either source."""
    if spec["source"] == "fixture":
        series, bounds = fixtures.six_regime(cfg)
        n = len(series)
        start = pd.Period("2000-01", freq="M")
        calendar = contracts.from_columns({
            "series_id": series["series_id"].to_numpy(object), "t": series["t"].to_numpy(),
            "period": [(start + i).start_time.date().isoformat() for i in range(n)],
            "imputed": np.zeros(n, dtype=bool),
            "first_release": [(start + i + 1).start_time.date().isoformat() for i in range(n)],  # synthetic: one month on
        }, "calendar")
        prov = {"source": "fixture", "regimes": [list(b) for b in bounds], "calendar": "synthetic monthly from 2000-01"}
        return series, calendar, {"fixture_six_regime": _frame_sha256(series)}, prov
    cat = spec["catalog"]
    raw, freq, releases = ingest.extract(cat["dsn"], cat["series"], cat["as_of"])
    series, calendar = ingest.prepare(raw, freq, cat, releases)
    prov = {
        "source": "catalog", "dsn": cat["dsn"], "as_of": cat["as_of"],
        "vintage_rule": "realtime_start <= as_of <= realtime_end",
        "raw_rows": {k: int(v) for k, v in raw.groupby("series_id").size().items()},
        "native_frequency": freq, "raw_sha256": ingest.raw_sha256(raw),
        "imputed_periods": {str(k): g.loc[g["imputed"], "period"].tolist()
                            for k, g in calendar.groupby("series_id", observed=True) if g["imputed"].any()},
    }
    return series, calendar, {"catalog_extract": prov["raw_sha256"]}, prov


def _versions() -> dict:
    out = {"python": platform.python_version()}
    for lib in ("numpy", "scipy", "pandas", "pyarrow", "pyyaml", "psycopg"):
        try:
            out[lib] = metadata.version(lib)
        except metadata.PackageNotFoundError:
            pass
    return out


def build(spec: dict, cfg: dict, root: Path | None = None) -> Path:
    root = Path(root) if root else PKG_ROOT
    series, calendar, data_hashes, prov = _inputs(spec, cfg)
    commit = code_version()
    cfg_hash = hashlib.sha256((config_sha256(cfg) + run_spec_sha256(spec)).encode()).hexdigest()
    bid = make_build_id(cfg_hash, data_hashes, commit)
    out, reports = root / "builds" / bid, root / "reports" / bid
    if out.exists():
        shutil.rmtree(out)  # same build_id = same inputs; rebuild from scratch
    artifacts: dict[str, dict] = {}

    def write(df: pd.DataFrame, artifact: str, rel: str) -> None:
        p = contracts.write(df, artifact, out / rel)
        artifacts[rel] = {"artifact": artifact, "rows": len(df), "sha256": file_sha256(p)}

    stage = "ingest"
    try:
        ingest.check(series)
        write(series, "series", "series.parquet")
        write(calendar, "calendar", "calendar.parquet")
        stage = "register"
        reg = register.run(cfg)
        write(reg, "registry", "registry.parquet")
        stage = "fit"
        states, cache = fit.run(series, reg, cfg)
        write(states, "states", "states.parquet")
        stage = "fibers"
        index = fibers.fiber_index(reg, cfg)
        write(index, "fiber_index", "fiber_index.parquet")
        stage = "grid"
        months, t_of = grid.holdout(series, calendar)
        series_ids, Z, raw = [], [], []
        n_origins = {}
        for sid, g in series.groupby("series_id", sort=False, observed=True):
            sid = str(sid)
            stage = "forecast"
            steps = forecast.run_series(sid, g, reg, states, cfg, cache[sid])
            write(steps, "steps", f"steps/{_safe(sid)}.parquet")
            n_origins[sid] = int(steps["origin"].nunique())
            stage = "fibers"
            write(fibers.run_series(sid, g, states, steps, cfg, index), "fibers", f"fibers/{_safe(sid)}.parquet")
            stage = "cadence"
            write(cadence.run_series(sid, g, steps, cfg), "cadence", f"cadence/{_safe(sid)}.parquet")
            stage = "grid"
            series_ids.append(sid)
            Z.append(grid.series_rows(sid, len(series_ids) - 1, g, states, list(index["config_id"]), t_of[sid], cfg, steps))
            raw.append(grid.raw_errors(sid, states, list(index["config_id"]), t_of[sid]))
            del steps
            stage = "lagcorr"
            lc = lagcorr.run_series(sid, g, states, reg, cfg)
            write(lc, "lagcorr", f"lagcorr/{_safe(sid)}.parquet")
            stage = "bundle_summary"
            write(bundle.run_series(sid, lc, cfg), "bundle_summary", f"bundle_summary/{_safe(sid)}.parquet")
            del lc
        stage = "grid"
        vintage = f"fred:{spec['catalog']['as_of']}" if spec["source"] == "catalog" else "fixture:synthetic"
        frames = grid.assemble(Z, series_ids, reg, list(index["config_id"]), months, t_of, calendar, cfg, vintage, bid)
        for name, frame in frames.items():
            write(frame, name, f"grid/{name.removeprefix('grid_')}.parquet")
        grid_info = {
            "contract": "rdiag input v2: no fused configuration (no k_fused, is_fused, member_ks or residual_metrics)",
            "holdout": [str(months[0].date()), str(months[-1].date())],
            "standardization_id": grid.standardization_id(cfg), "vintage_id": vintage,
            "rdiag_minimums": grid.minimums(frames),
            "files": {name: f"grid/{name.removeprefix('grid_')}.parquet" for name in frames},
        }
        stage = "compare"
        compared, compare_info = compare.run(frames, reg, index, cfg, np.stack(raw, axis=1))
        for name, frame in compared.items():
            write(frame, name, f"compare/{name.removeprefix('compare_')}.parquet")
        # Track A, who leads by phase: each stage runs on every configuration's own rows of the grid.
        from .stages import coherence, spectral, wavelet

        stage = "wavelet"
        wav, wavelet_info = wavelet.run(frames, cfg)
        for name, frame in wav.items():
            write(frame, name, f"wavelet/{name.removeprefix('wavelet_')}.parquet")
        stage = "spectral"
        spec_frames, spectral_info = spectral.run(frames, wav, cfg)
        for name, frame in spec_frames.items():
            write(frame, name, f"spectral/{name.removeprefix('spectral_')}.parquet")
        stage = "coherence"
        coh, coherence_info = coherence.run(frames, wav, spec_frames, cfg)
        for name, frame in coh.items():
            write(frame, name, f"coherence/{name.removeprefix('coherence_')}.parquet")
        track_a = {"wavelet": wavelet_info, "spectral": spectral_info, "coherence": coherence_info}
    except AcceptanceError as err:
        if err.rows is not None:
            reports.mkdir(parents=True, exist_ok=True)
            err.rows.to_parquet(reports / f"{stage}.parquet")
        raise

    manifest = {
        "build_id": bid,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_commit": commit,
        "config_sha256": config_sha256(cfg),
        "run_spec_sha256": run_spec_sha256(spec),
        "run_spec": spec,
        "config": cfg,
        "seed": cfg["seed"],
        "inputs": data_hashes,
        "provenance": prov,
        "split_boundary": ingest.split_boundary(series),
        "origins_per_series": n_origins,
        "configurations": {"registered": len(reg), "admissible": int(reg["admissible"].sum())},
        "fiber": {"coordinates": len(index)},
        "cadence": {"scale": cadence.SCALE_COLUMN[cfg["sigma.failure_scale"]], "labels": cfg["cadence.labels"]},
        "bundle_summary": {"alignment_A_t": "not built: it averages across configurations (archive rule)", "base_closed": cfg["base.closed"]},
        "grid": grid_info,
        "compare": compare_info,
        **track_a,
        "stages_passed": ["ingest", "register", "fit", "forecast", "fibers", "cadence", "lagcorr", "bundle_summary", "grid", "compare", *track_a],
        "artifacts": artifacts,
        "libraries": _versions(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return out
