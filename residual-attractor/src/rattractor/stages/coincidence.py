"""Stage coincidence: rdiag's s3.coincidence under input contract v2, inside each configuration.

Reads events_flags. Do the events of one series tend to be followed by events of another, more than
each one's own timing explains: procession, not only simultaneity. Inside one configuration k, for
every ordered pair of event series a = (kind_a, i_a) -> b = (kind_b, i_b), a != b, and every window
[delta_min, delta_max] of coincidence.windows (months):

    eligible   an event of a at month t counts when the months t + delta_min .. t + delta_max all lie
               inside the sample and b is defined on every one of them
    rate       the share of a's eligible events with at least one event of b in
               [t + delta_min, t + delta_max]                      (coincidence.direction: precursor)
    null       b's series, events and defined together, circularly shifted: b[(t + o) mod P]. a stays.
               A shift keeps b's own timing (its event count, clusters and gaps) and breaks only its
               alignment with a. The same rate is computed on every shifted series.
    p_value    (1 + #{surrogates whose rate >= rate}) / (1 + n_surrogates)

When surrogates.n_coincidence is at least the number of offsets that exist (P - 2 x
surrogates.circular_shift_min_offset + 1; 75 on spec 0), every offset is used once: the whole null
distribution, exact, and cheaper than drawing. Otherwise that many offsets are drawn for each
follower row by surrogates.offsets(cfg, "coincidence", P, n, k, i_b).

Writes coincidence_precursor, one row per (k, a, b, window) where a has an eligible event. Every
window is its own test with its raw p-value; nothing is corrected or decided here, and no value
comes from more than one configuration. A significant rate is a timing regularity, not a cause.

Source: rdiag s3_cooccurrence/coincidence.py, common/surrogates.py, schemas/30_stage3.yaml
(s3.coincidence), params coincidence.* and surrogates.n_coincidence.
Departures from rdiag, and the choices it leaves open:
  - k is in every key; both series of a pair belong to the same configuration.
  - rdiag's one window, coincidence.delta_min / delta_max = [0, 2], is the list coincidence.windows:
    the single lags [0, 0] to [12, 12] and rdiag's [0, 2], each scanned on its own (the plan:
    supply-chain pass-through runs longer than two months).
  - Eligibility at the sample's end. rdiag counts "only t where b is defined" and says nothing about a
    window that runs past the last month; with windows up to a year that decides the rate. Here an
    event of a whose window is not wholly inside the sample is not counted, so a rate is always over
    events whose whole window was observed and rates at different lags compare. n_events_a is all of
    a's events (rdiag's column); n_eligible_a is the denominator. Rows exist where n_eligible_a > 0.
  - All offsets are enumerated when the requested draws would cover them anyway. p-values then move
    in steps of 1 / (n + 1): the smallest on spec 0 is 1 / 76 = 0.013, whatever the evidence. Drawing
    1,000 from the same 75 would report 1 / 1001 for the same evidence.
  - A surrogate under which a has no eligible event has no rate and is not counted; n_surrogates is
    the number that were (it can fall short only where b has undefined months).
  - rdiag's columns f_a, a, f_b, b are kind_a, i_a, kind_b, i_b.
  - rdiag's recipe table s3.surrogate_index is not written (common.surrogates explains why), and no
    registry: the p-values stay in this table with their keys.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import contracts
from ..common import surrogates
from . import AcceptanceError
from .events import KINDS

PURPOSE = "coincidence"
DIRECTIONS = ("precursor",)


def plan(cfg: dict, P: int) -> dict:
    """How the null of one test is built for rows of P months."""
    distinct = surrogates.n_distinct(cfg, P)
    if distinct < 1:
        raise AcceptanceError(PURPOSE, f"no circular shift exists: P = {P} is shorter than twice surrogates.circular_shift_min_offset = {cfg['surrogates.circular_shift_min_offset']}")
    requested = cfg["surrogates.n_coincidence"]
    n = distinct if requested >= distinct else requested
    return {"mode": "enumerated" if requested >= distinct else "drawn", "n": int(n), "requested": requested,
            "distinct_offsets": int(distinct), "smallest_p_value": 1.0 / (n + 1)}


def offset_weights(cfg: dict, P: int, k: int, series: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(the offsets that exist, how many of each follower's surrogates use each one).

    series: the series index i of every event series (unit) of configuration k. Enumerated: every offset once
    for every unit. Drawn: each unit's own draws, keyed by its series, counted per offset.
    """
    pl, m = plan(cfg, P), cfg["surrogates.circular_shift_min_offset"]
    offsets = np.arange(m, m + pl["distinct_offsets"], dtype=np.int64)
    if pl["mode"] == "enumerated":
        return offsets, np.ones((series.size, offsets.size), dtype=np.int64)
    draws = {int(i): np.bincount(surrogates.offsets(cfg, PURPOSE, P, pl["n"], k, int(i)) - m, minlength=offsets.size) for i in np.unique(series)}
    return offsets, np.stack([draws[int(i)] for i in series])


