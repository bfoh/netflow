"""Ping and traceroute (D-128): the target rule, Windows' commands and their answers, hops
matched to devices, and the endpoints. Synthetic output, RFC 5737 addresses; no program is
started (conftest forbids it) and no device is contacted."""

import os
import subprocess

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.domain.troubleshoot import Hop, KnownAddress, TargetError, check_target, match_hops
from undm.drivers.ssh import base as ssh_base
from undm.services import pc_tools
from undm.services import troubleshoot as ts
from undm.services.errors import ConflictError

PING_EN = """
Pinging 198.51.100.11 with 32 bytes of data:
Reply from 198.51.100.11: bytes=32 time=3ms TTL=64
Reply from 198.51.100.11: bytes=32 time<1ms TTL=64
Request timed out.
Reply from 198.51.100.11: bytes=32 time=12ms TTL=64

Ping statistics for 198.51.100.11:
    Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),
"""
PING_UNREACHABLE = """
Pinging 198.51.100.11 with 32 bytes of data:
Reply from 198.51.100.1: Destination host unreachable.
Reply from 198.51.100.1: Destination host unreachable.
"""
PING_DE = """
Ping wird ausgeführt für 198.51.100.11 mit 32 Bytes Daten:
Antwort von 198.51.100.11: Bytes=32 Zeit<1ms TTL=64
Antwort von 198.51.100.11: Bytes=32 Zeit=2ms TTL=64
"""
TRACE = """
Tracing route to 198.51.100.11 over a maximum of 20 hops

  1    <1 ms    <1 ms    <1 ms  198.51.100.1
  2     *        2 ms     1 ms  203.0.113.9
  3     *        *        *     Request timed out.
  4     3 ms     2 ms     2 ms  198.51.100.11

Trace complete.
"""


def test_only_one_address_is_ever_a_target():
    assert check_target(" 198.51.100.11 ") == "198.51.100.11"
    for bad in ("router.example", "198.51.100.0/24", "198.51.100.1-9", "198.51.100.*",
                "-n 1 198.51.100.1", "0.0.0.0", "255.255.255.255", "224.0.0.5",
                "240.0.0.1", "198.51.100", "198.51.100.1 198.51.100.2", ""):
        with pytest.raises(TargetError):
            check_target(bad)
    with pytest.raises(TargetError):
        check_target("198.51.100.255", prefix=24)  # its network's broadcast
    assert check_target("198.51.100.255", prefix=23) == "198.51.100.255"


def test_windows_commands_are_microsofts_with_fixed_options(monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    assert pc_tools.ping_command("198.51.100.11", 4) == [
        os.path.join(r"C:\Windows", "System32", "PING.EXE"), "-n", "4", "-w", "1000",
        "198.51.100.11"]
    assert pc_tools.tracert_command("198.51.100.11")[1:] == [
        "-d", "-h", "20", "-w", "1000", "198.51.100.11"]


def test_replies_are_counted_only_from_ttl_lines_of_the_target():
    assert pc_tools.parse_ping(PING_EN, "198.51.100.11") == (3, (3.0, 1.0, 12.0))
    assert pc_tools.parse_ping(PING_UNREACHABLE, "198.51.100.11") == (0, ())
    assert pc_tools.parse_ping(PING_DE, "198.51.100.11")[0] == 2  # same tokens in German


def test_hops_are_read_from_tokens_that_do_not_depend_on_the_language():
    hops = pc_tools.parse_tracert(TRACE)
    assert [(h.n, h.address, h.timed_out) for h in hops] == [
        (1, "198.51.100.1", False), (2, "203.0.113.9", False), (3, None, True),
        (4, "198.51.100.11", False)]
    assert hops[0].rtt_ms == (1.0, 1.0, 1.0) and hops[1].rtt_ms == (None, 2.0, 1.0)


def test_shared_addresses_give_candidates_not_a_guess():
    hops = [Hop(1, "192.168.1.1"), Hop(2, "198.51.100.1"), Hop(3, None, timed_out=True)]
    known = [KnownAddress("sw-a", "192.168.1.1", "bench address"),
             KnownAddress("sw-b", "192.168.1.1", "bench address"),
             KnownAddress("fw", "198.51.100.1", 'interface "port3"')]
    match_hops(hops, known)
    assert hops[0].device_id is None and hops[0].candidates == ["sw-a", "sw-b"]
    assert (hops[1].device_id, hops[1].interface) == ("fw", 'interface "port3"')


def test_outside_windows_the_programs_are_refused(monkeypatch):
    monkeypatch.setattr(pc_tools.os, "name", "posix")
    with pytest.raises(ConflictError, match="Windows"):
        pc_tools._run(["PING.EXE"], 5)


def test_a_program_that_runs_too_long_is_stopped(monkeypatch):
    monkeypatch.setattr(pc_tools.os, "name", "nt")

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5, output=b"Tracing route to 198.51.100.11")

    monkeypatch.setattr(pc_tools.subprocess, "run", slow)
    out = pc_tools._run(["TRACERT.EXE"], 5)
    assert out.startswith("Tracing route") and "stopped waiting after 5 s" in out


