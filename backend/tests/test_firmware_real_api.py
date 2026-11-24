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
        options = {"firmware_reboot_wait_seconds": 0, "firmware_reboot_wait_attempts": 4,
                   **settings}
        self.client, _ = make_client(
            data_dir=str(tmp_path), tftp_host="127.0.0.1", tftp_port=0, **options)
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
    assert r.status_code == 403 and "Firmware changes are off" in r.json()["error"]
    dry = b.plan(dry_run=True)
    assert dry.status_code == 201, dry.json()
    t = dry.json()["targets"][0]
    assert (t["from_version"], t["to_version"]) == ("WC.16.10.0012", TARGET)
    assert not any(c.startswith(("copy", "boot")) for c in b.switch.commands)
    assert not b.hub.running


def test_firmware_switch_alone_is_not_enough(bench):
    b = bench(enable_real_device_firmware=True)  # write switch off
    r = b.plan()
    assert r.status_code == 403 and "Real-device changes are off" in r.json()["error"]


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


def test_approved_older_version_needs_the_plan_option(bench):
    """New units ship with WC.16.11.0001; the project's approved version is older."""
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    b.switch.running = b.switch.primary = "WC.16.11.0001"
    refused = b.plan().json()
    assert refused["state"] == "failed"
    assert any("downgrades are refused unless the plan allows" in e["message"]
               for e in refused["events"])
    dep = b.client.post(
        f"/api/projects/{b.pid}/firmware-upgrades", headers=ALICE,
        json={"device_ids": [b.did], "image_id": b.image_id, "allow_downgrade": True}).json()
    assert dep["state"] == "awaiting_approval" and dep["allow_downgrade"] is True
    assert any("DOWNGRADE to the approved version" in e["message"] for e in dep["events"])
    b.approve(dep["id"])
    out = b.execute(dep["id"]).json()
    assert out["state"] == "succeeded", [e["message"] for e in out["events"]]
    assert b.switch.running == TARGET
    audit = b.client.get("/api/audit?limit=50").json()
    created = next(a for a in audit if a["action"] == "firmware_deployment.create"
                   and a["details"]["allow_downgrade"])
    assert created["details"]["version"] == TARGET


def test_plan_can_also_write_the_secondary_flash(bench):
    """Project standard (2026-11-23): the approved release in both image slots. The bench
    unit already runs it from primary after the downgrade; secondary still holds the
    shipped, newer release."""
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    b.switch.running = b.switch.primary = TARGET
    b.switch.secondary = "WC.16.11.0001"
    dep = b.client.post(
        f"/api/projects/{b.pid}/firmware-upgrades", headers=ALICE,
        json={"device_ids": [b.did], "image_id": b.image_id, "allow_downgrade": True,
              "also_secondary": True}).json()
    assert dep["state"] == "awaiting_approval" and dep["also_secondary"] is True, dep["events"]
    assert any("only the secondary flash will be written" in e["message"]
               for e in dep["events"])
    b.approve(dep["id"])
    out = b.execute(dep["id"]).json()
    assert out["state"] == "succeeded", [e["message"] for e in out["events"]]
    assert (b.switch.primary, b.switch.secondary, b.switch.running) == (TARGET,) * 3
    assert b.switch.restarts == 0  # the running image was not touched
    assert "copy tftp flash 127.0.0.1 WC_16_10_0025.swi secondary" in b.switch.commands
    assert not any(c.startswith("copy tftp flash") and c.endswith("primary")
                   for c in b.switch.commands)
    messages = [e["message"] for e in out["events"]]
    assert any(m.startswith("secondary: WC.16.10.0025 is in the secondary flash") for m in messages)
    assert any(m == f"running {TARGET}, secondary {TARGET}" for m in messages)
    audit = b.client.get("/api/audit?limit=50").json()
    assert any(a["action"] == "firmware_deployment.create" and a["details"]["also_secondary"]
               for a in audit)


def test_full_upgrade_with_secondary_restarts_before_writing_secondary(bench):
    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True)
    dep = b.client.post(
        f"/api/projects/{b.pid}/firmware-upgrades", headers=ALICE,
        json={"device_ids": [b.did], "image_id": b.image_id, "also_secondary": True}).json()
    b.approve(dep["id"])
    out = b.execute(dep["id"]).json()
    assert out["state"] == "succeeded", [e["message"] for e in out["events"]]
    copies = [c for c in b.switch.commands if c.startswith(("copy tftp flash", "boot"))]
    assert copies == ["copy tftp flash 127.0.0.1 WC_16_10_0025.swi primary",
                      "boot system flash primary",
                      "copy tftp flash 127.0.0.1 WC_16_10_0025.swi secondary"]
    assert (b.switch.primary, b.switch.secondary, b.switch.running) == (TARGET,) * 3


