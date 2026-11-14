"""Signatures: rdiag's Stage 3 signatures under input contract v2, inside each configuration. Consolidation only.

A signature is a rule over named metrics, so that "things correlated" does not blur into one
finding. Reads common_mode_month and nothing else; every row comes from one configuration k's own
rows of that table (the archive rule), and no stage picks a configuration.

consolidation, a rising common mode, is about all series of a configuration together (i = -1).
At month t the rule holds when every requirement in signatures.consolidation_requires holds:

    lambda1_above_band   lambda1(k, t) > lambda1_q(k, t), the surrogate band of common_mode
    absorption_rising    absorption_ratio(k, t) > absorption_ratio(k, t - 1)

    available    every metric the rule reads at (k, t) is defined
    held_months  the months in a row, up to and including t, on which the rule held (0 where it does not)
    flagged      held_months >= signatures.persistence_months: a flag is reported only after the rule
                 has held that many months in a row, so one noisy month cannot raise it
    components   the metrics the rule read, by name and value

Writes signatures_flag, one row per (k, t, mode, i) for each kind in signatures.kinds, every month
of the grid. A month where a metric is undefined is not available, is not flagged and ends a run.

Departures from rdiag (s3_cooccurrence/signatures.py, schemas/30_stage3.yaml):
- k is in the key, and common_mode's values are each configuration's own.
- only consolidation is built. collapse needs ensemble spread and member residuals, which have no
  source; collusion needs the Bai-Ng split, which is not built. signatures.kinds lists what runs.
- "absorption_ratio rising" is read as higher than the month before. rdiag's schema says "rising over
  persistence_months"; with the persistence rule that is persistence_months rises in a row.
- components is a JSON object in a string column (rdiag: map<string, float64>), null where undefined.
- held_months is added, so the persistence rule can be checked from the table.
- the requirement rdiag calls lambda1_above_q95 is lambda1_above_band: the band's level is a config key.
- rdiag registers flagged spans in its inference registry. A span has no p-value and no registry is
  written here: a span is a run of flagged months in this table.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import contracts
from . import AcceptanceError

KINDS = ("consolidation",)   # the kinds this stage can build
SYSTEM_WIDE = -1             # rdiag: i = -1 when the mode is about all series together

# A requirement of the consolidation rule: the metrics it reads at (k, t), and the rule on them.
REQUIREMENTS = {
    "lambda1_above_band": (("lambda1", "lambda1_q"), lambda m: m["lambda1"] > m["lambda1_q"]),
    "absorption_rising": (("absorption_ratio", "absorption_ratio_prev"), lambda m: m["absorption_ratio"] > m["absorption_ratio_prev"]),
}


def metrics_read(requires: list[str]) -> list[str]:
    """The metrics the listed requirements read, each once, in the order they are first read."""
    return list(dict.fromkeys(name for req in requires for name in REQUIREMENTS[req][0]))


def held_months(holds: np.ndarray) -> np.ndarray:
    """Along the last axis (months): how many months in a row the rule has held, up to and including each."""
    out = np.zeros(holds.shape, dtype=np.int64)
    for t in range(holds.shape[-1]):
        out[..., t] = np.where(holds[..., t], (out[..., t - 1] if t else 0) + 1, 0)
    return out


def evaluate(metrics: dict[str, np.ndarray], requires: list[str], persistence: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(available, held_months, flagged) from the metrics, each an array whose last axis is months."""
    available = np.logical_and.reduce([~np.isnan(metrics[name]) for name in metrics_read(requires)])
    with np.errstate(invalid="ignore"):
        holds = available & np.logical_and.reduce([REQUIREMENTS[req][1](metrics) for req in requires])
    held = held_months(holds)
    return available, held, held >= persistence


