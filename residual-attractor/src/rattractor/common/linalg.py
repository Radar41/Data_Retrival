"""Linear algebra with fixed conventions, shared by the analyses on the archive (rdiag common/linalg).

    corr(X)        Pearson correlation of the columns of X, (..., observations, variables) ->
                   (..., variables, variables); columns standardized with ddof = 1. A flat column
                   (max == min) has no correlation: its row and column are NaN.
    eigh_desc(A)   (eigenvalues descending, eigenvectors as columns) of symmetric A, from
                   numpy.linalg.eigh, with the sign rule applied after it so the output is unique:
                   each vector's sum is >= 0; where the sum is 0 to SIGN_TOL, the vector's first
                   entry larger than SIGN_TOL in size is positive.
    mp_edge(N, w)  (1 + sqrt(N / w))^2, the Marchenko-Pastur upper edge for N series over w months.
    angle(u, v)    the angle between two vectors, radians in [0, pi]: 2 atan2(|u - v|, |u + v|) on
                   the unit vectors, which stays exact near 0 and pi where arccos does not.
Every function broadcasts over leading axes. rdiag's principal_angles is not built: no stage reads
it yet (rdiag uses it for the factor split and for replay).
"""

from __future__ import annotations

import numpy as np

SIGN_TOL = 1e-12  # rdiag: "if the sum is 0 to 1e-12, the first nonzero entry is positive"


def corr(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    n = X.shape[-2]
    c = X - X.mean(axis=-2, keepdims=True)
    ss = (c * c).sum(axis=-2, keepdims=True)
    flat = (X.max(axis=-2, keepdims=True) == X.min(axis=-2, keepdims=True)) | (ss == 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        Z = np.where(flat, np.nan, c / np.sqrt(ss / (n - 1)))
    return np.swapaxes(Z, -1, -2) @ Z / (n - 1)


def sign_rule(V: np.ndarray) -> np.ndarray:
    """+1 or -1 for each column of V (..., n, r): the factor that gives the column the sign the rule asks for."""
    sums = V.sum(axis=-2)
    first = np.take_along_axis(V, np.argmax(np.abs(V) > SIGN_TOL, axis=-2)[..., None, :], axis=-2)[..., 0, :]
    lead = np.where(np.abs(sums) <= SIGN_TOL, first, sums)
    return np.where(lead < 0.0, -1.0, 1.0)


def eigh_desc(A: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    vals, vecs = np.linalg.eigh(A)
    vals, vecs = vals[..., ::-1], vecs[..., ::-1]
    return np.ascontiguousarray(vals), vecs * sign_rule(vecs)[..., None, :]


def mp_edge(N: int, window: int) -> float:
    return float((1.0 + np.sqrt(N / window)) ** 2)


def angle(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    u = u / np.linalg.norm(u, axis=-1, keepdims=True)
    v = v / np.linalg.norm(v, axis=-1, keepdims=True)
    return 2.0 * np.arctan2(np.linalg.norm(u - v, axis=-1), np.linalg.norm(u + v, axis=-1))