def configuration(E: np.ndarray, D: np.ndarray, windows: list, offsets: np.ndarray, weights: np.ndarray) -> dict[str, np.ndarray]:
    """One configuration's tests. E, D: (units, P) events and defined. Returns (windows, units a, units b) arrays:
    n_eligible and hits of the series as observed, and over the surrogates n_used and n_ge (rate >= the observed)."""
    U, P = E.shape
    S = offsets.size
    # index 0 holds every series as observed, 1 + s every series shifted by offsets[s]
    Es = np.stack([E] + [surrogates.shift(E, o) for o in offsets]).astype(np.int64)
    Ds = np.stack([D] + [surrogates.shift(D, o) for o in offsets]).astype(np.int64)
    zero = np.zeros((1 + S, U, 1), dtype=np.int64)
    cE, cD = np.concatenate([zero, np.cumsum(Es, axis=2)], axis=2), np.concatenate([zero, np.cumsum(Ds, axis=2)], axis=2)   # counts over months [0, j)
    lead = E.astype(np.float64)
    out = {name: np.zeros((len(windows), U, U), dtype=np.int64) for name in ("n_eligible", "hits", "n_used", "n_ge")}
    for w, (lo, hi) in enumerate(windows):
        T = P - hi                                   # an event of a at t < T has its whole window inside the sample
        if T <= 0:
            continue
        events_in = cE[:, :, hi + 1 : hi + 1 + T] - cE[:, :, lo : lo + T]     # b's events in [t + lo, t + hi]
        defined_in = cD[:, :, hi + 1 : hi + 1 + T] - cD[:, :, lo : lo + T]
        eligible = defined_in == hi - lo + 1
        followed = eligible & (events_in > 0)
        # (1 + S, a, b): a's events at eligible months, and those of them that are followed; exact, the sums are counts
        n_el = np.rint(lead[:, :T] @ eligible.transpose(0, 2, 1).astype(np.float64)).astype(np.int64)
        hits = np.rint(lead[:, :T] @ followed.transpose(0, 2, 1).astype(np.float64)).astype(np.int64)
        used = n_el[1:] > 0
        ge = used & (hits[1:] * n_el[0][None] >= hits[0][None] * n_el[1:])   # rate_s >= rate, compared as whole numbers
        out["n_eligible"][w], out["hits"][w] = n_el[0], hits[0]
        out["n_used"][w] = np.einsum("bs,sab->ab", weights, used.astype(np.int64))
        out["n_ge"][w] = np.einsum("bs,sab->ab", weights, ge.astype(np.int64))
    return out


def kind_codes(column: pd.Series, kinds: list[str]) -> np.ndarray:
    """The position of each row's kind in `kinds`, -1 for a kind that is not among them."""
    return column.astype(object).map({kind: j for j, kind in enumerate(kinds)}).fillna(-1).to_numpy(dtype=np.int64)


