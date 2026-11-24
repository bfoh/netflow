"""The TFTP server is tested against tftpy, an independent client implementation."""

import hashlib
import os
import socket
import struct
import time

import pytest
import tftpy

from undm.transfer.tftp import TftpServer, TftpServerError


@pytest.fixture
def server():
    s = TftpServer("127.0.0.1", 0, timeout=1.0, retries=3)
    s.start()
    yield s
    s.stop()


def fetch(server, name, dest, **options):
    client = tftpy.TftpClient("127.0.0.1", server.port, dict(options))
    client.download(name, str(dest), timeout=2)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def last_record(server, name):
    """The server finalises a record just after the client's last ACK; wait for that."""
    deadline = time.time() + 3
    while time.time() < deadline:
        records = server.transfers_for(name)
        if records and records[-1].finished_at is not None:
            return records[-1]
        time.sleep(0.02)
    return server.transfers_for(name)[-1]


@pytest.mark.parametrize("size", [0, 1, 511, 512, 513, 1024, 70_000])
def test_downloads_are_byte_exact(server, tmp_path, size):
    src = tmp_path / "image.swi"
    src.write_bytes(os.urandom(size))
    server.publish("image.swi", src)
    out = tmp_path / "out.bin"
    fetch(server, "image.swi", out)
    assert sha(out) == sha(src)
    record = last_record(server, "image.swi")
    assert record.completed and record.bytes_sent == size and record.error == ""


def test_blksize_and_tsize_options(server, tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(os.urandom(100_000))
    server.publish("f.bin", src)
    out = tmp_path / "o.bin"
    fetch(server, "f.bin", out, blksize=1024, tsize=0)
    assert sha(out) == sha(src)


def test_block_number_rollover(server, tmp_path):
    """More than 65535 blocks: block numbers wrap around."""
    src = tmp_path / "big.bin"
    src.write_bytes(os.urandom(8 * 65_700))
    server.publish("big.bin", src)
    out = tmp_path / "o.bin"
    fetch(server, "big.bin", out, blksize=8)
    assert sha(out) == sha(src)


def test_only_published_names_are_served(server, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("not published")
    src = tmp_path / "ok.txt"
    src.write_text("ok")
    server.publish("ok.txt", src)
    for name in ("secret.txt", "../secret.txt", str(secret), "ok.txt.bak"):
        with pytest.raises(tftpy.TftpException):
            fetch(server, name, tmp_path / "x")
    server.unpublish("ok.txt")
    with pytest.raises(tftpy.TftpException):
        fetch(server, "ok.txt", tmp_path / "x")


def test_client_allowlist(server, tmp_path):
    src = tmp_path / "cfg.txt"
    src.write_text("hostname x\n")
    server.publish("cfg.txt", src, clients={"192.0.2.77"})  # not us
    with pytest.raises(tftpy.TftpException):
        fetch(server, "cfg.txt", tmp_path / "x")
    server.publish("cfg.txt", src, clients={"127.0.0.1"})
    fetch(server, "cfg.txt", tmp_path / "y")
    assert (tmp_path / "y").read_text() == "hostname x\n"


def test_uploads_are_refused(server, tmp_path):
    f = tmp_path / "up.txt"
    f.write_text("data")
    with pytest.raises(tftpy.TftpException):
        tftpy.TftpClient("127.0.0.1", server.port).upload("up.txt", str(f), timeout=2)
    assert not server.transfers


def test_publish_rejects_paths_and_missing_files(server, tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"x")
    for bad in ("../a.bin", "dir/a.bin", "dir\\a.bin", ".hidden", ""):
        with pytest.raises(ValueError):
            server.publish(bad, f)
    with pytest.raises(FileNotFoundError):
        server.publish("missing.bin", tmp_path / "missing.bin")


def test_abandoned_transfer_is_recorded_as_incomplete(server, tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(os.urandom(5000))
    server.publish("f.bin", src)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    sock.sendto(struct.pack("!H", 1) + b"f.bin\0octet\0", ("127.0.0.1", server.port))
    data, _ = sock.recvfrom(2048)  # first block arrives; never acknowledge it
    assert struct.unpack("!HH", data[:4]) == (3, 1)
    sock.close()
    deadline = time.time() + 8
    while time.time() < deadline and server.transfers[-1].finished_at is None:
        time.sleep(0.1)
    record = server.transfers[-1]
    assert not record.completed and "timeout" in record.error


def test_port_conflict_gives_clear_error(server):
    other = TftpServer("127.0.0.1", server.port)
    with pytest.raises(TftpServerError, match="Another TFTP program"):
        other.start()


def _start_raw_fetch(server, name):
    """Request ``name`` and acknowledge the first block; returns (socket, server TID)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    sock.sendto(struct.pack("!H", 1) + name.encode() + b"\0octet\0", ("127.0.0.1", server.port))
    data, tid = sock.recvfrom(2048)
    assert struct.unpack("!HH", data[:4]) == (3, 1)
    return sock, tid


@pytest.mark.parametrize("how", ["withdrawn", "stopped"])
def test_a_transfer_in_progress_is_cancelled(tmp_path, how):
    """Bench 2026-11-24: a fetch must not carry on after UNDM ended the step. Withdrawing
    the file (or stopping the server) cancels the transfer at the next block."""
    s = TftpServer("127.0.0.1", 0, timeout=1.0, retries=3)
    s.start()
    try:
        src = tmp_path / "image.out"
        src.write_bytes(os.urandom(512 * 20))
        s.publish("image.out", src)
        sock, tid = _start_raw_fetch(s, "image.out")
        if how == "withdrawn":
            s.unpublish("image.out")
        else:
            s.stop()
        sock.sendto(struct.pack("!HH", 4, 1), tid)  # acknowledge block 1
        data, _ = sock.recvfrom(2048)
        assert struct.unpack("!H", data[:2])[0] == 5  # ERROR instead of block 2
        assert b"cancelled" in data
        sock.close()
        record = s.transfers[-1]
        deadline = time.time() + 3
        while time.time() < deadline and record.finished_at is None:
            time.sleep(0.02)
        assert not record.completed and record.bytes_sent == 512
        assert record.error.startswith("cancelled by UNDM")
    finally:
        s.stop()


def test_a_republished_file_keeps_its_transfer_going(server, tmp_path):
    src = tmp_path / "image.out"
    src.write_bytes(os.urandom(512 * 3))
    server.publish("image.out", src, {"127.0.0.1"})
    sock, tid = _start_raw_fetch(server, "image.out")
    server.publish("image.out", src, {"127.0.0.1"})  # offered again: same file, same client
    sock.sendto(struct.pack("!HH", 4, 1), tid)
    data, _ = sock.recvfrom(2048)
    assert struct.unpack("!HH", data[:4]) == (3, 2)
    sock.close()
