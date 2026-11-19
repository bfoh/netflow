"""Process-wide access to the TFTP server, started only while a job needs it."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from undm.transfer.tftp import TftpServer, Transfer


def local_address_towards(device_ip: str) -> str:
    """The address of this PC on the network that leads to ``device_ip``."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((device_ip, 9))  # UDP connect sends nothing; it only selects the route
        return str(s.getsockname()[0])


class TransferSession:
    """What a driver sees: offer a file to one device, then ask whether it was fetched."""

    def __init__(self, server: TftpServer) -> None:
        self._server = server
        self._published: set[str] = set()

    @property
    def port(self) -> int:
        return self._server.port

    def offer(self, path: Path, name: str, client_ip: str) -> str:
        """Publish ``path`` as ``name`` for ``client_ip`` only; returns the server address."""
        server_ip = local_address_towards(client_ip)
        self._server.publish(name, path, {client_ip})
        self._published.add(name)
        return server_ip

    def last_transfer(self, name: str, client_ip: str) -> Transfer | None:
        records = self._server.transfers_for(name, client_ip)
        return records[-1] if records else None

    def close(self) -> None:
        for name in self._published:
            self._server.unpublish(name)
        self._published.clear()


class TransferHub:
    def __init__(self, host: str = "0.0.0.0", port: int = 69) -> None:  # noqa: S104
        self._host, self._port = host, port
        self._server: TftpServer | None = None
        self._users = 0
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._server is not None and self._server.running

    @property
    def port(self) -> int:
        """The port in use while running, otherwise the configured one."""
        return self._server.port if self._server is not None else self._port

    @contextmanager
    def session(self) -> Iterator[TransferSession]:
        """Start the server if needed; stop it when the last session ends."""
        with self._lock:
            if self._server is None:
                server = TftpServer(self._host, self._port)
                server.start()  # raises TftpServerError with a clear message
                self._server = server
            self._users += 1
            session = TransferSession(self._server)
        try:
            yield session
        finally:
            session.close()
            with self._lock:
                self._users -= 1
                if self._users == 0 and self._server is not None:
                    self._server.stop()
                    self._server = None
