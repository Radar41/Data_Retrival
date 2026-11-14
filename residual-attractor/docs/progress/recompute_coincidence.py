"""Second implementation of coincidence on a built archive, by plain loops and exact fractions.
Reads events/flags.parquet and coincidence/precursor.parquet; imports no stage code.

usage: PY -I recompute_coincidence.py <build dir> [n_rows=600]
"""
import json, sys
from fractions import Fraction
import numpy as np, pandas as pd

b = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 600
cfg = json.load(open(f"{b}/manifest.json"))["config"]
ev = pd.read_parquet(f"{b}/events/flags.parquet").sort_values(["k", "i", "t"])
co = pd.read_parquet(f"{b}/coincidence/precursor.parquet")
K, N = ev.k.nunique(), ev.i.nunique(); P = len(ev) // (K * N)
E = ev.event.to_numpy().reshape(K, N, P); D = ev.defined.to_numpy().reshape(K, N, P)
m = cfg["surrogates.circular_shift_min_offset"]
offs = list(range(m, P - m + 1))
assert cfg["surrogates.n_coincidence"] >= len(offs), "drawn mode: not covered here"

def counts(a, eb, db, lo, hi):
    el = hit = 0
    for t in range(P):
        if a[t] and t + hi <= P - 1 and all(db[t + d] for d in range(lo, hi + 1)):
            el += 1; hit += any(eb[t + d] for d in range(lo, hi + 1))
    return hit, el

bad = 0
for r in co.sample(min(n, len(co)), random_state=1).itertuples():
    a, eb, db = E[r.k, r.i_a], E[r.k, r.i_b], D[r.k, r.i_b]
    h, el = counts(a, eb, db, r.delta_min, r.delta_max)
    rate = Fraction(h, el); used = ge = 0
    for o in offs:
        hs, es = counts(a, np.roll(eb, -o), np.roll(db, -o), r.delta_min, r.delta_max)
        if es:
            used += 1; ge += Fraction(hs, es) >= rate
    want = (r.n_events_a == a.sum(), r.n_eligible_a == el, r.rate == float(rate), r.n_surrogates == used, r.p_value == float(Fraction(1 + ge, 1 + used)))
    if not all(want):
        bad += 1
        if bad <= 5: print("MISMATCH", r.k, r.i_a, r.i_b, r.delta_min, r.delta_max, want)
print(f"checked {min(n, len(co))} rows, {bad} mismatches")
