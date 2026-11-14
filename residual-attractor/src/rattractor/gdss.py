"""The bridge to the GDSS adapters (MATLAB `src/+gdss`): request out, forecast cube in.

A build whose registry holds estimated families (theta_spec = estimated, methods.precomputed) needs their
forecasts from MATLAB. The build writes a request and stops until the cube is there:

    external/<request_id>/request.json     the estimated configurations, H, request_id
    external/<request_id>/series.parquet   series_id, t, y exactly as ingest produced them
    (MATLAB, sbatch src/gdss_bridge.sbatch residual-attractor/external/<request_id>)
    external/<request_id>/cube/<series>.parquet, fit_status.parquet, done.json

request_id = hash(series values, configurations, H), so a changed series or sweep never reads an old cube.
On read every row is checked: fit_through <= issuance (no parameter saw data after the issuance), issuances
contiguous to N - 1, MATLAB's cut test passed for every configuration. A configuration that cannot give a
forecast from every issuance a series needs (from its first issuance, which must leave W_sigma training
issuances for the growth factor, to N - 1) is not admissible for the run, with the reason kept: the grid
stays dense. Nothing here combines configurations; each one's forecasts stay its own.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import contracts
from .methods import FAMILIES
from .methods.precomputed import y_sha256
from .stages import AcceptanceError

FORECAST_STATUS = ["REFIT", "FILTERED", "REFIT_FAILED", "NO_FIT", "FORECAST_FAILED"]


def estimated(reg: pd.DataFrame) -> pd.DataFrame:
    return reg[reg["theta_spec"] == "estimated"]


def _series_sha(series: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for sid, g in series.groupby("series_id", sort=False, observed=True):
        h.update(str(sid).encode())
        h.update(y_sha256(g["y"].to_numpy()).encode())
    return h.hexdigest()


def _configurations(est: pd.DataFrame) -> list[dict]:
    return [{"config_id": str(c), "method": str(m), "adapter_id": FAMILIES[str(m)].adapter_id, "params": json.loads(p)}
            for c, m, p in zip(est["config_id"], est["method"], est["params"])]


def request(root: Path, series: pd.DataFrame, est: pd.DataFrame, cfg: dict) -> tuple[Path, str]:
    """Write the request (once) and return (its directory, request_id)."""
    confs = _configurations(est)
    H = int(cfg["horizon.H"])
    body = {"series_sha256": _series_sha(series), "configurations": confs, "horizon": H}
    rid = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    d = Path(root) / "external" / rid
    if not (d / "request.json").exists():
        d.mkdir(parents=True, exist_ok=True)
        out = series[["series_id", "t", "y"]].copy()
        out["series_id"] = out["series_id"].astype(str)
        out.to_parquet(d / "series.parquet", index=False)
        (d / "request.json").write_text(json.dumps({"request_id": rid, **body}, indent=2) + "\n")
    return d, rid


def missing(d: Path) -> str:
    rel = d.resolve()
    return (f"the estimated families need the GDSS forecast cube; it is not in {rel}. From the repository root:\n"
            f"    sbatch src/gdss_bridge.sbatch {rel}\n"
            f"then rerun this build.")


def load(d: Path, rid: str, series: pd.DataFrame, est: pd.DataFrame, cfg: dict):
    """(store for methods.precomputed.attach, {config_id: reason not admissible}, cube artifacts, fit status, info)."""
    done = json.loads((d / "done.json").read_text())
    if done.get("request_id") != rid:
        raise AcceptanceError("gdss", f"{d}/done.json is for request {done.get('request_id')}, not {rid}")
    leak = done.get("leakage", [])
    leak = [leak] if isinstance(leak, dict) else leak
    bad_leak = [x["config_id"] for x in leak if not x["identical"]]
    if bad_leak or {x["config_id"] for x in leak} != set(est["config_id"]):
        raise AcceptanceError("gdss", f"MATLAB's cut test failed or is missing for {sorted(set(est['config_id']) - {x['config_id'] for x in leak if x['identical']})}")

    H, W = int(cfg["horizon.H"]), int(cfg["sigma.window"])
    H1 = H + 1
    yc = [f"yhat_{h:02d}" for h in range(1, H1 + 1)]
    sc = [f"sd_{h:02d}" for h in range(1, H1 + 1)]
    store: dict[str, dict[str, dict]] = {}
    drop: dict[str, str] = {}
    cubes: dict[str, pd.DataFrame] = {}
    for sid, g in series.groupby("series_id", sort=False, observed=True):
        sid = str(sid)
        y = g["y"].to_numpy()
        n = y.size
        ts = int(np.argmax((g["split"] == "test").to_numpy()))
        C = pd.read_parquet(d / "cube" / f"{sid}.parquet")
        if not set(est["config_id"]) <= set(C["config_id"]):
            raise AcceptanceError("gdss", f"{sid}: cube lacks configurations {sorted(set(est['config_id']) - set(C['config_id']))}")
        ft, iss = C["fit_through"].to_numpy(), C["issuance"].to_numpy()
        leaked = (ft >= 0) & (ft > iss)
        if leaked.any():
            raise AcceptanceError("gdss", f"{sid}: {int(leaked.sum())} cube rows were estimated on data after their issuance", C[leaked])
        rec = store.setdefault(y_sha256(y), {})
        for cid, c in C.groupby("config_id", sort=False):
            if cid not in set(est["config_id"]):
                continue
            c = c.sort_values("issuance")
            i = c["issuance"].to_numpy()
            if i.size and not (np.array_equal(i, np.arange(i[0], i[0] + i.size)) and i[-1] == n - 1):
                raise AcceptanceError("gdss", f"{sid} {cid}: issuances are not contiguous to N - 1")
            Y, S = np.full((n, H1), np.nan), np.full((n, H1), np.nan)
            Y[i], S[i] = c[yc].to_numpy(np.float64), c[sc].to_numpy(np.float64)
            ok = np.isfinite(Y).all(axis=1)
            i0 = int(np.argmax(ok)) if ok.any() else n
            why = None
            if i0 >= n:
                why = f"{sid}: no forecast at any issuance ({', '.join(sorted(set(c['status'])))})"
            elif not ok[i0:].all():
                why = f"{sid}: no forecast from {int((~ok[i0:]).sum())} issuances after the first"
            elif i0 > ts - H - W:
                why = f"{sid}: first forecast at issuance {i0} leaves fewer than W_sigma = {W} training issuances (needs <= {ts - H - W})"
            if why:
                drop.setdefault(str(cid), why)
            rec[str(cid)] = {"yhat": Y, "sd": S, "i0": min(i0, n - 1)}
        keep = C[C["config_id"].isin(est["config_id"])].sort_values(["config_id", "issuance"])
        cubes[sid] = contracts.from_columns({
            "series_id": keep["series_id"].astype(str).to_numpy(object), "config_id": keep["config_id"].astype(str).to_numpy(object),
            "issuance": keep["issuance"].to_numpy(np.int32), "fit_through": keep["fit_through"].to_numpy(np.int32),
            "status": keep["status"].astype(str).to_numpy(object),
            "sd_m": keep[sc].to_numpy(np.float32),
        }, "gdss_cube")

    F = pd.read_parquet(d / "fit_status.parquet")
    status = contracts.from_columns({
        "series_id": F["series_id"].astype(str).to_numpy(object), "config_id": F["config_id"].astype(str).to_numpy(object),
        "issuance": F["issuance"].to_numpy(np.int32), "fit_through": F["fit_through"].to_numpy(np.int32),
        "status": F["status"].astype(str).to_numpy(object), "reason": F["reason"].astype(str).to_numpy(object),
        "warnings": F["warnings"].astype(str).to_numpy(object), "convergence_status": F["convergence_status"].astype(str).to_numpy(object),
        "log_likelihood": F["log_likelihood"].to_numpy(np.float64), "params_json": F["params_json"].astype(str).to_numpy(object),
        "seconds": F["seconds"].to_numpy(np.float64),
    }, "gdss_fit_status")
    info = {
        "request_id": rid, "request_dir": str(d),
        "configurations": int(len(est)), "not_admissible": drop,
        "policy": "expanding window, parameters re-estimated every refit_every issuances, filtered forward between refits",
        "standardization": "the same as the fixed families: e1 over the configuration's own trailing sigma; the model's own forecast sd is gdss/cube sd_m",
        "matlab": {k: done.get(k) for k in ("matlab_version", "wall_seconds", "workers", "refits", "refits_failed",
                                            "refits_with_warnings", "issuances_without_forecast", "created")},
    }
    return store, drop, cubes, status, info
