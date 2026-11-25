"""The FortiGate staging order through the API, against a fake FortiGate.

Order agreed with the product owner (2026-11-19): firmware 7.2.7 -> 7.6.5, then the
base file (full backup, restored), then the site file (script) with the tunnel key
from the credential store, a revision after each file. Synthetic device wording
(see fake_fortigate.py); proves the workflow, gates and record-keeping, not hardware.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import keyring
import pytest
from api_helpers import make_client
from fake_fortigate import FakeFortiGate, fake_image
from fake_netmiko import Scenario, factory_for
from memory_keyring import MemoryKeyring
from test_fortios_files import BACKUP, SCRIPT
from test_fortios_procedures import tune

from undm.drivers.ssh.base import SshCliDriver

SLOT = "vdom > root > vpn ipsec phase1-interface > example-tunnel > psksecret"
PSK = "Example-Only-Psk-77"
ADMIN_PW = "Example-Only-1"


def window():
    now = datetime.now(UTC)
    return {"window_start": (now - timedelta(minutes=5)).isoformat(),
            "window_end": (now + timedelta(hours=1)).isoformat()}


@pytest.fixture
def bench(tmp_path, monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    tune(monkeypatch)
    client, _ = make_client(
        data_dir=str(tmp_path), tftp_host="127.0.0.1", tftp_port=0,
        firmware_reboot_wait_seconds=0, firmware_reboot_wait_attempts=4,
        enable_real_device_writes=True, enable_real_device_firmware=True,
        firmware_require_separate_approver=False)
    with client:
        hub = client.app.state.transfer_hub
        fg = FakeFortiGate(tftp_port=lambda: hub.port, password=ADMIN_PW)
        monkeypatch.setattr(SshCliDriver, "connection_factory",
                            staticmethod(factory_for(Scenario(device=fg))))
        c = client
        pid = c.post("/api/projects", json={"name": "Staging"}).json()["id"]

        def credential(name, user, password):
            ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": name}).json()
            c.put(f"/api/credential-refs/{ref['id']}/secret",
                  json={"username": user, "password": password})
            return ref["id"]

        admin = credential("fw-admin", "admin", ADMIN_PW)
        psk = credential("cen-psk", "psk", PSK)
        did = c.post(f"/api/projects/{pid}/devices", json={
            "name": "lab-fw1", "manufacturer": "Fortinet", "category": "firewall",
            "model": "FortiGate-101F", "os_family": "FortiOS",
            "driver_id": "ssh.fortinet.fortios", "environment": "lab",
            "management_address": "127.0.0.1", "credential_ref_id": admin}).json()["id"]
        assert c.post(f"/api/devices/{did}/operations/get_facts").json()["status"] == "success"
        yield type("Bench", (), dict(c=c, pid=pid, did=did, fg=fg, hub=hub, psk=psk))
    keyring.set_keyring(previous)


def run(b, dep):
    assert dep.get("state") == "awaiting_approval", dep
    approved = b.c.post(f"/api/deployments/{dep['id']}/approve",
                        json=window() if dep["kind"] == "firmware" else None).json()
    assert approved["state"] == "ready", approved
    return b.c.post(f"/api/deployments/{dep['id']}/execute").json()


def messages(dep):
    return " | ".join(e["message"] for e in dep["events"])


def imported(b, name, text):
    r = b.c.post(f"/api/devices/{b.did}/configs/import", json={"filename": name, "text": text})
    assert r.status_code == 201, r.json()
    return r.json()


def plan(b, version, mode, secrets=None):
    return b.c.post(f"/api/projects/{b.pid}/deployments", json={
        "device_ids": [b.did], "apply_mode": mode, "config_versions": {b.did: version["id"]},
        **({"secrets": {b.did: secrets}} if secrets else {})})


def test_firmware_then_base_then_site_with_psk_and_revisions(bench):
    b = bench
    # 1. Firmware 7.2.7 -> 7.6.5 directly.
    data = fake_image("7.6.5")
    img = b.c.post("/api/firmware/images", data={
        "vendor": "Fortinet", "platform": "fortios", "version": "7.6.5",
        "compatible_models": "FortiGate-101F", "vendor_sha256": hashlib.sha256(data).hexdigest()},
        files={"file": ("FGT_101F-v7.6.5-FORTINET.out", data, "application/octet-stream")}).json()
    b.c.post(f"/api/firmware/images/{img['id']}/approve")
    fw = b.c.post(f"/api/projects/{b.pid}/firmware-upgrades",
                  json={"device_ids": [b.did], "image_id": img["id"]}).json()
    out = run(b, fw)
    assert out["state"] == "succeeded", messages(out)
    assert b.fg.version == "v7.6.5" and b.fg.restarts == 1 and not b.hub.running

    # 2. Base file: full backup, restored by TFTP, revision named after the file.
    base = imported(b, "base-example.conf", BACKUP)
    assert base["inspection"]["blocked_reason"] == ""
    wrong = plan(b, base, "merge")
    assert wrong.status_code == 409 and "replace mode" in wrong.json()["error"]
    out = run(b, plan(b, base, "replace").json())
    assert out["state"] == "succeeded", messages(out)
    assert b.fg.vdoms and b.fg.hostname == "lab-fw-base" and b.fg.restarts == 2
    assert "back after the restore" in messages(out) and "device reachable again" in messages(out)
    assert b.fg.revisions == ["base-example"]
    assert not b.hub.running

    # 3. Site file: script with the approved tunnel key, revision named after the file.
    site = imported(b, "site-example.cfg", SCRIPT)
    assert [s["slot_id"] for s in site["inspection"]["secret_slots"]] == [SLOT]
    dep = plan(b, site, "merge", {SLOT: b.psk}).json()
    assert dep["targets"][0]["secret_refs"] == {SLOT: b.psk}
    out = run(b, dep)
    assert out["state"] == "succeeded", messages(out)
    assert f'set psksecret "{PSK}"' in b.fg.applied  # the approved key reached the device
    assert "example-only-not-a-secret" not in " ".join(b.fg.applied)  # not the placeholder
    assert b.fg.hostname == "lab-fw-site" and b.fg.revisions == ["base-example", "site-example"]
    assert "expected, before the first block" in messages(out)
    audit = b.c.get("/api/audit?limit=200").json()
    start = [a for a in audit if a["action"] == "deployment.execute.start"]
    assert [a["details"]["tftp"] for a in start] == [False, True, True]  # newest first

    # The key never appears in anything UNDM stores or returns.
    for blob in (repr(audit), repr(b.c.get(f"/api/deployments/{dep['id']}").json()),
                 repr(b.c.get("/api/deployments").json())):
        assert PSK not in blob


def test_secret_mapping_is_checked_when_the_plan_is_made(bench):
    b = bench
    site = imported(b, "site-example.cfg", SCRIPT)
    r = plan(b, site, "merge", {"vdom > root > nothing": b.psk})
    assert r.status_code == 409 and "no secret setting" in r.json()["error"]
    bad = b.c.post(f"/api/projects/{b.pid}/credential-refs", json={"name": "bad"}).json()
    b.c.put(f"/api/credential-refs/{bad['id']}/secret",
            json={"username": "psk", "password": 'has"quote'})
    r = plan(b, site, "merge", {SLOT: bad["id"]})
    assert r.status_code == 409 and "cannot type safely" in r.json()["error"]
    assert 'has"quote' not in r.text


def test_base_file_with_another_password_ends_with_a_clear_message(bench):
    b = bench
    b.fg.vdoms = False
    b.fg.restore_sets_password = "Something-Else-9"  # the base file carries its own password
    base = imported(b, "base-example.conf", BACKUP)
    out = run(b, plan(b, base, "replace").json())
    assert out["state"] == "recovery_required", messages(out)
    assert "Authentication failed" in out["targets"][0]["message"]
    assert b.fg.revisions == []


# --- generic device staging (D-085): firmware, base, site as one plan -----------------------

def approved_image(b, version="7.6.5", approve=True):
    data = fake_image(version)
    img = b.c.post("/api/firmware/images", data={
        "vendor": "Fortinet", "platform": "fortios", "version": version,
        "compatible_models": "FortiGate-101F", "vendor_sha256": hashlib.sha256(data).hexdigest()},
        files={"file": (f"FGT_101F-v{version}-FORTINET.out", data, "application/octet-stream")}
    ).json()
    if approve:
        b.c.post(f"/api/firmware/images/{img['id']}/approve")
    return img


def test_firmware_base_and_site_as_one_device_staging_plan(bench):
    b = bench
    img = approved_image(b)
    base = imported(b, "base-example.conf", BACKUP)
    site = imported(b, "site-example.cfg", SCRIPT)
    r = b.c.post(f"/api/projects/{b.pid}/device-staging", json={"device_id": b.did, "steps": [
        {"kind": "firmware", "image_id": img["id"]},
        {"kind": "configuration", "version_id": base["id"]},  # mode from the file: replace
        {"kind": "configuration", "version_id": site["id"], "secrets": {SLOT: b.psk}}]})
    assert r.status_code == 201, r.json()
    plan_ = r.json()
    steps = plan_["steps"]
    assert [s["kind"] for s in steps] == ["firmware", "configuration", "configuration"]
    assert [s["apply_mode"] for s in steps[1:]] == ["replace", "merge"]
    assert all(s["state"] == "awaiting_approval" for s in steps)
    assert "deferred: it is made at the run, after step 1 (firmware)" in messages(steps[1])
    assert b.fg.restarts == 0  # nothing changed yet
    listed = b.c.get(f"/api/projects/{b.pid}/staging-plans").json()
    assert listed[0]["device_id"] == b.did and listed[0]["kinds"] == [
        "firmware", "configuration", "configuration"]

    sid = plan_["staging_id"]
    no_window = b.c.post(f"/api/staging-plans/{sid}/approve")
    assert no_window.status_code == 409 and "maintenance window" in no_window.json()["error"]
    approved = b.c.post(f"/api/staging-plans/{sid}/approve", json=window()).json()
    assert all(s["state"] == "ready" for s in approved["steps"])
    out = b.c.post(f"/api/staging-plans/{sid}/execute?background=false").json()
    assert [s["state"] for s in out["steps"]] == ["succeeded"] * 3, [
        messages(s) for s in out["steps"]]
    assert b.fg.version == "v7.6.5" and b.fg.hostname == "lab-fw-site"
    assert b.fg.revisions == ["base-example", "site-example"]
    assert f'set psksecret "{PSK}"' in b.fg.applied
    assert PSK not in repr(out)


def test_device_staging_is_checked_before_anything_is_made(bench):
    b = bench
    img = approved_image(b, "7.6.6", approve=False)
    site = imported(b, "site-example.cfg", SCRIPT)
    before = len(b.c.get("/api/deployments").json())
    cases = [
        ([{"kind": "firmware", "image_id": img["id"]}], "not approved"),
        ([{"kind": "configuration", "version_id": site["id"]}, {"kind": "first_login"}],
         "first login can only be the first step"),
        ([{"kind": "configuration", "version_id": site["id"], "apply_mode": "replace"}],
         "merge mode"),
        ([{"kind": "configuration"}], "choose the file"),
    ]
    for steps, words in cases:
        r = b.c.post(f"/api/projects/{b.pid}/device-staging",
                     json={"device_id": b.did, "steps": steps})
        assert r.status_code == 409 and words in r.json()["error"], (words, r.json())
    assert len(b.c.get("/api/deployments").json()) == before  # no plan was made


# --- bench log (D-090) ------------------------------------------------------------------------

def test_bench_log_lists_every_step_and_masks_what_identifies_the_system(bench):
    b = bench
    img = approved_image(b)
    base = imported(b, "base-example.conf", BACKUP)
    site = imported(b, "site-example.cfg", SCRIPT)
    sid = b.c.post(f"/api/projects/{b.pid}/device-staging", json={"device_id": b.did, "steps": [
        {"kind": "firmware", "image_id": img["id"]},
        {"kind": "configuration", "version_id": base["id"]},
        {"kind": "configuration", "version_id": site["id"], "secrets": {SLOT: b.psk}}]}
    ).json()["staging_id"]
    b.c.post(f"/api/staging-plans/{sid}/approve", json=window())
    steps = b.c.post(f"/api/staging-plans/{sid}/execute?background=false").json()["steps"]
    assert [s["state"] for s in steps] == ["succeeded"] * 3

    r = b.c.get(f"/api/projects/{b.pid}/bench-log", headers={"X-UNDM-Actor": "Example Person"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    log = r.text
    assert log.startswith("UNDM bench log (masked)")
    assert "real-device changes ON" in log and "second approver for firmware off" in log
    assert log.count("→ succeeded") == 3 and "step 3" in log
    assert "firmware" in log and "configuration (replace" in log and "configuration (merge" in log
    assert "Masking is automatic and best effort" in log
    serial = b.c.get(f"/api/devices/{b.did}").json()["observed_facts"]["serial_number"]
    for secret in ("Staging", "lab-fw1", "lab-fw-base", "lab-fw-site", "example-tunnel",
                   "127.0.0.1", "fw-admin", "cen-psk", serial, PSK, ADMIN_PW,
                   "base-example.conf", "site-example.cfg", "base-example", "site-example"):
        assert secret not in log, secret
    # Revisions are named after the files (bench 2026-11-25: one showed the site code).
    assert "revision '<file-" in log
    assert "<device-1>" in log and "<hostname-" in log
    assert "Fortinet FortiGate-101F" in log  # the model is not an identifier: kept
    assert "number<serial" not in log
    audit = b.c.get("/api/audit").json()
    assert any(a["action"] == "system.bench_log" for a in audit)


def test_bench_log_window(bench):
    b = bench
    assert "0 plans" in b.c.get(f"/api/projects/{b.pid}/bench-log?hours=1").text
    imported(b, "site-example.cfg", SCRIPT)
    b.c.post(f"/api/projects/{b.pid}/deployments", json={"device_ids": [b.did], "dry_run": True,
                                                           "apply_mode": "merge"})
    assert "1 plans" in b.c.get(f"/api/projects/{b.pid}/bench-log?hours=0").text
    assert b.c.get(f"/api/projects/{b.pid}/bench-log?hours=-1").status_code == 422
