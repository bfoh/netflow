"""Working with one device (D-098, D-099): restart through a plan, an SSH window on this PC,
reachability of a system's devices, and the device's log. Simulated devices and fakes only;
no program is started and no real device is contacted."""

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.drivers.base import Capability
from undm.drivers.ssh import base as ssh_base
from undm.services import devices as devsvc


@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, _ = make_client(data_dir=str(tmp_path), enable_real_device_writes=True)
    with c:
        yield c
    keyring.set_keyring(previous)


def system(c, driver="mock.aruba.aos_switch", environment="simulated", name="Bench"):
    pid = c.post("/api/projects", json={"name": name}).json()["id"]
    ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
    c.put(f"/api/credential-refs/{ref['id']}/secret",
          json={"username": "manager", "password": "Example-Only-Approved-1"})
    did = c.post(f"/api/projects/{pid}/devices", json={
        "name": "lab-sw-a", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": driver, "environment": environment,
        "management_address": "192.0.2.10", "credential_ref_id": ref["id"]}).json()["id"]
    return pid, did


def test_a_restart_is_a_plan_previewed_approved_and_run(client):
    pid, did = system(client)
    plan = client.post(f"/api/devices/{did}/restart-plan").json()
    assert plan["kind"] == "restart" and plan["state"] == "awaiting_approval", plan
    preview = " | ".join(e["message"] for e in plan["events"])
    assert "Changes that were not saved on it are lost" in preview
    client.post(f"/api/deployments/{plan['id']}/approve")
    done = client.post(f"/api/deployments/{plan['id']}/execute").json()
    events = " | ".join(e["message"] for e in done["events"])
    assert done["state"] == "succeeded", events
    assert "rebooted (simulated)" in events and "back after the restart" in events
    device = client.get(f"/api/devices/{did}").json()
    assert device["deployment_status"] == "never_deployed"  # a restart deploys nothing


def test_only_devices_with_a_restart_procedure(client):
    from undm.drivers.fortinet.fortios_ssh import FortiOSSsh
    from undm.drivers.ssh.platforms import ArubaOSSwitchSsh

    assert Capability.RESTART in ArubaOSSwitchSsh.info.capabilities
    assert Capability.RESTART not in FortiOSSsh.info.capabilities  # not verified yet (Q-47)
    pid = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    fw = client.post(f"/api/projects/{pid}/devices", json={
        "name": "lab-fw", "manufacturer": "Fortinet", "category": "firewall",
        "model": "FortiGate-101F", "driver_id": "ssh.fortinet.fortios", "environment": "lab",
        "management_address": "192.0.2.99"}).json()["id"]
    r = client.post(f"/api/devices/{fw}/restart-plan")
    assert r.status_code == 409 and "no verified restart procedure" in r.json()["error"]


def test_ssh_window_command_never_holds_the_password(client, monkeypatch):
    pid, did = system(client, driver="ssh.aruba.aos_switch", environment="lab")
    started: list[list[str]] = []
    monkeypatch.setattr(devsvc, "launch_window", started.append)
    from undm.api.routers import devices as router

    monkeypatch.setattr(router, "_from_this_pc", lambda request: True)
    out = client.post(f"/api/devices/{did}/open-ssh").json()
    assert started and started[0][-1] == "manager@192.0.2.10" and "-p" in started[0]
    assert "Example-Only" not in repr(started) + repr(out)
    assert any(a["action"] == "device.session_opened" for a in client.get("/api/audit").json())


def test_ssh_window_only_from_this_pc_and_never_for_a_simulated_device(client, monkeypatch):
    monkeypatch.setattr(devsvc, "launch_window", lambda argv: None)
    pid, did = system(client, driver="ssh.aruba.aos_switch", environment="lab")
    r = client.post(f"/api/devices/{did}/open-ssh")  # the test client is not this PC
    assert r.status_code == 409 and "PC that runs UNDM" in r.json()["error"]
    from undm.api.routers import devices as router

    monkeypatch.setattr(router, "_from_this_pc", lambda request: True)
    _, sim = system(client, name="Practice")
    assert client.post(f"/api/devices/{sim}/open-ssh").status_code == 409


def test_reachability_reports_each_device_without_logging_in(client, monkeypatch):
    pid, real = system(client, driver="ssh.aruba.aos_switch", environment="lab")
    client.post(f"/api/projects/{pid}/devices", json={
        "name": "lab-sim", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "mock.aruba.aos_switch", "environment": "simulated",
        "management_address": "192.0.2.11"})
    asked: list[str] = []

    def probe(host, port, timeout=3.0):
        asked.append(host)
        return False

    monkeypatch.setattr(ssh_base, "tcp_port_open", probe)
    states = {r["address"]: r["state"] for r in
              client.get(f"/api/projects/{pid}/reachability").json()}
    assert states == {"192.0.2.10": "no_answer", "192.0.2.11": "simulated"}
    assert asked == ["192.0.2.10"]


def test_device_log_lists_tests_and_plan_events_newest_first_and_masks(client):
    pid, did = system(client)
    client.post(f"/api/devices/{did}/operations/check_reachability")
    plan = client.post(f"/api/devices/{did}/restart-plan").json()
    rows = client.get(f"/api/devices/{did}/log").json()
    kinds = [r["kind"] for r in rows]
    assert "device.check_reachability" in kinds and "restart.preview" in kinds
    assert rows == sorted(rows, key=lambda r: r["time"], reverse=True)
    assert any(r["plan_id"] == plan["id"] for r in rows)
    masked = client.get(f"/api/devices/{did}/log?masked=true").json()
    assert "lab-sw-a" not in repr(masked) and all(r["actor"] == "" for r in masked)
