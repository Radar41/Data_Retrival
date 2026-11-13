"""Stage 9, grid: the residual archive as rdiag's input field, R[k, i, t] over the holdout months.

Reads series, calendar, registry and states (steps only to check overlap); writes the tables
rdiag's loader (Database.open_build) takes, under its reworked input contract v2, in which there
is no fused configuration: grid_resid (in_resid), grid_config (in_config), grid_attrs
(in_field_attrs), grid_series (dim_series), grid_month (dim_month), grid_provenance
(in_provenance) and grid_names (meta_names).

    resid(k, i, t) = e1_k(i, t) / sigma_k(i, t - 1)
configuration k's own one-step residual for month t over its own sigma at t - 1, the month the
forecast was issued: stage 4's sigma, the sd of that configuration's one-step residuals over the
W_sigma steps ending there, floored. Real time and per configuration; nothing is pooled across
configurations or series. Where t - 1 is a stage 4 origin, resid equals that forward step's e / sigma.

Holdout: the months every series covers from its test split on, from the latest first test month
to the earliest last month; every series must be monthly and cover all of them (rdiag's field is dense).
Provenance, one row per (k, i, t): vintage_id = "<source>:<as_of>", data_cutoff = month t - 1,
release_date = calendar.first_release of month t, model_run_id = the build_id.
rdiag's own minimums (K >= 2, N >= 3, P >= 60) are reported in the manifest, not enforced here.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError
from .forecast import rolling_sigma, series_floor

RTOL = 1e-12  # resid vs the archive's forward one-step e / sigma


def _contiguous_month_starts(ts: pd.Series) -> bool:
    """True when every timestamp is a month start at midnight and they run month after month without gaps."""
    ts = pd.Series(pd.to_datetime(ts)).sort_values()
    starts = (ts.dt.day == 1).all() and (ts == ts.dt.normalize()).all()
    ordinal = (ts.dt.year * 12 + ts.dt.month).to_numpy()
    return bool(starts and (np.diff(ordinal) == 1).all())


def standardization_id(cfg: dict) -> str:
    return (f"rattractor:e1_t/sigma_t-1:window={cfg['sigma.window']}:ddof={cfg['sigma.ddof']}"
            f":floor_factor={cfg['sigma.floor_factor']}")


def holdout(series: pd.DataFrame, calendar: pd.DataFrame) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    """(holdout months, {series_id: the t of each holdout month})."""
    first, last, months_of = [], [], {}
    for sid, cal in calendar.groupby("series_id", sort=False, observed=True):
        sid = str(sid)
        cal = cal.sort_values("t")
        per = pd.to_datetime(cal["period"].astype(str)).astype("datetime64[ns]")
        if not _contiguous_month_starts(per):
            raise AcceptanceError("grid", f"{sid}: not a contiguous monthly series; rdiag's field is monthly")
        s = series[series["series_id"] == sid].sort_values("t")
        test = (s["split"] == "test").to_numpy()
        first.append(per.to_numpy()[np.argmax(test)])
        last.append(per.to_numpy()[-1])
        months_of[sid] = pd.Series(cal["t"].to_numpy(), index=per.to_numpy())
    start, end = max(first), min(last)
    if start > end:
        raise AcceptanceError("grid", f"the series share no holdout month (latest test start {start}, earliest end {end})")
    months = pd.date_range(start, end, freq="MS").astype("datetime64[ns]")
    t_of = {}
    for sid, m in months_of.items():
        missing = months.difference(m.index)
        if len(missing):
            raise AcceptanceError("grid", f"{sid}: no value for holdout months {[str(x.date()) for x in missing[:5]]}")
        t_of[sid] = m.loc[months].to_numpy().astype(np.int64)
    return months, t_of


def series_rows(sid: str, i: int, g: pd.DataFrame, states: pd.DataFrame, coords: list[str], t_idx: np.ndarray,
                cfg: dict, steps: pd.DataFrame | None = None) -> np.ndarray:
    """resid as a (K, P) array for one series; checked against the archive's forward one-step rows when given."""
    y = g.sort_values("t")["y"].to_numpy()
    ts = int(np.argmax((g.sort_values("t")["split"] == "test").to_numpy()))
    floor = series_floor(y[:ts], cfg)
    st = states[states["series_id"] == sid]
    E = st.pivot(index="t", columns="config_id", values="e1").sort_index()
    if not np.array_equal(E.index.to_numpy(), np.arange(y.size)) or set(coords) - set(E.columns):
        raise AcceptanceError("grid", f"{sid}: states do not cover every configuration at every t")
    Z = np.empty((len(coords), t_idx.size))
    for kk, cid in enumerate(coords):
        e1 = E[cid].to_numpy(np.float64)
        sig = rolling_sigma(e1, cfg, floor)
        z = e1[t_idx] / sig[t_idx - 1]
        if not np.isfinite(z).all():
            bad = t_idx[~np.isfinite(z)]
            raise AcceptanceError("grid", f"{sid}: configuration {cid} has no finite standardized residual at t = {bad[:5].tolist()}")
        Z[kk] = z
    if steps is not None:
        fw = steps[(steps["ladder"] == "forward") & (steps["h"] == 1)]
        fw = fw[fw["t_target"].isin(t_idx)]
        pos = {int(t): j for j, t in enumerate(t_idx)}
        kpos = {c: kk for kk, c in enumerate(coords)}
        want = (fw["e"].to_numpy() / fw["sigma"].to_numpy())
        got = Z[[kpos[c] for c in fw["config_id"]], [pos[int(t)] for t in fw["t_target"]]]
        bad = ~np.isclose(got, want, rtol=RTOL, atol=0.0)
        if bad.any():
            rows = fw.loc[bad, ["series_id", "config_id", "origin", "t_target"]].assign(resid=got[bad], steps_e_over_sigma=want[bad])
            raise AcceptanceError("grid", f"{sid}: {int(bad.sum())} residuals disagree with the archive's forward one-step e / sigma", rows)
    return Z


