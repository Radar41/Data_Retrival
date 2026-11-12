"""Stage 5, cadence: steps -> cadence, one row per (series, configuration, eligible origin).

Each row reads one configuration's own forward ladder from one origin; nothing is pooled
across configurations, origins or series (the archive rule). Pooled readouts, such as the
2-sigma failure rate, are views computed from these rows, not artifacts.

On the failure scale chosen by sigma.failure_scale (r, r_h or r_g; decision 1 picks r_g):
    h_k  = min{h : scale(c, o, h) >= k} for the four thresholds k (null = not reached within H)
    gaps = successive differences of the non-null crossings
label = the first rule in cadence.labels that applies (decision 4: the spec's nine, in its order):
    Holds         no crossing of the fail level within H
    Immediate     the fail level is crossed at h = 1
    Oscillating   after first reaching a level k in cadence.oscillation_levels, the scale later
                  falls below k - cadence.oscillation_drop
    Jump          a zero gap
    Insufficient  fewer than two gaps
    Steady        max gap <= steady_ratio x min gap, or max gap - min gap <= steady_abs
    Accelerating  every gap <= the one before, last < first
    Decelerating  every gap >= the one before, last > first
    Mixed         otherwise
Rules that read gaps need at least two gaps (Jump at least one); with the spec's order,
Insufficient has already taken every row with fewer.
Only eligible origins are scored: o from H + W_sigma to N - 1 - H, so every ladder has its
full follow-up.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError

CADENCE_RULES = ("Holds", "Immediate", "Oscillating", "Jump", "Insufficient", "Steady", "Accelerating", "Decelerating", "Mixed")
SCALE_COLUMN = {"one_step": "r", "model_h": "r_h", "training_growth": "r_g"}


def ladder(r: np.ndarray, cfg: dict) -> tuple[list[int | None], list[int], str]:
    """(crossings h1..h4, gaps, label) for one forward ladder's failure-scale path r[0..H-1] (step h = index + 1)."""
    levels = cfg["thresholds"]
    hk: list[int | None] = []
    for k in levels:
        hit = np.flatnonzero(r >= k)
        hk.append(int(hit[0]) + 1 if hit.size else None)
    reached = [h for h in hk if h is not None]
    gaps = [b - a for a, b in zip(reached, reached[1:])]
    h_fail = hk[[i for i, k in enumerate(levels) if k == cfg["cadence.fail_level"]][0]]
    by_level = dict(zip(levels, hk))
    drop = cfg["cadence.oscillation_drop"]

    def applies(rule: str) -> bool:
        if rule == "Holds":
            return h_fail is None
        if rule == "Immediate":
            return h_fail == 1
        if rule == "Oscillating":
            return any(by_level[k] is not None and bool((r[by_level[k]:] < k - drop).any())
                       for k in cfg["cadence.oscillation_levels"])
        if rule == "Jump":
            return any(g == 0 for g in gaps)
        if rule == "Insufficient":
            return len(gaps) < 2
        if len(gaps) < 2:
            return rule == "Mixed"
        if rule == "Steady":
            return max(gaps) <= cfg["cadence.steady_ratio"] * min(gaps) or max(gaps) - min(gaps) <= cfg["cadence.steady_abs"]
        if rule == "Accelerating":
            return all(b <= a for a, b in zip(gaps, gaps[1:])) and gaps[-1] < gaps[0]
        if rule == "Decelerating":
            return all(b >= a for a, b in zip(gaps, gaps[1:])) and gaps[-1] > gaps[0]
        if rule == "Mixed":
            return True
        raise AcceptanceError("cadence", f"unknown cadence rule {rule!r}")

    for rule in cfg["cadence.labels"]:
        if applies(rule):
            return hk, gaps, rule
    raise AcceptanceError("cadence", "no cadence rule applied; Mixed must be last")  # unreachable after config validation


def eligible_origins(n: int, origins: np.ndarray, cfg: dict) -> np.ndarray:
    H = cfg["horizon.H"]
    o = np.unique(origins)
    return o[(o >= H + cfg["sigma.window"]) & (o <= n - 1 - H)]


