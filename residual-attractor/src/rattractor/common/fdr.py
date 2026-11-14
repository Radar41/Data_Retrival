"""Benjamini-Yekutieli q-values within one family of tests (rdiag inference/fdr.py).

For the m p-values of a family sorted ascending, p_(1) <= ... <= p_(m):

    q_(i) = min over j >= i of  min(1, p_(j) x m x c(m) / j),      c(m) = 1 + 1/2 + ... + 1/m

A test is a discovery at level q when its q-value is <= q, which is the step-up rule: reject the i smallest
where i is the largest rank with p_(i) <= i q / (m c(m)). The bound holds under any dependence between the
tests (Benjamini and Yekutieli 2001), which shared surrogates and overlapping cells create. The sort is
stable and equal p-values get equal q-values. A null p-value is no test: it gets a null q-value and does not
count in m. What a family is, is the caller's decision; nothing here looks across families.
"""

from __future__ import annotations

import numpy as np

METHODS = ("benjamini_yekutieli",)


def harmonic(m: int) -> float:
    """c(m) = 1 + 1/2 + ... + 1/m."""
    return float((1.0 / np.arange(1, m + 1)).sum())


def benjamini_yekutieli(p: np.ndarray) -> np.ndarray:
    """q-values of one family, in the order given."""
    p = np.asarray(p, dtype=np.float64)
    out = np.full(p.shape, np.nan)
    ok = ~np.isnan(p)
    m = int(ok.sum())
    if not m:
        return out
    order = np.argsort(p[ok], kind="stable")
    raw = p[ok][order] * (m * harmonic(m)) / np.arange(1, m + 1)
    q = np.empty(m)
    q[order] = np.minimum(np.minimum.accumulate(raw[::-1])[::-1], 1.0)
    out[ok] = q
    return out
