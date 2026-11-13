"""Stage 7, bundle summary: lagcorr -> bundle_summary, one row per (series, configuration).

Each row summarizes one configuration's own lag fibers along the base; nothing is pooled
across configurations. The spec's per-t alignment A(t), a mean resultant length across
configurations, is not built (the archive rule), so there are no per-t rows.

    D(k)            the stored rho at lag k in base order, with nulls and exact zeros removed
                    (they have no sign); gaps are bridged
    flips_lag_m1/p1 sign changes between adjacent entries of D(-1) / D(+1)
    total_rotation  (1/pi) x sum over every k != 0 of sum |theta(t_j+1, k) - theta(t_j, k)| over
                    consecutive non-null theta: the accumulated twist in half twists (rho = -1 is a
                    half twist). Null if some k != 0 has fewer than two non-null theta.
    closure_p1      n/a on an open base (base.closed false). On a closed base: n/a if D(+1) has
                    fewer than two entries, else mobius when the signs of its first and last
                    entries differ and orientable when they agree.
Since sign(first) x sign(last) = (-1)^flips over the same D, closure is Mobius exactly when
flips_lag_p1 is odd (spec invariant); the check recomputes it on every build, open base included.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError


def signs(rho: np.ndarray) -> np.ndarray:
    """D: the signs of a base-ordered rho path, nulls and exact zeros removed."""
    r = np.asarray(rho, dtype=np.float64)
    return np.sign(r[~np.isnan(r) & (r != 0.0)])


def flips(rho: np.ndarray) -> int:
    d = signs(rho)
    return int((d[1:] != d[:-1]).sum()) if d.size > 1 else 0


def closure(rho: np.ndarray) -> str:
    """The closed-base closure of one lag path."""
    d = signs(rho)
    if d.size < 2:
        return "n/a"
    return "mobius" if d[0] != d[-1] else "orientable"


def total_rotation(theta_by_lag: dict[int, np.ndarray]) -> float:
    acc = 0.0
    for k, th in theta_by_lag.items():
        if k == 0:
            continue
        v = np.asarray(th, dtype=np.float64)
        v = v[~np.isnan(v)]
        if v.size < 2:
            return float("nan")
        acc += float(np.abs(np.diff(v)).sum())
    return acc / np.pi


def _paths(lc: pd.DataFrame):
    """{config_id: (rho pivot, theta pivot)} with t ascending and k as columns."""
    for cid, g in lc.groupby("config_id", sort=False, observed=True):
        yield str(cid), g.pivot(index="t", columns="k", values="rho").sort_index(), g.pivot(index="t", columns="k", values="theta").sort_index()


def run_series(sid: str, lc: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = {k: [] for k in ("series_id", "config_id", "flips_lag_m1", "flips_lag_p1", "total_rotation", "closure_p1")}
    for cid, rho, theta in _paths(lc):
        out["series_id"].append(sid)
        out["config_id"].append(cid)
        out["flips_lag_m1"].append(flips(rho[-1].to_numpy()))
        out["flips_lag_p1"].append(flips(rho[1].to_numpy()))
        out["total_rotation"].append(total_rotation({int(k): theta[k].to_numpy() for k in theta.columns}))
        out["closure_p1"].append(closure(rho[1].to_numpy()) if cfg["base.closed"] else "n/a")
    summary = contracts.from_columns(out, "bundle_summary")
    check(sid, summary, lc, cfg)
    return summary


def check(sid: str, summary: pd.DataFrame, lc: pd.DataFrame, cfg: dict) -> None:
    """Stage 7 acceptance: one row per configuration, and closure parity matches flip parity.

    The parity check recomputes the closed-base closure from lagcorr whatever base.closed says,
    so it runs on every build, and compares it with the stored flips_lag_p1.
    """
    problems, frames = [], []
    ids = list(dict.fromkeys(lc["config_id"].astype(str)))
    if sorted(summary["config_id"].astype(str)) != sorted(ids) or summary["config_id"].duplicated().any():
        problems.append(f"{len(summary)} rows for {len(ids)} configurations in lagcorr")
    s = summary.set_index("config_id")
    bad = []
    for cid, rho, theta in _paths(lc):
        if cid not in s.index:
            continue
        row = s.loc[cid]
        closed = closure(rho[1].to_numpy())
        if closed != "n/a" and (closed == "mobius") != (int(row["flips_lag_p1"]) % 2 == 1):
            bad.append((cid, "closure parity does not match flip parity at lag +1"))
        stored = str(row["closure_p1"])
        if cfg["base.closed"] and stored != closed:
            bad.append((cid, f"closure_p1 is {stored}, the lag +1 path gives {closed}"))
        if not cfg["base.closed"] and stored != "n/a":
            bad.append((cid, "closure_p1 must be n/a on an open base"))
        if int(row["flips_lag_m1"]) < 0 or int(row["flips_lag_p1"]) < 0:
            bad.append((cid, "negative flips"))
        short = any(int((~np.isnan(theta[k].to_numpy())).sum()) < 2 for k in theta.columns if k != 0)
        tr = row["total_rotation"]
        if np.isnan(tr) != short or (not np.isnan(tr) and tr < 0):
            bad.append((cid, "total_rotation must be >= 0, and null exactly when a lag has fewer than two thetas"))
    if bad:
        problems.append(f"{len(bad)} configuration rows break a rule")
        frames.append(pd.DataFrame([(sid, c, p) for c, p in bad], columns=["series_id", "config_id", "problem"]))
    if problems:
        raise AcceptanceError("bundle_summary", f"{sid}: " + "; ".join(problems), pd.concat(frames, ignore_index=True) if frames else None)