def test_stop_ends_a_background_run_waiting_for_a_switch_that_does_not_return(bench, tmp_path):
    """Bench 2026-11-23: after a restart the switch answered on another port, so UNDM kept
    waiting. The run continues on the server; Stop ends the wait and asks for a check."""
    import time

    b = bench(enable_real_device_writes=True, enable_real_device_firmware=True,
              database_url=f"sqlite:///{tmp_path}/bench.db",
              firmware_reboot_wait_seconds=0.2, firmware_reboot_wait_attempts=500)
    b.switch.down_for_connects = 10_000  # never answers again at this address
    dep = b.plan().json()
    b.approve(dep["id"])
    r = b.client.post(f"/api/deployments/{dep['id']}/execute?background=true", headers=BOB)
    assert r.status_code == 200 and r.json()["state"] == "ready"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        events = b.client.get(f"/api/deployments/{dep['id']}").json()["events"]
        if any(e["message"].startswith("waiting for the device to answer at 127.0.0.1")
               for e in events):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("the run never reached the restart wait")
    stopped = b.client.post(f"/api/deployments/{dep['id']}/stop", headers=ALICE)
    assert stopped.status_code == 200
    while time.monotonic() < deadline:
        out = b.client.get(f"/api/deployments/{dep['id']}").json()
        if out["state"] not in ("deploying", "verifying", "recovering"):
            break
        time.sleep(0.05)
    assert out["state"] == "recovery_required", [e["message"] for e in out["events"]]
    assert out["targets"][0]["state"] == "manual_recovery_required"
    assert "stopped by alice while deploying" in out["targets"][0]["message"]
    while b.hub.running and time.monotonic() < deadline:  # closes as the run ends
        time.sleep(0.05)
    assert not b.hub.running  # the TFTP session ended with the run
    device = b.client.get(f"/api/devices/{b.did}").json()
    assert device["locked_by_deployment_id"] is None
    audit = b.client.get("/api/audit?limit=50").json()
    assert any(a["action"] == "deployment.stop_requested" and a["actor"] == "alice"
               for a in audit)


# --- Settings → Safety (D-082) -------------------------------------------------------------

def test_safety_switches_start_off_and_change_from_settings(bench):
    b = bench()
    pol = b.client.get("/api/policy").json()
    assert (pol["enable_real_device_writes"], pol["enable_real_device_firmware"]) == (False, False)
    assert pol["locked"] == [] and pol["firmware_require_separate_approver"] is True
    assert b.plan().status_code == 403  # off: the plan is refused
    r = b.client.put("/api/policy", headers=BOB, json={
        "enable_real_device_writes": True, "enable_real_device_firmware": True})
    assert r.status_code == 200, r.json()
    assert r.json()["enable_real_device_writes"] and r.json()["enable_real_device_firmware"]
    assert b.plan().json()["state"] == "awaiting_approval"  # in force at once, no restart
    audit = [a for a in b.client.get("/api/audit").json() if a["action"] == "policy.change"]
    seen = {(a["actor"], a["target_id"], a["details"]["before"], a["details"]["after"])
            for a in audit}
    assert seen == {("bob", "enable_real_device_writes", False, True),
                    ("bob", "enable_real_device_firmware", False, True)}


def test_safety_switches_are_kept_in_the_data_folder(bench, tmp_path):
    b = bench()
    b.client.put("/api/policy", json={"firmware_require_separate_approver": False})
    stored = (tmp_path / "settings.json").read_text()
    assert '"firmware_require_separate_approver": false' in stored
    again, _ = make_client(data_dir=str(tmp_path))  # a restart of the same copy
    assert again.get("/api/policy").json()["firmware_require_separate_approver"] is False


def test_an_unchanged_switch_is_not_audited(bench):
    b = bench()
    assert b.client.put("/api/policy", json={"enable_real_device_writes": False}).status_code == 200
    assert not [a for a in b.client.get("/api/audit").json() if a["action"] == "policy.change"]


def test_a_switch_from_the_start_up_settings_is_locked(bench, tmp_path):
    b = bench(enable_real_device_writes=True)
    pol = b.client.get("/api/policy").json()
    assert pol["locked"] == ["enable_real_device_writes"] and pol["enable_real_device_writes"]
    r = b.client.put("/api/policy", json={"enable_real_device_writes": False})
    assert r.status_code == 409 and "start-up settings" in r.json()["error"]
    assert not (tmp_path / "settings.json").exists()


def test_production_switches_cannot_be_changed_from_settings(bench):
    r = bench().client.put("/api/policy", json={"allow_production_deployments": True})
    assert r.status_code == 422


def test_turning_firmware_off_stops_an_approved_plan_from_running(bench):
    b = bench()
    b.client.put("/api/policy", json={"enable_real_device_writes": True,
                                      "enable_real_device_firmware": True,
                                      "firmware_require_separate_approver": False})
    dep = b.plan().json()
    assert b.approve(dep["id"]).json()["state"] == "ready"
    b.client.put("/api/policy", json={"enable_real_device_firmware": False})
    r = b.client.post(f"/api/deployments/{dep['id']}/execute")
    assert r.status_code == 403 and "Firmware changes are off" in r.json()["error"]
    assert not any(c.startswith(("copy", "boot")) for c in b.switch.commands)


def test_a_damaged_settings_file_means_all_switches_off(bench, tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    pol = bench().client.get("/api/policy").json()
    assert (pol["enable_real_device_writes"], pol["enable_real_device_firmware"]) == (False, False)
