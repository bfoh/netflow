"""Ping and traceroute from a device (D-128). The commands are the vendors' documented ones;
the answers here are SYNTHETIC (no device output has been seen yet, Q-59), so they test the
drivers' logic, not the parsers' accuracy on hardware. No device is contacted."""

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.domain.operations import DeviceOperation
from undm.drivers.base import Credentials, DeviceTarget, OperationResult, ResultStatus
from undm.drivers.blackbox.lig1014a_ssh import BlackBoxLig1014aSsh
from undm.drivers.fortinet.fortios_ssh import FortiOSSsh
from undm.drivers.mock.drivers import MockFortiGateDriver
from undm.drivers.nokia.sar_ssh import NokiaSarSsh
from undm.drivers.ssh.base import Dialogue
from undm.drivers.ssh.platforms import ArubaOSSwitchSsh

TARGET = "198.51.100.11"
BSD_PING = (f"PING {TARGET} ({TARGET}): 56 data bytes\n"
            f"64 bytes from {TARGET}: icmp_seq=0 ttl=64 time=0.4 ms\n"
            f"64 bytes from {TARGET}: icmp_seq=1 ttl=64 time=0.3 ms\n"
            f"--- {TARGET} ping statistics ---\n"
            "5 packets transmitted, 2 packets received, 60% packet loss\nlab-fw # ")
TRACE = (f"traceroute to {TARGET} ({TARGET}), 32 hops max, 3 probe packets per hop\n"
         " 1  198.51.100.1  0.4 ms  0.3 ms  0.3 ms\n 2  *  *  *\n"
         f" 3  {TARGET}  1.2 ms  1.1 ms  1.0 ms\nlab-fw # ")


def ssh(cls, status=""):
    d = cls(DeviceTarget("d1", "198.51.100.1"), Credentials("admin", "Example-Only-1"))
    d._conn = object()  # connected (the fake answers below)
    sent: list[tuple[str, list]] = []

    def dialogue(command, answers, **kwargs):
        sent.append((command, list(answers)))
        if command.startswith(("execute ping", "ping")):
            return Dialogue(BSD_PING, [], "prompt")
        if command.startswith(("execute traceroute", "traceroute")):
            return Dialogue(TRACE, [], "prompt")
        return Dialogue(f"{command}\nlab-fw (root) # ", [], "prompt")

    d._dialogue = dialogue
    d._status = lambda: status
    return d, sent


def test_fortios_pings_inside_the_vdom_of_the_target_on_a_multi_vdom_unit():
    d, sent = ssh(FortiOSSsh, "Virtual domain configuration: multiple\n")
    r = d.ping(TARGET, 4, {"vdom": "root"})
    assert r.ok and (r.data["sent"], r.data["received"]) == (5, 2)
    assert r.data["rtt_ms"] == [0.4, 0.3]
    assert [c for c, _ in sent] == ["config vdom", "edit root", f"execute ping {TARGET}", "end"]
    assert all(answers == [] for _, answers in sent)  # no question is ever answered
    d, sent = ssh(FortiOSSsh, "Virtual domain configuration: multiple\n")
    d.ping(TARGET, 4, {"vdom": "root; execute reboot"})
    assert [c for c, _ in sent][1] == "edit root"  # an odd VDOM name is not sent


def test_fortios_without_vdoms_runs_the_command_alone_and_traces():
    d, sent = ssh(FortiOSSsh, "Virtual domain configuration: disable\n")
    assert d.ping(TARGET).ok and [c for c, _ in sent] == [f"execute ping {TARGET}"]
    r = d.traceroute(TARGET)
    assert r.ok and [(h["n"], h["address"]) for h in r.data["hops"]] == [
        (1, "198.51.100.1"), (2, None), (3, TARGET)]
    assert r.data["hops"][1]["rtt_ms"] == [None, None, None]


def test_the_2930f_uses_repetitions_and_traceroute():
    d, sent = ssh(ArubaOSSwitchSsh)
    assert d.ping(TARGET, 3).ok and sent[-1][0] == f"ping {TARGET} repetitions 3"
    assert d.traceroute(TARGET).ok and sent[-1][0] == f"traceroute {TARGET}"


def test_an_answer_that_cannot_be_read_is_none_and_kept():
    d, _ = ssh(ArubaOSSwitchSsh)
    d._dialogue = lambda command, answers, **kw: Dialogue("something new\nlab-sw# ", [],
                                                          "prompt")
    r = d.ping(TARGET, 2)
    assert r.ok and r.data["received"] is None and "something new" in r.data["raw"]


def test_a_question_ends_the_ping_unanswered():
    d, _ = ssh(FortiOSSsh, "")
    d._dialogue = lambda command, answers, **kw: Dialogue("Do you want to continue? (y/n)",
                                                          [], "timeout", "no output for 30 s")
    r = d.ping(TARGET)
    assert r.status is ResultStatus.FAILED and "did not end at the prompt" in r.message


def test_unsupported_platforms_say_so_and_never_raise():
    bb = BlackBoxLig1014aSsh(DeviceTarget("b", "192.0.2.1"))
    assert bb.ping(TARGET).status is ResultStatus.UNSUPPORTED
    assert bb.traceroute(TARGET).status is ResultStatus.UNSUPPORTED
    modem = NokiaSarSsh(DeviceTarget("m", "198.51.100.31"))
    assert modem.traceroute(TARGET).status is ResultStatus.UNSUPPORTED  # not confirmed


