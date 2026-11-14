"""The linear algebra conventions the analyses on the archive share (rdiag common/linalg)."""

import numpy as np
import pytest

from rattractor.common import linalg


def test_corr_is_pearson_on_columns_and_broadcasts(rng):
    X = rng.standard_normal((5, 30, 4)) * np.array([1.0, 10.0, 0.01, 300.0]) + np.array([0.0, 5.0, -2.0, 1e3])
    C = linalg.corr(X)
    assert C.shape == (5, 4, 4)
    for j in range(5):
        np.testing.assert_allclose(C[j], np.corrcoef(X[j], rowvar=False), rtol=0, atol=1e-12)
    np.testing.assert_allclose(np.diagonal(C, axis1=1, axis2=2), 1.0, rtol=0, atol=1e-14)
    np.testing.assert_array_equal(linalg.corr(X[2]), C[2])  # one matrix or a stack: the same numbers


def test_corr_of_a_flat_column_is_undefined_and_leaves_the_rest(rng):
    X = rng.standard_normal((24, 3))
    X[:, 1] = 0.1  # 24 x 0.1 does not sum to 2.4 exactly: the centred column is rounding noise, not zero
    C = linalg.corr(X)
    assert np.isnan(C[1]).all() and np.isnan(C[:, 1]).all()
    assert C[0, 2] == pytest.approx(np.corrcoef(X[:, 0], X[:, 2])[0, 1], abs=1e-14) and C[0, 0] == pytest.approx(1.0, abs=1e-14)


def test_eigh_desc_orders_reconstructs_and_signs(rng):
    A = rng.standard_normal((6, 7, 7))
    A = A + np.swapaxes(A, 1, 2)
    vals, vecs = linalg.eigh_desc(A)
    assert (np.diff(vals, axis=1) <= 0).all()
    np.testing.assert_allclose(vecs @ (vals[:, :, None] * np.swapaxes(vecs, 1, 2)), A, atol=1e-12)
    np.testing.assert_allclose(np.swapaxes(vecs, 1, 2) @ vecs, np.broadcast_to(np.eye(7), (6, 7, 7)), atol=1e-12)
    assert (vecs.sum(axis=1) >= 0).all()                       # every vector, not only the leading one
    one_vals, one_vecs = linalg.eigh_desc(A[3])
    np.testing.assert_array_equal(one_vals, vals[3])
    np.testing.assert_array_equal(one_vecs, vecs[3])


def test_sign_rule_breaks_a_zero_sum_by_the_first_entry():
    # [[1, r], [r, 1]] with r < 0: the leading vector is (1, -1) / sqrt(2), whose sum is 0.
    vals, vecs = linalg.eigh_desc(np.array([[1.0, -0.5], [-0.5, 1.0]]))
    np.testing.assert_allclose(vals, [1.5, 0.5], atol=1e-15)
    np.testing.assert_allclose(vecs[:, 0], [2 ** -0.5, -(2 ** -0.5)], atol=1e-15)
    np.testing.assert_allclose(vecs[:, 1], [2 ** -0.5, 2 ** -0.5], atol=1e-15)
    V = np.array([[0.0, -0.6, 1e-13], [-1.0, 0.8, -1.0], [1.0, 0.2, 1.0]])   # columns: sum 0; sum 0.4; sum 1e-13 (a tie)
    np.testing.assert_array_equal(linalg.sign_rule(V), [-1.0, 1.0, -1.0])    # first entry beyond the tolerance decides a tie
    np.testing.assert_array_equal(linalg.sign_rule(-V), [1.0, -1.0, 1.0])


def test_mp_edge():
    assert linalg.mp_edge(14, 24) == pytest.approx((1 + np.sqrt(14 / 24)) ** 2, rel=1e-15)
    assert linalg.mp_edge(24, 24) == 4.0 and linalg.mp_edge(1, 4) == 2.25


def test_angle_is_exact_at_both_ends(rng):
    u = rng.standard_normal(9)
    assert linalg.angle(u, u) == 0.0 and linalg.angle(u, 3.0 * u) < 1e-15    # arccos of a rounded dot product would give ~1e-8
    assert linalg.angle(u, -u) == pytest.approx(np.pi, abs=1e-15)
    e = np.eye(4)
    assert linalg.angle(e[0], e[1]) == pytest.approx(np.pi / 2, abs=1e-15)
    small = np.array([np.cos(1e-9), np.sin(1e-9), 0.0, 0.0])
    assert linalg.angle(e[0], small) == pytest.approx(1e-9, rel=1e-6)
    a, b = rng.standard_normal((2, 50, 6))
    want = np.arccos(np.clip((a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1), -1, 1))
    np.testing.assert_allclose(linalg.angle(a, b), want, atol=1e-12)          # broadcasts over rows