def run_series(sid: str, g: pd.DataFrame, steps: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    n, H = len(g), cfg["horizon.H"]
    col = SCALE_COLUMN[cfg["sigma.failure_scale"]]
    elig = eligible_origins(n, steps["origin"].to_numpy(), cfg)
    if elig.size == 0:
        raise AcceptanceError("cadence", f"{sid}: no eligible origin (o <= N - 1 - H = {n - 1 - H})")
    fw = steps[(steps["series_id"] == sid) & (steps["ladder"] == "forward") & steps["origin"].isin(elig)]
    out = {k: [] for k in ("series_id", "config_id", "origin", "h1", "h2", "h3", "h4", "gaps", "label")}
    for cid, rows in fw.groupby("config_id", sort=False, observed=True):
        piv = rows.pivot(index="origin", columns="h", values=col).reindex(index=elig, columns=range(1, H + 1))
        if piv.isna().to_numpy().any():
            miss = piv.isna().stack()
            miss = miss[miss].reset_index()[["origin", "h"]]
            raise AcceptanceError("cadence", f"{sid}: configuration {cid} lacks {len(miss)} forward steps at eligible origins",
                                  miss.assign(series_id=sid, config_id=str(cid))[["series_id", "config_id", "origin", "h"]])
        R = piv.to_numpy(np.float64)
        for o, r in zip(piv.index.to_numpy(), R):
            hk, gaps, lab = ladder(r, cfg)
            out["series_id"].append(sid)
            out["config_id"].append(str(cid))
            out["origin"].append(int(o))
            for name, h in zip(("h1", "h2", "h3", "h4"), hk):
                out[name].append(pd.NA if h is None else h)
            out["gaps"].append(gaps)
            out["label"].append(lab)
    cad = contracts.from_columns(out, "cadence")
    check(sid, cad, elig, steps["config_id"].unique())
    return cad


def check(sid: str, cad: pd.DataFrame, elig: np.ndarray, config_ids) -> None:
    """Spec acceptance: h1 <= h2 <= h3 <= h4 wherever defined; every row has a label; one row per ladder.

    A failure carries the failing rows (with the rule each broke), or the missing and extra (config_id, origin) pairs.
    """
    problems, frames = [], []
    H = cad[["h1", "h2", "h3", "h4"]].astype("float64").to_numpy()
    for a, b in ((0, 1), (1, 2), (2, 3)):
        bad = ~np.isnan(H[:, b]) & (np.isnan(H[:, a]) | (H[:, b] < H[:, a]))
        if bad.any():
            rule = f"h{a + 1} <= h{b + 1}"
            problems.append(f"{rule} fails on {int(bad.sum())} rows")
            frames.append(cad.loc[bad, ["series_id", "config_id", "origin"]].assign(problem=rule))
    unlabelled = cad["label"].isna().to_numpy()
    if unlabelled.any():
        problems.append(f"{int(unlabelled.sum())} rows without a label")
        frames.append(cad.loc[unlabelled, ["series_id", "config_id", "origin"]].assign(problem="no label"))
    want = pd.MultiIndex.from_product([[str(c) for c in config_ids], [int(o) for o in elig]], names=["config_id", "origin"])
    have = pd.MultiIndex.from_frame(cad[["config_id", "origin"]].astype({"config_id": object, "origin": int}))
    missing, extra = want.difference(have), have.difference(want)
    if len(missing) or len(extra) or len(cad) != len(want):
        problems.append(f"{len(cad)} rows, expected {len(want)} (one per configuration and eligible origin)")
        for idx, what in ((missing, "missing ladder"), (extra, "extra ladder")):
            if len(idx):
                frames.append(idx.to_frame(index=False).assign(series_id=sid, problem=what)[["series_id", "config_id", "origin", "problem"]])
    if problems:
        raise AcceptanceError("cadence", f"{sid}: " + "; ".join(problems), pd.concat(frames, ignore_index=True) if frames else None)