def test_the_modem_pings_with_count(monkeypatch):
    from test_sar_ssh import FakeChannel

    answers = {"environment no more": "", f"ping {TARGET} count 2":
               f"PING {TARGET} 56 data bytes\r\n64 bytes from {TARGET}: icmp_seq=1 ttl=64 "
               "time=1.2ms.\r\n2 packets transmitted, 2 packets received, 0.00% packet loss"}
    holder = {}

    def factory(**kwargs):
        holder["conn"] = FakeChannel(answers=answers)
        return holder["conn"]

    monkeypatch.setattr(NokiaSarSsh, "connection_factory", staticmethod(factory))
    monkeypatch.setattr(NokiaSarSsh, "wake_timeout", 0.5)
    monkeypatch.setattr(NokiaSarSsh, "settle_time", 0.0)
    d = NokiaSarSsh(DeviceTarget("m", "198.51.100.31"), Credentials("admin", "Example-Only-9"))
    assert d.connect().ok
    r = d.ping(TARGET, 2)
    assert r.ok and (r.data["sent"], r.data["received"]) == (2, 2)
    assert holder["conn"].sent[-1] == f"ping {TARGET} count 2"


@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def system(c, *, real_fw=False):
    pid = c.post("/api/projects", json={"name": "Practice B009"}).json()["id"]
    ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
    c.put(f"/api/credential-refs/{ref['id']}/secret",
          json={"username": "admin", "password": "Example-Only-1"})
    fw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-fw", "manufacturer": "Fortinet", "category": "firewall",
        "environment": "lab" if real_fw else "simulated", "credential_ref_id": ref["id"],
        "driver_id": "ssh.fortinet.fortios" if real_fw else "mock.fortinet.fortios",
        "management_address": "192.168.1.99"}).json()["id"]
    sw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-sw-a", "manufacturer": "Aruba", "category": "switch",
        "driver_id": "mock.aruba.aos_switch", "management_address": "192.168.1.1"}).json()["id"]
    for did, address in ((fw, "198.51.100.1"), (sw, TARGET)):
        c.put(f"/api/devices/{did}/network-address", json={"address": address})
    assert c.put(f"/api/projects/{pid}/reached-via", json={"via": "network"}).status_code == 200
    return pid, fw, sw


def test_from_a_production_device_it_needs_the_start_up_setting(client, monkeypatch):
    pid, fw, sw = system(client, real_fw=True)
    r = client.post(f"/api/projects/{pid}/troubleshoot/ping",
                    json={"source": fw, "target": "203.0.113.5"})
    assert r.status_code == 403 and "UNDM_ALLOW_PRODUCTION_READ_ONLY" in r.json()["error"]


def test_from_the_bfw_with_the_setting_on(tmp_path, monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    calls: list[tuple] = []

    def fake_connect(self):
        calls.append(("connect", self.target.management_address))
        return OperationResult.success(DeviceOperation.CHECK_REACHABILITY)

    def fake_ping(self, target, count=4, context=None):
        calls.append(("ping", target, dict(context or {})))
        return OperationResult.success(DeviceOperation.PING, {
            "sent": count, "received": count, "rtt_ms": [0.5] * count, "raw": "SYNTHETIC"})

    monkeypatch.setattr(FortiOSSsh, "connect", fake_connect)
    monkeypatch.setattr(FortiOSSsh, "disconnect", lambda self: calls.append(("disconnect",)))

    monkeypatch.setattr(FortiOSSsh, "ping", fake_ping)
    try:
        c, _ = make_client(data_dir=str(tmp_path), allow_production_read_only=True)
        with c:
            pid, fw, sw = system(c, real_fw=True)
            out = c.post(f"/api/projects/{pid}/troubleshoot/ping",
                         json={"source": fw, "target": "203.0.113.5", "count": 2}).json()
            assert (out["received"], out["source"]) == (2, fw)
            assert calls[0] == ("connect", "198.51.100.1")  # its network address
            rows = c.post(f"/api/projects/{pid}/troubleshoot/check-all",
                          json={"source": fw}).json()
            assert [r["device_id"] for r in rows] == [sw] and rows[0]["state"] == "answers"
            assert [x[0] for x in calls].count("connect") == 2  # one session for Check all
    finally:
        keyring.set_keyring(previous)


def test_a_simulated_bfw_answers_for_the_units_of_the_lab(client):
    pid, fw, sw = system(client)
    client.post(f"/api/devices/{sw}/operations/check_reachability")  # the unit exists now
    rows = client.post(f"/api/projects/{pid}/troubleshoot/check-all",
                       json={"source": fw}).json()
    assert rows[0]["device_id"] == sw and rows[0]["state"] == "answers"
    out = client.post(f"/api/projects/{pid}/troubleshoot/ping",
                      json={"source": fw, "target": "203.0.113.77"}).json()
    assert out["received"] == 0  # no simulated unit there
    trace = client.post(f"/api/projects/{pid}/troubleshoot/traceroute",
                        json={"source": fw, "target": TARGET}).json()
    assert trace["reached"] and trace["hops"][-1]["device_id"] == sw


def test_the_operations_endpoint_sends_ping_to_its_own_place(client):
    pid, fw, sw = system(client)
    r = client.post(f"/api/devices/{sw}/operations/ping")
    assert r.status_code == 409 and "Troubleshoot" in r.json()["error"]


def test_a_device_without_a_documented_ping_is_refused(client):
    pid = client.post("/api/projects", json={"name": "Practice B010"}).json()["id"]
    bbu = client.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-bbu", "manufacturer": "Nokia", "category": "other",
        "driver_id": "mock.nokia.flexi", "management_address": "192.168.255.1"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/troubleshoot/ping",
                    json={"source": bbu, "target": "203.0.113.5"})
    assert r.status_code == 409 and "no documented ping" in r.json()["error"]


def test_mock_drivers_declare_ping_for_the_contract():
    from undm.drivers.base import Capability

    assert Capability.PING in MockFortiGateDriver.info.capabilities
