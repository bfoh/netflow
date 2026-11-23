"""Stopping a running deployment (Stop button), and runs that continue in the background.

A stop takes effect at the next safe point. The outcome must say honestly whether a device
may have been changed, and no further device action is taken after a stop.
"""

import time
from datetime import UTC, datetime, timedelta

from api_helpers import SWITCH, SWITCH_INTENT, make_client

from undm.domain.lifecycle import DeploymentState as S
from undm.drivers.base import DeviceTarget, FirmwareImageRef
from undm.drivers.mock.lab import SimulatedDevice, default_lab
from undm.drivers.registry import default_registry
from undm.orchestration.deployment import (
    Deployment,
    DeploymentOrchestrator,
    DeploymentTarget,
)
from undm.orchestration.deployment import TargetState as T
from undm.orchestration.firmware import FirmwareOrchestrator

REG = default_registry()
IMAGE = FirmwareImageRef("WC.16.10.0025", "WC_16_10_0025.swi", "c" * 64, 1, "/tmp/none")


def sw(addr, **kw):
    return default_lab().add(SimulatedDevice(address=addr, vendor="Aruba", model="SIM-2930F",
                                             os_version="WC.16.09.0004",
                                             serial_number="S" + addr, **kw))


def fw_plan(*addrs):
    now = datetime.now(UTC)
    targets = [DeploymentTarget(a, a, REG.create("mock.aruba.aos_switch", DeviceTarget(a, a)), "")
               for a in addrs]
    return Deployment("stop-1", targets, created_by="alice", firmware=IMAGE,
                      window_start=now - timedelta(minutes=1), window_end=now + timedelta(hours=1))


def stop_when(dep, needle, by="bob"):
    """An event sink that presses Stop when an event containing ``needle`` appears."""
    def sink(_dep, ev):
        if needle in ev.message:
            dep.stop.request(by)
    return sink


def run_fw(dep, sink=None):
    o = FirmwareOrchestrator(sink, reboot_wait_attempts=3, reboot_wait_delay_s=0)
    assert o.prepare(dep)
    o.approve(dep, "carol")
    return o.execute(dep)


def test_stop_before_the_run_begins_changes_nothing():
    d = sw("10.0.9.1")
    dep = fw_plan("10.0.9.1")
    dep.stop.request("bob")
    assert run_fw(dep) is S.FAILED
    assert dep.events[-1].message == "stopped by bob; no device was changed"
    assert dep.targets[0].state is T.SKIPPED
    assert d.os_version == "WC.16.09.0004"


def test_stop_while_waiting_for_a_restart_asks_for_a_check_and_does_nothing_more():
    d = sw("10.0.9.2", unreachable_after_reboot=True)
    dep = fw_plan("10.0.9.2")
    assert run_fw(dep, stop_when(dep, "reboot:")) is S.RECOVERY_REQUIRED
    t = dep.targets[0]
    assert t.state is T.MANUAL_RECOVERY_REQUIRED
    assert "stopped by bob while deploying" in t.message and "check it" in t.message
    messages = [e.message for e in dep.events]
    assert not any("rolled back" in m or m.startswith("recover") for m in messages)
    assert d.previous_os_version == "WC.16.09.0004"  # no automatic rollback was attempted
    assert messages[-1].startswith("stopped by bob; 1 device(s) may be mid-change")


def test_stop_between_devices_leaves_the_rest_untouched():
    a, b = sw("10.0.9.3"), sw("10.0.9.4")
    dep = fw_plan("10.0.9.3", "10.0.9.4")
    assert run_fw(dep, stop_when(dep, "device reachable again")) is S.RECOVERY_REQUIRED
    assert a.os_version == "WC.16.10.0025" and b.os_version == "WC.16.09.0004"
    assert [t.state for t in dep.targets] == [T.MANUAL_RECOVERY_REQUIRED, T.SKIPPED]


def test_stopped_configuration_run_is_not_rolled_back_automatically():
    sw("10.0.9.5")
    t = DeploymentTarget("s", "s", REG.create("mock.aruba.aos_switch",
                                               DeviceTarget("s", "10.0.9.5")), "hostname new\n")
    dep = Deployment("stop-2", [t], created_by="alice")
    o = DeploymentOrchestrator(stop_when(dep, "backing_up -> deploying"))
    assert o.prepare(dep)
    o.approve(dep, "carol")
    assert o.execute(dep) is S.FAILED  # stopped before the first device was touched
    assert dep.events[-1].message == "stopped by bob; no device was changed"