@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, factory = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def practice(c, real_switch=False):
    pid = c.post("/api/projects", json={"name": "Practice B007"}).json()["id"]
    fw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-fw", "manufacturer": "Fortinet", "category": "firewall",
        "driver_id": "mock.fortinet.fortios", "management_address": "192.168.1.99"}).json()["id"]
    sw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-sw-a", "manufacturer": "Aruba", "category": "switch",
        "environment": "lab" if real_switch else "simulated",
        "driver_id": "ssh.aruba.aos_switch" if real_switch else "mock.aruba.aos_switch",
        "management_address": "192.168.1.1"}).json()["id"]
    c.put(f"/api/devices/{fw}/network-address", json={"address": "198.51.100.1"})
    c.put(f"/api/devices/{sw}/network-address", json={"address": "198.51.100.11"})
    return pid, fw, sw


def test_a_simulated_target_starts_no_program(client):
    pid, fw, sw = practice(client)
    out = client.post(f"/api/projects/{pid}/troubleshoot/ping",
                      json={"target": "198.51.100.11"}).json()
    assert out["simulated"] and out["note"] == "Simulated: nothing was sent."
    assert out["received"] == 4 and out["target_device"] == sw
    logged = [a for a in client.get("/api/audit").json() if a["action"] == "troubleshoot.ping"]
    assert logged and logged[0]["details"]["simulated"] is True


def test_in_the_network_a_simulated_trace_goes_through_the_bfw(client):
    pid, fw, sw = practice(client)
    assert client.put(f"/api/projects/{pid}/reached-via",
                      json={"via": "network"}).status_code == 200
    out = client.post(f"/api/projects/{pid}/troubleshoot/traceroute",
                      json={"target": "198.51.100.11"}).json()
    assert [(h["address"], h["device_id"]) for h in out["hops"]] == [
        ("198.51.100.1", fw), ("198.51.100.11", sw)]
    logged = [a for a in client.get("/api/audit").json()
              if a["action"] == "troubleshoot.traceroute"]
    assert logged[0]["details"]["hops"][0]["device"] == fw  # kept for the packet path


def test_a_real_target_runs_windows_ping_and_tracert(client, monkeypatch):
    pid, fw, sw = practice(client, real_switch=True)
    started: list[list[str]] = []

    def run(argv, timeout):
        started.append(argv)
        return PING_EN if "PING" in argv[0] else TRACE

    monkeypatch.setattr(pc_tools, "runner", run)
    out = client.post(f"/api/projects/{pid}/troubleshoot/ping",
                      json={"target": "198.51.100.11", "count": 4}).json()
    assert (out["sent"], out["received"], out["simulated"]) == (4, 3, False)
    assert out["raw"].startswith("\nPinging") and started[-1][-1] == "198.51.100.11"
    trace = client.post(f"/api/projects/{pid}/troubleshoot/traceroute",
                        json={"target": "198.51.100.11"}).json()
    assert trace["reached"] and trace["hops"][0]["device_id"] == fw
    assert trace["hops"][3]["device_id"] == sw and trace["hops"][1]["device_id"] is None


def test_requests_are_refused_for_bad_targets_and_other_sources(client):
    pid, fw, sw = practice(client)
    r = client.post(f"/api/projects/{pid}/troubleshoot/ping", json={"target": "10.0.0.0/8"})
    assert r.status_code == 409
    r = client.post(f"/api/projects/{pid}/troubleshoot/ping",
                    json={"source": "not-a-device", "target": "198.51.100.11"})
    assert r.status_code == 404


def test_one_traceroute_at_a_time_from_one_place(client):
    pid, fw, sw = practice(client)
    lock = ts._lock("pc")
    assert lock.acquire(blocking=False)
    try:
        r = client.post(f"/api/projects/{pid}/troubleshoot/traceroute",
                        json={"target": "198.51.100.11"})
        assert r.status_code == 409 and "running" in r.json()["error"]
    finally:
        lock.release()


def test_check_all_covers_only_the_systems_addresses(client, monkeypatch):
    pid, fw, sw = practice(client, real_switch=True)
    client.put(f"/api/projects/{pid}/reached-via", json={"via": "network"})
    pinged: list[str] = []
    monkeypatch.setattr(pc_tools, "runner", lambda argv, timeout: pinged.append(argv[-1])
                        or PING_EN.replace("Request timed out.\n", ""))
    monkeypatch.setattr(ssh_base, "tcp_port_open", lambda host, port, timeout=3.0: True)
    rows = {r["device_id"]: r for r in client.post(
        f"/api/projects/{pid}/troubleshoot/check-all", json={}).json()}
    assert rows[fw]["state"] == "simulated"
    assert rows[sw]["state"] == "answers" and rows[sw]["address"] == "198.51.100.11"
    assert pinged == ["198.51.100.11"]  # only the real device's address in use
    assert any(a["action"] == "troubleshoot.check_all" for a in client.get("/api/audit").json())