def _month_metrics(month: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """(k values, months, {metric: (K, P)}) from common_mode_month, one configuration per row of each array."""
    m = month.sort_values(["k", "t"])
    ks, ts = np.sort(m["k"].unique()), np.sort(m["t"].unique())
    if len(m) != ks.size * ts.size:
        raise AcceptanceError("signatures", f"common_mode_month has {len(m)} rows, not one per configuration and month ({ks.size} x {ts.size})")
    out = {c: m[c].to_numpy(np.float64).reshape(ks.size, ts.size) for c in ("lambda1", "lambda1_q", "absorption_ratio")}
    out["absorption_ratio_prev"] = np.concatenate([np.full((ks.size, 1), np.nan), out["absorption_ratio"][:, :-1]], axis=1)
    return ks, ts, out


def _components(metrics: dict[str, np.ndarray], names: list[str]) -> list[str]:
    cols = [metrics[n].reshape(-1) for n in names]
    return [json.dumps({n: (None if np.isnan(v) else float(v)) for n, v in zip(names, row)}, sort_keys=True, separators=(",", ":"))
            for row in zip(*cols)]


def run(common: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    ks, ts, metrics = _month_metrics(common["common_mode_month"])
    K, P = ks.size, ts.size
    requires, persistence = list(cfg["signatures.consolidation_requires"]), cfg["signatures.persistence_months"]
    cols = {c: [] for c in ("k", "t", "mode", "i", "components", "available", "held_months", "flagged")}
    for kind in cfg["signatures.kinds"]:   # consolidation: each configuration's months, in order, on its own
        available, held, flagged = evaluate(metrics, requires, persistence)
        cols["k"].append(np.repeat(ks, P))
        cols["t"].append(np.tile(ts, K))
        cols["mode"].append(np.full(K * P, kind, dtype=object))
        cols["i"].append(np.full(K * P, SYSTEM_WIDE))
        cols["components"].append(np.array(_components(metrics, metrics_read(requires)), dtype=object))
        cols["available"].append(available.reshape(-1))
        cols["held_months"].append(held.reshape(-1))
        cols["flagged"].append(flagged.reshape(-1))
    if cols["k"]:
        flag = contracts.from_columns({c: np.concatenate(v) for c, v in cols.items()}, "signatures_flag")
    else:
        flag = contracts.empty_frame("signatures_flag")
    built = {"signatures_flag": flag}
    check(built, common, cfg)
    info = {
        "kinds": list(cfg["signatures.kinds"]),
        "consolidation": {"requires": requires, "persistence_months": persistence,
                          "lambda1_above_band": "lambda1 > lambda1_q",
                          "absorption_rising": "absorption_ratio(t) > absorption_ratio(t - 1)",
                          "scope": "all series of one configuration together, i = -1"},
        "not_built": {"collapse": "needs ensemble spread and member residuals, which have no source",
                      "collusion": "needs the Bai-Ng split, which is not built"},
        "registry": "none written: a flagged span is a run of flagged months in signatures_flag",
    }
    return built, info


def check(b: dict[str, pd.DataFrame], common: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Acceptance: rdiag's signature invariants with k in the key; a failure carries the failing rows.

    Each row's components are compared with what common_mode wrote under the same keys, and the
    flags are recomputed from what the components say the rule read, month after month within
    each configuration: another path than run's.
    """
    f, month = b["signatures_flag"], common["common_mode_month"]
    kinds, requires, persistence = list(cfg["signatures.kinds"]), list(cfg["signatures.consolidation_requires"]), cfg["signatures.persistence_months"]
    names = metrics_read(requires)
    if len(f) != len(month) * len(kinds) or set(f["mode"].astype(str)) != set(kinds):
        raise AcceptanceError("signatures", f"signatures_flag has {len(f)} rows for kinds {sorted(set(f['mode'].astype(str)))}, "
                                            f"expected {len(month)} (one per configuration and month) for each of {kinds}")
    src = month.sort_values(["k", "t"])[["k", "t", "lambda1", "lambda1_q", "absorption_ratio"]]
    src = src.assign(absorption_ratio_prev=src.groupby("k")["absorption_ratio"].shift(1))   # the month before, of the same configuration
    problems, failing = [], []
    for kind in kinds:
        g = f[f["mode"] == kind].merge(src, on=["k", "t"], how="left").sort_values(["k", "t"]).reset_index(drop=True)
        parsed = [json.loads(text) for text in g["components"]]
        named = np.array([list(d) == sorted(names) for d in parsed], dtype=bool)
        read = {n: np.array([np.nan if d.get(n) is None else d[n] for d in parsed], dtype=np.float64) for n in names}
        same = np.logical_and.reduce([(read[n] == g[n].to_numpy()) | (np.isnan(read[n]) & g[n].isna().to_numpy()) for n in names])
        available = np.logical_and.reduce([~np.isnan(read[n]) for n in names])
        with np.errstate(invalid="ignore"):
            holds = available & np.logical_and.reduce([REQUIREMENTS[req][1](read) for req in requires])
        held, run_length, k_before = np.zeros(len(g), dtype=np.int64), 0, None
        for row, (k, h) in enumerate(zip(g["k"].to_numpy(), holds)):
            run_length = (run_length + 1 if k == k_before else 1) if h else 0
            held[row], k_before = run_length, k
        col = lambda c: g[c].to_numpy()
        rules = [
            (~named, "components name every metric the rule read, and no other"),
            (named & ~same, "components carry the values common_mode wrote for the same configuration"),
            (col("i") != SYSTEM_WIDE, "consolidation is about all series together: i = -1"),
            (col("available") != available, "available exactly where every metric the rule read is defined"),
            (col("held_months") != held, "held_months counts the months in a row on which the rule held"),
            (col("flagged") != (col("held_months") >= persistence), "flagged exactly where the rule has held signatures.persistence_months months in a row"),
            (col("flagged") & ~col("available"), "a row that is not available is not flagged"),
        ]
        for mask, rule in rules:
            if mask.any():
                problems.append(f"signatures_flag: {rule} ({int(mask.sum())} rows)")
                failing.append(g.loc[mask, ["k", "t", "mode", "i"]].assign(artifact="signatures_flag", problem=rule))
    if problems:
        raise AcceptanceError("signatures", "; ".join(problems), pd.concat(failing, ignore_index=True))
