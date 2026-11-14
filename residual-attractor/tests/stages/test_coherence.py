"""Stage coherence (track A3). WORK IN PROGRESS: only the smoothing kernels are tested so far."""

import numpy as np
import pytest

from rattractor.common import wavelets


def test_smoothing_kernels(cfg, rng):
    P = 60
    s = wavelets.scales(wavelets.periods(P, cfg), cfg)
    G, b = wavelets.smoother(s, P, cfg)
    np.testing.assert_allclose(b, np.array([0.9, 1, 1, 1, 0.9]) / 4.8, rtol=1e-12)   # 0.6 octaves = 4.8 steps of 1/8
    assert wavelets.scale_weights({**cfg, "coherence.scale_smoothing_width": 0.1}).tolist() == [1.0]
    j, u = 5, 30
    g = np.exp(-0.5 * ((np.arange(P) - u) / s[j]) ** 2)
    np.testing.assert_allclose(G[j, :, u], g / np.exp(-0.5 * (np.arange(-400, 401) / s[j]) ** 2).sum(), rtol=1e-12)
    assert G[j, u, :].sum() == pytest.approx(1.0, abs=1e-12) and G[j, 0, :].sum() < 0.6    # nothing is renormalized at the ends
    f = rng.standard_normal((2, s.size, P)) + 1j * rng.standard_normal((2, s.size, P))
    out = wavelets.smooth(f, (G, b))
    t = np.einsum("rjt,jtu->rju", f, G)
    want = np.zeros_like(t)
    for jj in range(s.size):
        for d in range(-2, 3):
            if 0 <= jj + d < s.size:
                want[:, jj] += b[d + 2] * t[:, jj + d]
    np.testing.assert_allclose(out, want, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(wavelets.smooth(f[0], (G, b)), wavelets.smooth(f[:1], (G, b))[0])
    np.testing.assert_allclose(wavelets.smooth(f.real, (G, b)), out.real, rtol=0, atol=1e-13)