def assemble(Z_by_series: list[np.ndarray], series_ids: list[str], registry: pd.DataFrame, coords: list[str], months: pd.DatetimeIndex,
             t_of: dict[str, np.ndarray], calendar: pd.DataFrame, cfg: dict, vintage_id: str, model_run_id: str) -> dict[str, pd.DataFrame]:
    """coords is the configuration order the rows of every Z were built in; k labels follow it, so they cannot drift."""
    by_id = registry.set_index("config_id")
    if len(set(coords)) != len(coords) or not set(coords) <= set(by_id.index[by_id["admissible"]]):
        raise AcceptanceError("grid", "coords must be distinct admissible configurations")
    adm = by_id.loc[coords].reset_index()
    K, N, P = len(adm), len(series_ids), months.size
    Z = np.stack(Z_by_series, axis=1)  # (K, N, P)
    kk, ii, pp = np.meshgrid(np.arange(K), np.arange(N), np.arange(P), indexing="ij")
    kk, ii, pp = kk.reshape(-1), ii.reshape(-1), pp.reshape(-1)
    t = months.to_numpy()[pp]
    rel = np.empty((N, P), dtype="datetime64[ns]")
    for n, sid in enumerate(series_ids):
        cal = calendar[calendar["series_id"] == sid].set_index("t")["first_release"]
        fr = cal.reindex(t_of[sid])
        if fr.isna().any():
            raise AcceptanceError("grid", f"{sid}: no first release recorded for holdout months at t = {t_of[sid][fr.isna().to_numpy()][:5].tolist()}")
        rel[n] = pd.to_datetime(fr.astype(str)).astype("datetime64[ns]").to_numpy()
    cutoff = (months - pd.offsets.MonthBegin(1)).astype("datetime64[ns]").to_numpy()
    frames = {
        "grid_resid": contracts.from_columns({"k": kk, "i": ii, "t": t, "resid": Z.reshape(-1)}, "grid_resid"),
        "grid_config": contracts.from_columns({
            "k": np.arange(K), "core_spec_id": adm["core_spec_id"].to_numpy(object),
            "exog_set": [[] if e == "" else [str(e)] for e in adm["exog_set_id"]],
        }, "grid_config"),
        "grid_attrs": contracts.from_columns({"standardization_id": [standardization_id(cfg)], "horizon": [1]}, "grid_attrs"),
        "grid_series": contracts.from_columns({"i": np.arange(N)}, "grid_series"),
        "grid_month": contracts.from_columns({"t": months.to_numpy()}, "grid_month"),
        "grid_provenance": contracts.from_columns({
            "k": kk, "i": ii, "t": t, "vintage_id": np.full(kk.size, vintage_id, dtype=object),
            "data_cutoff": cutoff[pp], "release_date": rel[ii, pp], "model_run_id": np.full(kk.size, model_run_id, dtype=object),
        }, "grid_provenance"),
        "grid_names": contracts.from_columns({
            "axis": ["k"] * K + ["i"] * N,
            "idx": np.concatenate([np.arange(K), np.arange(N)]),
            "name": [f"{c} {m} {json.dumps(json.loads(p), separators=(',', ':'))}" for c, m, p in zip(adm["config_id"], adm["method"], adm["params"])] + list(series_ids),
        }, "grid_names"),
    }
    check(frames)
    return frames


def minimums(frames: dict[str, pd.DataFrame]) -> dict:
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    return {"K": K, "N": N, "P": P, "K>=2": K >= 2, "N>=3": N >= 3, "P>=60": P >= 60}


def check(frames: dict[str, pd.DataFrame]) -> None:
    """The input checks rdiag's loader runs, other than its fused ones and its minimums."""
    r, prov, months = frames["grid_resid"], frames["grid_provenance"], frames["grid_month"]["t"]
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(months)
    problems = []
    if len(r) != K * N * P:
        problems.append(f"field not dense: {len(r)} rows, K x N x P = {K * N * P}")
    if not _contiguous_month_starts(months):
        problems.append("holdout months are not contiguous month starts")
    if not np.isfinite(r["resid"].to_numpy()).all():
        problems.append("non-finite resid")
    if len(prov) != len(r) or not (prov["data_cutoff"] < prov["t"]).all():
        problems.append("provenance must hold one row per residual with data_cutoff before t")
    if not set(r["k"]) <= set(frames["grid_config"]["k"]) or not set(r["i"]) <= set(frames["grid_series"]["i"]) or not set(r["t"]) <= set(months):
        problems.append("resid keys outside the config, series or month tables")
    if len(frames["grid_attrs"]) != 1:
        problems.append("one field-attributes row per build")
    if problems:
        raise AcceptanceError("grid", "; ".join(problems))
