"""Minimal read-only TFTP server (RFC 1350, options RFC 2347-2349).

Purpose-built for staging: devices on the bench pull firmware images and
configuration files from the PC running UNDM. Deliberately restricted:

* read requests only — write requests are refused;
* only files explicitly published are served, under the published name;
* each published file may be limited to named client addresses;
* every transfer is recorded (client, bytes, completed or error);
* a transfer in progress is cancelled when its file is withdrawn or the server stops,
  so a device cannot finish fetching a file after UNDM has ended the step.

Binary (octet) transfer only; netascii requests are served the same bytes.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERROR, OP_OACK = 1, 2, 3, 4, 5, 6
ERR_NOT_FOUND, ERR_ACCESS, ERR_ILLEGAL = 1, 2, 4
DEFAULT_BLOCK = 512
MAX_BLOCK = 1428  # fits a 1500-byte Ethernet frame without IP fragmentation


@dataclass
class Transfer:
    client: str
    name: str
    size: int
    bytes_sent: int = 0
    completed: bool = False
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


@dataclass(frozen=True)
class _Published:
    path: Path
    clients: frozenset[str] | None  # None = any client


class TftpServerError(RuntimeError):
    pass


class TftpServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 69, *,  # noqa: S104 - see docstring
                 timeout: float = 3.0, retries: int = 5) -> None:
        self.host, self.port = host, port
        self.timeout, self.retries = timeout, retries
        self._files: dict[str, _Published] = {}
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.transfers: list[Transfer] = []

    # -- publishing -----------------------------------------------------------------
    def publish(self, name: str, path: Path, clients: set[str] | None = None) -> None:
        if not name or "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("Published name must be a plain file name")
        if not path.is_file():
            raise FileNotFoundError(path)
        with self._lock:
            self._files[name] = _Published(path, frozenset(clients) if clients else None)

    def unpublish(self, name: str) -> None:
        with self._lock:
            self._files.pop(name, None)

    def _still_offered(self, name: str, path: Path, client: str) -> bool:
        with self._lock:
            published = self._files.get(name)
        return (published is not None and published.path == path
                and (published.clients is None or client in published.clients))

    def transfers_for(self, name: str, client: str | None = None) -> list[Transfer]:
        with self._lock:
            return [t for t in self.transfers
                    if t.name == name and (client is None or t.client == client)]

    # -- lifecycle ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
        except OSError as e:
            sock.close()
            raise TftpServerError(
                f"Cannot start the TFTP server on {self.host}:{self.port}: {e}. Another TFTP "
                "program may be running, or the port is not permitted.") from e
        sock.settimeout(0.3)
        self.port = sock.getsockname()[1]
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="undm-tftp", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            self._sock.close()
        self._sock, self._thread = None, None

    # -- protocol -------------------------------------------------------------------
    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(2048)
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(data, addr),
                             name="undm-tftp-xfer", daemon=True).start()

    @staticmethod
    def _error(sock: socket.socket, addr: tuple[str, int], code: int, message: str) -> None:
        sock.sendto(struct.pack("!HH", OP_ERROR, code) + message.encode() + b"\0", addr)

    def _handle(self, request: bytes, addr: tuple[str, int]) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # new transfer ID (port)
        try:
            sock.bind((self.host, 0))
            sock.settimeout(self.timeout)
            if len(request) < 4:
                return
            opcode = struct.unpack("!H", request[:2])[0]
            if opcode == OP_WRQ:
                self._error(sock, addr, ERR_ACCESS, "This server is read-only")
                return
            if opcode != OP_RRQ:
                self._error(sock, addr, ERR_ILLEGAL, "Illegal TFTP operation")
                return
            fields = request[2:].split(b"\0")
            name = fields[0].decode("ascii", "replace").lstrip("/")
            raw_opts = fields[2:]
            options = {raw_opts[i].decode("ascii", "replace").lower():
                       raw_opts[i + 1].decode("ascii", "replace")
                       for i in range(0, len(raw_opts) - 1, 2) if raw_opts[i]}
            with self._lock:
                published = self._files.get(name)
            if published is None:
                self._error(sock, addr, ERR_NOT_FOUND, "File not found")
                return
            if published.clients is not None and addr[0] not in published.clients:
                self._error(sock, addr, ERR_ACCESS, "Access violation")
                return
            self._send_file(sock, addr, name, published.path, options)
        except OSError:
            pass
        finally:
            sock.close()

    def _send_file(self, sock: socket.socket, addr: tuple[str, int], name: str, path: Path,
                   options: dict[str, str]) -> None:
        size = path.stat().st_size
        record = Transfer(addr[0], name, size)
        with self._lock:
            self.transfers.append(record)
        block_size = DEFAULT_BLOCK
        ack_opts: dict[str, str] = {}
        try:
            if "blksize" in options:
                block_size = max(8, min(int(options["blksize"]), MAX_BLOCK))
                ack_opts["blksize"] = str(block_size)
            if "tsize" in options:
                ack_opts["tsize"] = str(size)
            if "timeout" in options and 1 <= int(options["timeout"]) <= 255:
                sock.settimeout(int(options["timeout"]))
                ack_opts["timeout"] = options["timeout"]
        except ValueError:
            self._error(sock, addr, 8, "Bad option value")
            record.error, record.finished_at = "bad option value", time.time()
            return

        def exchange(packet: bytes, expect_block: int) -> bool:
            """Send and wait for the matching ACK; retransmit on timeout only."""
            for _ in range(self.retries):
                sock.sendto(packet, addr)
                deadline = time.monotonic() + sock.gettimeout()  # type: ignore[operator]
                while time.monotonic() < deadline:
                    try:
                        reply, source = sock.recvfrom(1024)
                    except TimeoutError:
                        break
                    if source != addr or len(reply) < 4:
                        continue
                    op, block = struct.unpack("!HH", reply[:4])
                    if op == OP_ERROR:
                        record.error = "client aborted: " + reply[4:].rstrip(b"\0").decode(
                            "ascii", "replace")
                        return False
                    if op == OP_ACK and block == expect_block:
                        return True
                    # stale or duplicate ACK: keep waiting, do not retransmit
                if self._stop.is_set():
                    break
            record.error = record.error or "client stopped acknowledging (timeout)"
            return False

        if ack_opts:
            oack = struct.pack("!H", OP_OACK) + b"".join(
                k.encode() + b"\0" + v.encode() + b"\0" for k, v in ack_opts.items())
            if not exchange(oack, 0):
                record.finished_at = time.time()
                return
        with path.open("rb") as f:
            block = 0
            while True:
                if self._stop.is_set() or not self._still_offered(name, path, addr[0]):
                    self._error(sock, addr, 0, "Transfer cancelled by the server")
                    record.error = ("cancelled by UNDM: "
                                    + ("the server stopped" if self._stop.is_set()
                                       else "the file is no longer offered"))
                    break
                chunk = f.read(block_size)
                block = (block + 1) & 0xFFFF  # block numbers wrap for files > 65535 blocks
                if not exchange(struct.pack("!HH", OP_DATA, block) + chunk, block):
                    break
                record.bytes_sent += len(chunk)
                if len(chunk) < block_size:
                    record.completed = True
                    break
        record.finished_at = time.time()
