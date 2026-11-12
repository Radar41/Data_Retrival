import numpy as np
import pytest

from rattractor.config import load_config


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture
def rng():
    return np.random.default_rng(20261112)