def units(evented: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], cfg: dict) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """(E, D as (K, units, P) arrays, the kinds): unit = position of the kind x N + i."""
    ev = evented["events_flags"]
    kinds = [kind for kind in KINDS if kind in set(cfg["events.kinds"])]
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), months.size
    f = kind_codes(ev["kind"], kinds)
    if len(ev) != K * len(kinds) * N * P or (f < 0).any():
        raise AcceptanceError(PURPOSE, f"events_flags has {len(ev)} rows, expected one per (k, kind, i, t): {K} x {len(kinds)} x {N} x {P}, of the kinds {kinds}")
    where = (ev["k"].to_numpy(), f * N + ev["i"].to_numpy(), np.searchsorted(months, ev["t"].to_numpy()))
    E, D = np.zeros((K, len(kinds) * N, P), dtype=bool), np.zeros((K, len(kinds) * N, P), dtype=bool)
    E[where], D[where] = ev["event"].to_numpy(), ev["defined"].to_numpy()
    return E, D, kinds


def run(frames: dict[str, pd.DataFrame], evented: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    E, D, kinds = units(evented, frames, cfg)
    K, U, P = E.shape
    N = len(frames["grid_series"])
    windows = [(int(lo), int(hi)) for lo, hi in cfg["coincidence.windows"]]
    cols = {c: [] for c in ("k", "a", "b", "w", "n_events_a", "n_eligible_a", "hits", "n_surrogates", "n_ge")}
    if U >= 2:                                       # one event series has nothing to be followed by
        series = np.tile(np.arange(N), len(kinds))
        ww, aa, bb = (x.reshape(-1) for x in np.meshgrid(np.arange(len(windows)), np.arange(U), np.arange(U), indexing="ij"))
        order = np.lexsort((ww, bb, aa))             # rows run a, b, then the windows in the config's order
        ww, aa, bb = ww[order], aa[order], bb[order]
        for k in range(K):
            got = configuration(E[k], D[k], windows, *offset_weights(cfg, P, k, series))
            n_el = got["n_eligible"][ww, aa, bb]
            keep = (aa != bb) & (n_el > 0)
            for name, values in (("k", np.full(ww.size, k)), ("a", aa), ("b", bb), ("w", ww), ("n_events_a", E[k].sum(axis=1)[aa]), ("n_eligible_a", n_el),
                                 ("hits", got["hits"][ww, aa, bb]), ("n_surrogates", got["n_used"][ww, aa, bb]), ("n_ge", got["n_ge"][ww, aa, bb])):
                cols[name].append(values[keep])
    c = {name: (np.concatenate(v) if v else np.zeros(0, dtype=np.int64)) for name, v in cols.items()}
    win = np.array(windows, dtype=np.int64).reshape(-1, 2)
    kind_of = np.array(kinds, dtype=object)
    built = {"coincidence_precursor": contracts.from_columns({
        "k": c["k"], "kind_a": kind_of[c["a"] // N], "i_a": c["a"] % N, "kind_b": kind_of[c["b"] // N], "i_b": c["b"] % N,
        "delta_min": win[c["w"], 0], "delta_max": win[c["w"], 1], "n_events_a": c["n_events_a"], "n_eligible_a": c["n_eligible_a"],
        "rate": c["hits"] / np.maximum(c["n_eligible_a"], 1), "n_surrogates": c["n_surrogates"],
        "p_value": (1 + c["n_ge"]) / (1 + c["n_surrogates"]),
    }, "coincidence_precursor")}
    check(built, frames, evented, cfg)
    info = {
        "rdiag": "s3.coincidence, every ordered pair of event series inside each configuration",
        "direction": cfg["coincidence.direction"],
        "windows": [list(x) for x in windows],
        "event_series_per_configuration": U,
        "ordered_pairs_per_configuration": U * (U - 1),
        "null": {**plan(cfg, P), "shift": "the follower's events and defined, b[(t + o) mod P]"} if U >= 2 else "no pair of event series: nothing to test",
        "tests": len(built["coincidence_precursor"]),
        "tests_possible": K * U * (U - 1) * len(windows),
        "eligibility": "an event of a counts when its whole window lies inside the sample and b is defined on all of it",
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], evented: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Stage coincidence acceptance: rdiag's s3.coincidence invariants in their v2 form; a failure carries the failing rows."""
    co = b["coincidence_precursor"]
    E, D, kinds = units(evented, frames, cfg)
    K, U, P = E.shape
    N = len(frames["grid_series"])
    windows = [(int(lo), int(hi)) for lo, hi in cfg["coincidence.windows"]]
    fa, fb = (kind_codes(co[c], kinds) for c in ("kind_a", "kind_b"))
    index = {win: j for j, win in enumerate(windows)}
    w = np.array([index.get(win, -1) for win in zip(co["delta_min"].tolist(), co["delta_max"].tolist())], dtype=np.int64)
    kk, ia, ib = (co[c].to_numpy().astype(np.int64) for c in ("k", "i_a", "i_b"))
    known = (fa >= 0) & (fb >= 0) & (w >= 0) & (kk >= 0) & (kk < K) & (ia >= 0) & (ia < N) & (ib >= 0) & (ib < N)
    keys = ["k", "kind_a", "i_a", "kind_b", "i_b", "delta_min", "delta_max"]
    if not known.all():
        raise AcceptanceError(PURPOSE, f"coincidence_precursor: {int((~known).sum())} rows name a configuration, event series or window that does not exist",
                              co.loc[~known, keys].assign(artifact="coincidence_precursor", problem="unknown configuration, event series or window"))
    a, bq = fa * N + ia, fb * N + ib
    # eligibility again, by another route: month by month over each window
    want = np.zeros((len(windows), K, U, U), dtype=np.int64)
    for j, (lo, hi) in enumerate(windows):
        T = P - hi
        if T > 0:
            whole = np.logical_and.reduce([D[:, :, d : d + T] for d in range(lo, hi + 1)])       # (K, b, T)
            want[j] = np.einsum("kat,kbt->kab", E[:, :, :T].astype(np.int64), whole.astype(np.int64))
    want[:, :, np.arange(U), np.arange(U)] = 0       # a series is never paired with itself
    n_el, n_ev, n_s, rate, p = (co[c].to_numpy() for c in ("n_eligible_a", "n_events_a", "n_surrogates", "rate", "p_value"))
    hits, ge = rate * n_el, p * (1 + n_s)
    limit = plan(cfg, P)["n"] if U >= 2 else 0
    rules = [
        (a == bq, "a series is never paired with itself"),
        (n_ev != E.sum(axis=2)[kk, a], "n_events_a counts the events of the leading series"),
        (n_el != want[w, kk, a, bq], "n_eligible_a counts the leading events whose whole window is inside the sample with the follower defined"),
        (n_el < 1, "a row exists only where the leading series has an eligible event"),
        ((rate < 0) | (rate > 1) | (np.abs(hits - np.rint(hits)) > 1e-9), "rate is a share of the eligible events, between 0 and 1"),
        ((n_s < 1) | (n_s > limit), "n_surrogates lies between 1 and the surrogates the null holds"),
        (~((p > 0) & (p <= 1)) | (np.abs(ge - np.rint(ge)) > 1e-9) | (np.rint(ge) < 1), "p_value is (1 + a count) / (1 + n_surrogates), in (0, 1]"),
    ]
    problems, failing = [], []
    for mask, rule in rules:
        if mask.any():
            problems.append(f"coincidence_precursor: {rule} ({int(mask.sum())} rows)")
            failing.append(co.loc[mask, keys].assign(artifact="coincidence_precursor", problem=rule))
    present = np.zeros(want.shape, dtype=bool)
    present[w, kk, a, bq] = True
    missing = (want > 0) & ~present
    if missing.any():
        problems.append(f"coincidence_precursor: {int(missing.sum())} tests with eligible events have no row")
    if problems:
        raise AcceptanceError(PURPOSE, "; ".join(problems), pd.concat(failing, ignore_index=True) if failing else None)
