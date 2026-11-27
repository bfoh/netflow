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
def _no_device_connections(monkeypatch):
    """No test reaches a device's management ports (D-130): only this PC's own loopback,
    where a test runs its own server."""
    import ipaddress
    import socket

    from undm.drivers import discovery

    def loopback_only(address, *args, **kwargs):
        if not ipaddress.ip_address(address[0]).is_loopback:
            raise AssertionError(f"a test tried to connect to {address[0]}:{address[1]}")
        return socket.create_connection(address, *args, **kwargs)

    monkeypatch.setattr(discovery, "connect", loopback_only)


@pytest.fixture(autouse=True)
def _clean_lab():
    default_lab().clear()
    default_lab().autocreate = True
    reset_simulation()
    yield
    default_lab().clear()
