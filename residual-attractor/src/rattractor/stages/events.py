"""Stage events: rdiag's s3.events under input contract v2, every configuration's row on its own.

Reads the grid (stage 9) and tails_thresholds. One row per (configuration k, event kind, series i,
month t), for the kinds named in events.kinds:

    residual   event   = |resid[k, i, t]| > u_star[k, i], the row's own threshold from stage tails
                         (events.residual: tails_threshold); never a fixed number of sigmas
               sign    = the sign of resid[k, i, t], at every month
               defined = the row has a threshold

Nothing is tested here; stage coincidence does that.

Source: rdiag s3_cooccurrence/events.py, schemas/30_stage3.yaml (s3.events), params events.*.
Departures from rdiag:
  - k is in every key, and the threshold is the configuration's own (rdiag: the fused row's).
  - Only `residual` is built. rdiag's band_power kind reads s2b.band_power and its persistence kind
    reads s2c.summaries; neither source exists here yet, so events.kinds refuses them.
  - rdiag's coordinate f is the column `kind`, with the config's names (residual, not resid).
  - defined is false for a row without a threshold (stage tails writes a null there instead of
    stopping the run, as rdiag would); such a row has no events.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError
from .tails import dense

KINDS = ("residual", "band_power", "persistence")   # rdiag's three, in its order
RULES = {"residual": ("tails_threshold",)}          # the kinds that are built, with the rules each may follow
WAITS_FOR = {"band_power": "s2b.band_power (the spectral stage)", "persistence": "s2c.summaries (the persistence stage)"}


def thresholds(tailed: dict[str, pd.DataFrame], K: int, N: int) -> np.ndarray:
    """u_star as a (K, N) array, NaN where a row has no threshold."""
    th = tailed["tails_thresholds"]
    seen = np.zeros((K, N), dtype=np.int64)
    np.add.at(seen, (th["k"].to_numpy(), th["i"].to_numpy()), 1)
    if (seen != 1).any():
        raise AcceptanceError("events", f"tails_thresholds must hold one row per (k, i); {int((seen != 1).sum())} rows of the field have none or several")
    u = np.empty((K, N))
    u[th["k"].to_numpy(), th["i"].to_numpy()] = th["u_star"].to_numpy()
    return u


def residual_events(R: np.ndarray, u: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(event, sign, defined), each (K, N, P): |resid| above the row's own threshold."""
    with np.errstate(invalid="ignore"):
        event = np.abs(R) > u[:, :, None]            # a null threshold compares false
    return event, np.sign(R).astype(np.int8), np.broadcast_to(~np.isnan(u)[:, :, None], R.shape)


def run(frames: dict[str, pd.DataFrame], tailed: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    R, months = dense(frames, "events")
    K, N, P = R.shape
    kinds = list(cfg["events.kinds"])
    u = thresholds(tailed, K, N)
    by_kind = {"residual": lambda: residual_events(R, u)}
    event, sign, defined = (np.stack(x, axis=1) for x in zip(*(by_kind[kind]() for kind in kinds)))   # (K, kinds, N, P)
    kk, ff, ii, tt = (x.reshape(-1) for x in np.meshgrid(np.arange(K), np.arange(len(kinds)), np.arange(N), np.arange(P), indexing="ij"))
    built = {"events_flags": contracts.from_columns({
        "k": kk, "kind": np.array(kinds, dtype=object)[ff], "i": ii, "t": months[tt],
        "event": event.reshape(-1), "sign": sign.reshape(-1), "defined": defined.reshape(-1),
    }, "events_flags")}
    check(built, frames, tailed, cfg)
    per_row = event.sum(axis=3)                      # (K, kinds, N)
    info = {
        "rdiag": "s3.events, each configuration's row against its own threshold",
        "kinds": kinds,
        "rules": {kind: cfg[f"events.{kind}"] for kind in kinds},
        "not_built": {kind: f"waits for {src}" for kind, src in WAITS_FOR.items()},
        "rows": {kind: {"units": K * N, "without_a_threshold": int((~defined[:, j, :, 0]).sum()), "events": int(per_row[:, j].sum()),
                        "events_per_unit": {"min": int(per_row[:, j].min()), "median": float(np.median(per_row[:, j])), "max": int(per_row[:, j].max())}}
                 for j, kind in enumerate(kinds)},
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], tailed: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Stage events acceptance: rdiag's s3.events invariants in their v2 form; a failure carries the failing rows."""
    ev = b["events_flags"]
    kinds = list(cfg["events.kinds"])
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    if len(ev) != K * len(kinds) * N * P or set(ev["kind"].unique()) != set(kinds):
        raise AcceptanceError("events", f"events_flags has {len(ev)} rows of kinds {sorted(ev['kind'].unique())}, expected {K * len(kinds) * N * P} of kinds {kinds}")
    th = tailed["tails_thresholds"][["k", "i", "u_star", "n_exceed"]]
    m = ev.merge(frames["grid_resid"], on=["k", "i", "t"], how="left").merge(th, on=["k", "i"], how="left")
    res = (m["kind"] == "residual").to_numpy()
    event, defined = m["event"].to_numpy(), m["defined"].to_numpy()
    with np.errstate(invalid="ignore"):
        above = (m["resid"].abs() > m["u_star"]).to_numpy()
    counted = m.assign(event=event & res).groupby(["k", "i"], sort=False)["event"].transform("sum").to_numpy()
    rules = [
        (event & ~defined, "an event implies defined"),
        (res & (event != above), "a residual event is |resid| above the row's own threshold"),
        (res & (m["sign"].to_numpy() != np.sign(m["resid"].to_numpy())), "sign is the sign of the residual"),
        (res & (defined != m["u_star"].notna().to_numpy()), "defined is false exactly where the row has no threshold"),
        (res & (counted != m["n_exceed"].to_numpy()), "a row has as many residual events as its threshold has exceedances"),
    ]
    problems, failing = [], []
    for mask, rule in rules:
        if mask.any():
            problems.append(f"events_flags: {rule} ({int(mask.sum())} rows)")
            failing.append(ev.loc[mask, ["k", "kind", "i", "t"]].assign(artifact="events_flags", problem=rule))
    if problems:
        raise AcceptanceError("events", "; ".join(problems), pd.concat(failing, ignore_index=True))
