"""The only source of randomness for the analyses on the archive (rdiag common/seeds).

    stream(cfg, stage, *keys) -> numpy.random.Generator
built from SeedSequence(cfg["seed"], spawn_key=(hash32(stage), *keys)). Keys are non-negative ints
(configuration, series, pair, draw). The same stage name and keys give the same generator in every
run and every process: hash32 is the first four bytes of sha256(stage name), never Python's hash().
No module seeds numpy globally or draws without a generator from here.
Stage 10's bootstrap predates this module and keeps its own key, [seed, 10, i].
"""

from __future__ import annotations

import hashlib

import numpy as np


def hash32(name: str) -> int:
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big")


def stream(cfg: dict, stage: str, *keys: int) -> np.random.Generator:
    if any(isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 0 for k in keys):
        raise ValueError(f"seed keys must be non-negative ints, got {keys}")
    return np.random.default_rng(np.random.SeedSequence(cfg["seed"], spawn_key=(hash32(stage), *(int(k) for k in keys))))
