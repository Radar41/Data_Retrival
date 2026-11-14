"""Stage adjacency (track A4): rdiag's s3.adjacency under input contract v2, one edge decision per (k, pair, scope).

Reads coherence_scope and the wavelet stage's scales; the cells are not read again. Every row is one row of
coherence_scope: a pair i_a < i_b of configuration k and a scope (all scales, band_a = band_b = -1, or an
overlap of the two rows' own bands). No value is computed from two configurations and none is preferred.

    weight      n_significant / n_cells: the share of the scope's in-cone cells that are significant
    expected    1 - coherence.quantile: the share rdiag expects of an unrelated pair
    n_eff       max(1, n_cells^2 / sum over the scope's in-cone cells of the cell's footprint). A cell at
                scale j stands for a block one smoothing footprint large: sqrt(2 pi) s_j months (the equivalent
                width of the Gaussian with sd s_j) by min(width x voices, scales in the scope) scales (the
                boxcar, at least one scale and no wider than the scope). n_eff is the Kish count of such
                blocks; one scale alone gives n_a / (sqrt(2 pi) s), n_a its in-cone months.
    p_value     P(X >= weight x n_eff) for X ~ Binomial(n_eff, expected), continued to real n_eff by the
                regularized incomplete beta function I_expected(x, n_eff - x + 1); 1 at weight 0. Raw.
    family      "all" for the all-scales rows, "band" for the band overlaps. The decision is taken inside one
                configuration: a row's family is the rows of the same k with the same label.
    family_size the tests in that family
    q_value     Benjamini-Yekutieli within the family (common.fdr)
    edge        q_value <= inference.q

adjacency.per_band: false writes the all-scales rows only. A scope without an in-cone cell has no test:
weight, n_eff, p_value and q_value are null and edge is false.

What the rule does on unrelated rows (independent AR(1) rows, 14 series, P = 98, 100 configurations at each of
phi = 0, 0.5, 0.9): coherence gives such a pair a weight of 0.077 on average, not the expected 0.05 (see the
coherence stage). The all-scales p-value is <= 0.05 for 7.2% of unrelated pairs. With no related pair at all a
discovery is a false one, so FDR control at q = 0.10 bounds the share of configurations with any edge in a family
by 0.10: measured 6.7% for the all-scales family, 5.7% for the band family, 11.3% for either.

rdiag sources: s3_cooccurrence/adjacency.py, inference/fdr.py, schemas/30_stage3.yaml (s3.adjacency),
params adjacency, inference.cooccurrence_family_method and inference.q.
Departures and choices where rdiag is silent:
  - k joins the key, and the false-discovery decision is taken within one configuration (the archive rule).
    A configuration's edges therefore depend on which series it holds: the family grows with them. weight,
    expected, n_eff and p_value do not.
  - rdiag names "effective n reduced for the smoothing footprint" and gives no formula; the Kish count above
    is this stage's. Multiplying a count of scales by a mean count of months instead put an edge in half of
    all pure-noise configurations.
  - rdiag's band_scope label is the pair (band_a, band_b), as in coherence_scope.
  - the scope family is read as two families per configuration: a band belongs to one row of one pair, so
    band overlaps cannot be grouped by label across pairs.
  - no registry is written; the raw p-value and the q-value are stored with their keys.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import special

from .. import contracts
from ..common import fdr, wavelets
from . import AcceptanceError
from .coherence import ALL

TINY = np.finfo(np.float64).tiny
FAMILIES = ("all", "band")
KEY = ["k", "i_a", "i_b", "band_a", "band_b"]
RTOL = 1e-9


def effective_n(j_lo: np.ndarray, j_hi: np.ndarray, scales: np.ndarray, n_a: np.ndarray, cfg: dict) -> np.ndarray:
    """The Kish count of smoothing footprints among the in-cone cells of scales j_lo..j_hi; null without a cell."""
    width = cfg["coherence.scale_smoothing_width"] * cfg["wavelet.voices_per_octave"]
    cum_n = np.concatenate([[0.0], np.cumsum(n_a)])
    cum_ns = np.concatenate([[0.0], np.cumsum(n_a * scales)])
    n, ns = cum_n[j_hi + 1] - cum_n[j_lo], cum_ns[j_hi + 1] - cum_ns[j_lo]
    across = np.minimum(max(width, 1.0), j_hi - j_lo + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        blocks = n * n / (np.sqrt(2.0 * np.pi) * across * ns)
    return np.where(n > 0, np.maximum(blocks, 1.0), np.nan)


def exceedance(weight: np.ndarray, n_eff: np.ndarray, expected: float) -> np.ndarray:
    """P(X >= weight x n_eff), X ~ Binomial(n_eff, expected), for real n_eff; 1 at weight 0; null where weight is."""
    x = weight * n_eff
    p = np.where(np.isnan(x), np.nan, 1.0)
    pos = x > 0
    p[pos] = np.maximum(special.betainc(x[pos], n_eff[pos] - x[pos] + 1.0, expected), TINY)
    return p


def edges(sp: pd.DataFrame, scales: np.ndarray, n_a: np.ndarray, cfg: dict) -> dict[str, np.ndarray]:
    """The columns of adjacency_edges for the rows of coherence_scope given, in their order."""
    k, band_a = sp["k"].to_numpy(np.int64), sp["band_a"].to_numpy(np.int64)
    cells, sig = sp["n_cells"].to_numpy(np.float64), sp["n_significant"].to_numpy(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        weight = np.where(cells > 0, sig / cells, np.nan)
    expected = 1.0 - cfg["coherence.quantile"]
    n_eff = effective_n(sp["j_lo"].to_numpy(np.int64), sp["j_hi"].to_numpy(np.int64), scales, n_a, cfg)
    p = exceedance(weight, n_eff, expected)
    label = (band_a != ALL).astype(np.int64)
    q, size = np.full(len(sp), np.nan), np.zeros(len(sp), dtype=np.int64)
    group = 2 * k + label                       # one family per configuration and label; nothing crosses k
    for g in np.unique(group):
        m = group == g
        q[m] = fdr.benjamini_yekutieli(p[m])
        size[m] = int((~np.isnan(p[m])).sum())
    with np.errstate(invalid="ignore"):
        edge = q <= cfg["inference.q"]
    return {**{c: sp[c].to_numpy() for c in KEY}, "weight": weight, "expected": np.full(len(sp), expected), "n_eff": n_eff, "p_value": p,
            "family": np.asarray(FAMILIES, dtype=object)[label], "family_size": size, "q_value": q, "edge": edge}


def _inputs(frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], coh: dict[str, pd.DataFrame], cfg: dict):
    P = len(frames["grid_month"])
    scales = wav["wavelet_scale"].sort_values("j")["scale"].to_numpy()
    n_a = wavelets.coi_mask(scales, P).sum(axis=1)
    sp = coh["coherence_scope"]
    if not cfg["adjacency.per_band"]:
        sp = sp[sp["band_a"] == ALL]
    return sp.sort_values(KEY).reset_index(drop=True), scales, n_a


def run(frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], coh: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    sp, scales, n_a = _inputs(frames, wav, coh, cfg)
    built = {"adjacency_edges": contracts.from_columns(edges(sp, scales, n_a, cfg), "adjacency_edges")}
    check(built, frames, wav, coh, cfg)
    ed = built["adjacency_edges"]
    info = {
        "weight": cfg["adjacency.edge_weight"], "rule": cfg["adjacency.edge_rule"], "per_band": cfg["adjacency.per_band"],
        "expected": 1.0 - cfg["coherence.quantile"],
        "effective_n": "max(1, n_cells^2 / (sqrt(2 pi) x min(width x voices, scales in scope) x sum of in-cone months x scale))",
        "decision": f"{cfg['inference.cooccurrence_family_method']} at q = {cfg['inference.q']}, within one configuration and family; no configuration is preferred",
        "families": {name: {"tests": int(((ed["family"] == name) & ed["p_value"].notna()).sum()), "edges": int(((ed["family"] == name) & ed["edge"]).sum())} for name in FAMILIES},
        "p_values": "adjacency_edges.p_value, one per (k, i_a, i_b, scope), raw",
    }
    return built, info


def _differs(got: np.ndarray, want: np.ndarray) -> np.ndarray:
    """Where two float columns differ beyond rounding; a null matches only a null."""
    got, want = np.asarray(got, dtype=np.float64), np.asarray(want, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        close = np.abs(got - want) <= RTOL * np.maximum(np.abs(want), TINY)
    return ~(close | (np.isnan(got) & np.isnan(want)))


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], wav: dict[str, pd.DataFrame], coh: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Acceptance: rdiag's s3.adjacency invariants with k in the key; a failure carries the failing rows."""
    ed = b["adjacency_edges"]
    sp, scales, n_a = _inputs(frames, wav, coh, cfg)
    if len(ed) != len(sp):
        raise AcceptanceError("adjacency", f"adjacency_edges has {len(ed)} rows, expected {len(sp)}")
    m = ed[KEY].astype(np.int64).merge(sp[KEY].astype(np.int64), how="outer", indicator=True)
    wrong = m[m["_merge"] != "both"]
    if len(wrong):
        rule = "the rows are coherence_scope's (k, pair, scope) rows"
        raise AcceptanceError("adjacency", f"adjacency_edges: {rule} ({len(wrong)} rows)", wrong[KEY].assign(artifact="adjacency_edges", problem=rule))
    ed = ed.sort_values(KEY).reset_index(drop=True)
    want = edges(sp, scales, n_a, cfg)
    weight, p, q = (ed[c].to_numpy(np.float64) for c in ("weight", "p_value", "q_value"))
    with np.errstate(invalid="ignore"):
        rules = [
            (_differs(weight, want["weight"]) | (weight < 0) | (weight > 1), "weight is n_significant / n_cells, null where the scope has no in-cone cell"),
            (_differs(ed["expected"], want["expected"]), "expected is 1 - coherence.quantile"),
            (_differs(ed["n_eff"], want["n_eff"]) | (ed["n_eff"].to_numpy() < 1), "n_eff is the Kish count of smoothing footprints, at least 1"),
            (_differs(p, want["p_value"]) | (p <= 0) | (p > 1), "p_value is the binomial exceedance of weight x n_eff, in (0, 1]"),
            ((ed["family"].astype(str).to_numpy() != want["family"]) | (ed["family_size"].to_numpy() != want["family_size"]),
             "family is all for the all-scales rows and band for the overlaps, and family_size counts its tests in the configuration"),
            (_differs(q, want["q_value"]) | (q < p), "q_value is Benjamini-Yekutieli within the configuration's family"),
            (ed["edge"].to_numpy() != (q <= cfg["inference.q"]), "edge equals q_value <= inference.q"),
        ]
    problems, out = [], []
    for mask, rule in rules:
        if mask.any():
            problems.append(f"adjacency_edges: {rule} ({int(mask.sum())} rows)")
            out.append(ed.loc[mask, KEY].assign(artifact="adjacency_edges", problem=rule))
    if problems:
        raise AcceptanceError("adjacency", "; ".join(problems), pd.concat(out, ignore_index=True))