def test_ssh_wait_for_a_device_answer_ends_on_stop(monkeypatch):
    from fake_aos_switch import FakeArubaSwitch
    from fake_netmiko import Scenario, factory_for

    from undm.drivers.base import Credentials
    from undm.drivers.ssh.base import SshCliDriver
    from undm.drivers.ssh.platforms import ArubaOSSwitchSsh

    switch = FakeArubaSwitch(tftp_port=0)
    switch.copy_question = "Type CONFIRM to continue: "  # unknown: never answered
    sc = Scenario(prompt="lab-2930f#", device=switch)
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory_for(sc)))
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.01)
    driver = ArubaOSSwitchSsh(DeviceTarget("d", "127.0.0.1"), Credentials("manager", ""))
    assert driver.connect().ok
    driver.should_stop = lambda: True
    began = time.monotonic()
    talk = driver._dialogue("copy tftp flash 127.0.0.1 x.swi primary", [],
                            timeout=60, idle_timeout=60)
    assert talk.ended == "stopped" and time.monotonic() - began < 5
    assert switch.keys == []


# -- API ------------------------------------------------------------------------------------
def _client(tmp_path):
    return make_client(database_url=f"sqlite:///{tmp_path}/undm.db")


def _plan(c):
    pid = c.post("/api/projects", json={"name": "P"}).json()["id"]
    did = c.post(f"/api/projects/{pid}/devices", json=SWITCH).json()["id"]
    c.put(f"/api/devices/{did}/intent", json=SWITCH_INTENT)
    assert c.post(f"/api/devices/{did}/configs/generate").json()["ok"]
    dep = c.post(f"/api/projects/{pid}/deployments", json={"device_ids": [did]},
                 headers={"X-UNDM-Actor": "alice"}).json()
    assert c.post(f"/api/deployments/{dep['id']}/approve",
                  headers={"X-UNDM-Actor": "carol"}).status_code == 200
    return dep["id"], did


def _until_finished(c, dep_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        dep = c.get(f"/api/deployments/{dep_id}").json()
        if dep["state"] in ("succeeded", "failed", "rolled_back", "recovery_required"):
            return dep
        time.sleep(0.05)
    raise AssertionError("deployment did not finish")


def test_background_run_returns_at_once_and_finishes_on_the_server(tmp_path):
    client, _ = _client(tmp_path)
    with client as c:
        dep_id, _ = _plan(c)
        r = c.post(f"/api/deployments/{dep_id}/execute?background=true")
        assert r.status_code == 200 and r.json()["state"] == "ready"
        assert c.post(f"/api/deployments/{dep_id}/execute?background=true").status_code \
            in (409,)  # already running, or no longer ready
        assert _until_finished(c, dep_id)["state"] == "succeeded"


def test_stop_without_a_run_resolves_a_plan_left_running(tmp_path):
    from undm.db.models import DeploymentRecord, Device

    client, factory = _client(tmp_path)
    with client as c:
        dep_id, did = _plan(c)
        with factory() as s:  # as left by a run that no longer exists in this process
            s.get(DeploymentRecord, dep_id).state = "deploying"
            s.get(Device, did).locked_by_deployment_id = dep_id
            s.commit()
        out = c.post(f"/api/deployments/{dep_id}/stop", headers={"X-UNDM-Actor": "bob"}).json()
        assert out["state"] == "recovery_required"
        assert "stopped by bob: no run was active" in out["events"][-1]["message"]
        device = c.get(f"/api/devices/{did}").json()
        assert device["locked_by_deployment_id"] is None
        assert device["deployment_status"] == "unknown"
        assert c.post(f"/api/deployments/{dep_id}/stop").status_code == 409  # finished


def test_stop_is_refused_for_a_plan_that_is_not_running(tmp_path):
    client, _ = _client(tmp_path)
    with client as c:
        dep_id, _ = _plan(c)
        r = c.post(f"/api/deployments/{dep_id}/stop")
        assert r.status_code == 409 and "not running" in r.json()["error"]
