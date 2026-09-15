import warnings

import pytest

from grudge_engine.sandbox.dev_backend import DevSandboxBackend


@pytest.fixture
def backend() -> DevSandboxBackend:
    """The insecure dev backend - fine for these tests since none of them exercise
    real untrusted code, only fixed reference bots and small test fixtures we
    wrote ourselves. Real isolation is exercised separately by the nsjail-marked
    tests once WSL2 + nsjail are available.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return DevSandboxBackend()
