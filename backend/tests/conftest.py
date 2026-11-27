import pytest

from undm.drivers.mock.lab import default_lab
from undm.services.provisioning import reset_simulation


@pytest.fixture(autouse=True)
def _no_ping_or_tracert(monkeypatch):
    """No test starts Windows' ping or tracert (D-128): tests replace the runner."""
    from undm.services import pc_tools

    def forbidden(argv, timeout):
        raise AssertionError(f"a test tried to start {argv[0]}")

    monkeypatch.setattr(pc_tools, "runner", forbidden)


@pytest.fixture(autouse=True)
def _clean_lab():
    default_lab().clear()
    default_lab().autocreate = True
    reset_simulation()
    yield
    default_lab().clear()
