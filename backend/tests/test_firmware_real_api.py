"""Firmware on a real-device driver through the API: safety switches and a full run.

The device is a fake 2930F (synthetic wording) that downloads from UNDM's TFTP
server with an independent client. Proves the workflow and its gates, not hardware.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import keyring
import pytest
from api_helpers import make_client
from fake_aos_switch import FakeArubaSwitch, fake_image
from fake_netmiko import Scenario, factory_for
from memory_keyring import MemoryKeyring

from undm.drivers.ssh.base import SshCliDriver
from undm.drivers.ssh.platforms import ArubaOSSwitchSsh

TARGET = "WC.16.10.0025"
IMAGE = fake_image(TARGET)
ALICE, BOB = {"X-UNDM-Actor": "alice"}, {"X-UNDM-Actor": "bob"}


def window():
    now = datetime.now(UTC)
    return {"window_start": (now - timedelta(minutes=5)).isoformat(),
            "window_end": (now + timedelta(hours=1)).isoformat()}


class Bench:
    def __init__(self, tmp_path, monkeypatch, **settings):
        previous = keyring.get_keyring()
        keyring.set_keyring(MemoryKeyring())
        self._restore = lambda: keyring.set_keyring(previous)
        self.client, _ = make_client(
            data_dir=str(tmp_path), tftp_host="127.0.0.1", tftp_port=0,
            firmware_reboot_wait_seconds=0, firmware_reboot_wait_attempts=4, **settings)
        hub = self.client.app.state.transfer_hub
        self.hub = hub
        self.switch = FakeArubaSwitch(tftp_port=lambda: hub.port)
        self.scenario = Scenario(prompt="lab-2930f#", device=self.switch)
        monkeypatch.setattr(SshCliDriver, "connection_factory",
                            staticmethod(factory_for(self.scenario)))
        monkeypatch.setattr(SshCliDriver, "poll_interval", 0.01)
        monkeypatch.setattr(ArubaOSSwitchSsh, "question_timeout", 0.3)
        monkeypatch.setattr(ArubaOSSwitchSsh, "reboot_quiet_timeout", 0.3)

    def setup(self):
        c = self.client
        self.pid = c.post("/api/projects", json={"name": "Bench"}).json()["id"]
        ref = c.post(f"/api/projects/{self.pid}/credential-refs", json={"name": "c"}).json()
        c.put(f"/api/credential-refs/{ref['id']}/secret",
              json={"username": "manager", "password": ""})
        self.did = c.post(f"/api/projects/{self.pid}/devices", json={
            "name": "lab-2930f", "manufacturer": "Aruba", "category": "switch",
            "model": "2930F", "os_family": "ArubaOS-Switch",
            "driver_id": "ssh.aruba.aos_switch", "environment": "lab",
            "management_address": "127.0.0.1", "credential_ref_id": ref["id"]}).json()["id"]
        img = c.post("/api/firmware/images", data={
            "vendor": "Aruba", "platform": "aos_switch", "version": TARGET,
            "compatible_models": "2930F", "vendor_sha256": hashlib.sha256(IMAGE).hexdigest()},
            files={"file": ("WC_16_10_0025.swi", IMAGE, "application/octet-stream")}).json()
        c.post(f"/api/firmware/images/{img['id']}/approve")
        self.image_id = img["id"]

    def plan(self, dry_run=False, headers=ALICE):
        return self.client.post(
            f"/api/projects/{self.pid}/firmware-upgrades", headers=headers,
            json={"device_ids": [self.did], "image_id": self.image_id, "dry_run": dry_run})

    def approve(self, dep_id, headers=BOB):
        return self.client.post(f"/api/deployments/{dep_id}/approve", json=window(),
                                headers=headers)

    def execute(self, dep_id):
        return self.client.post(f"/api/deployments/{dep_id}/execute", headers=BOB)


@pytest.fixture
def bench(tmp_path, monkeypatch):
    made = []

    def make(**settings):
        b = Bench(tmp_path, monkeypatch, **settings)
        made.append(b)
        b.client.__enter__()
        b.setup()
        return b
    yield make
    for b in made:
        b.client.__exit__(None, None, None)
        b._restore()


def test_policy_reports_the_firmware_switch(bench):
    assert bench().client.get("/api/policy").json()["enable_real_device_firmware"] is False


def test_real_firmware_needs_both_switches_but_dry_run_is_allowed(bench):
    b = bench(enable_real_device_writes=True)  # firmware switch still off
    r = b.plan()
    assert r.status_code == 403 and "UNDM_ENABLE_REAL_DEVICE_FIRMWARE" in r.json()["error"]
    dry = b.plan(dry_run=True)
    assert dry.status_code == 201, dry.json()
    t = dry.json()["targets"][0]
    assert (t["from_version"], t["to_version"]) == ("WC.16.10.0012", TARGET)
    assert not any(c.startswith(("copy", "boot")) for c in b.switch.commands)
    assert not b.hub.running


def test_firmware_switch_alone_is_not_enough(bench):
    b = bench(enable_real_device_firmware=True)  # write switch off
    r = b.plan()
    assert r.status_code == 403 and "UNDM_ENABLE_REAL_DEVICE_WRITES" in r.json()["error"]


def test_full_upgrade_of_a_fake_2930f_over_tftp(bench):
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    dep = b.plan().json()
    assert dep["state"] == "awaiting_approval", dep
    assert b.approve(dep["id"], headers=ALICE).status_code == 403  # second person by default
    assert b.approve(dep["id"]).json()["state"] == "ready"
    assert not b.hub.running  # nothing is served until the job runs
    out = b.execute(dep["id"]).json()
    assert out["state"] == "succeeded", out["events"]
    assert not b.hub.running  # and nothing afterwards
    t = out["targets"][0]
    assert t["state"] == "verified" and t["backup_version_id"]
    assert (t["from_version"], t["to_version"]) == ("WC.16.10.0012", TARGET)
    assert b.switch.running == TARGET and b.switch.restarts == 1
    assert b.switch.keys == ["y", "y"]  # copy confirmation, restart confirmation
    messages = " | ".join(e["message"] for e in out["events"])
    assert "bytes transferred" in messages and "device reachable again" in messages
    device = b.client.get(f"/api/devices/{b.did}").json()
    assert device["observed_facts"]["os_version"] == TARGET
    audit = b.client.get("/api/audit?limit=50").json()
    start = next(a for a in audit if a["action"] == "deployment.execute.start")
    assert start["details"]["tftp"] is True


def test_single_technician_bench_mode_is_an_explicit_setting(bench):
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True,
              firmware_require_separate_approver=False)
    dep = b.plan().json()
    assert b.approve(dep["id"], headers=ALICE).json()["state"] == "ready"


def test_unanswered_question_stops_the_job_and_shows_the_switch_output(bench):
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    b.switch.copy_question = "Erase ALL images and reformat flash? Type CONFIRM: "
    dep = b.plan().json()
    b.approve(dep["id"])
    out = b.execute(dep["id"]).json()
    assert out["state"] == "rolled_back", out["events"]  # still on the original version
    assert b.switch.keys == [] and b.switch.restarts == 0
    messages = " | ".join(e["message"] for e in out["events"])
    assert "stage failed" in messages and "Type CONFIRM" in messages
    assert "still running the original version WC.16.10.0012" in out["targets"][0]["message"]
    assert not b.hub.running


def test_switch_that_does_not_restart_is_not_reported_as_upgraded(bench):
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    b.switch.reboot_mode = "refuse"
    dep = b.plan().json()
    b.approve(dep["id"])
    out = b.execute(dep["id"]).json()
    assert out["state"] == "rolled_back", out["events"]
    assert b.switch.primary == TARGET and b.switch.running == "WC.16.10.0012"
    assert "may start at the next restart" in out["targets"][0]["message"]


def test_tftp_port_in_use_is_explained_before_anything_is_touched(bench, monkeypatch):
    import socket
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    taken = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    taken.bind(("127.0.0.1", 0))
    try:
        b.hub._port = taken.getsockname()[1]
        dep = b.plan().json()
        b.approve(dep["id"])
        r = b.execute(dep["id"])
        assert r.status_code == 409 and "Cannot start the TFTP server" in r.json()["error"]
        assert not any(c.startswith("copy") for c in b.switch.commands)
        state = b.client.get(f"/api/deployments/{dep['id']}").json()["state"]
        assert state == "ready"  # can be run again once the port is free
    finally:
        taken.close()
