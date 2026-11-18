import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from api_helpers import SWITCH, make_client

from undm.drivers.mock.lab import default_lab

IMAGE = b"SYNTHETIC TEST IMAGE - not real firmware\n" * 64
SHA = hashlib.sha256(IMAGE).hexdigest()


@pytest.fixture
def client(tmp_path):
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c


def upload(client, sha=SHA, models="6300M", data=IMAGE, **extra):
    form = {"vendor": "Aruba", "platform": "aoscx", "version": "10.1.0",
            "compatible_models": models, **extra}
    if sha:
        form["vendor_sha256"] = sha
    return client.post("/api/firmware/images", data=form,
                       files={"file": ("cx-10.1.0.swi", data, "application/octet-stream")})


def window(start_min=-5, hours=1):
    now = datetime.now(UTC)
    return {"window_start": (now + timedelta(minutes=start_min)).isoformat(),
            "window_end": (now + timedelta(minutes=start_min, hours=hours)).isoformat()}


def setup_switch(client):
    pid = client.post("/api/projects", json={"name": "FW"}).json()["id"]
    did = client.post(f"/api/projects/{pid}/devices", json=SWITCH).json()["id"]
    return pid, did


def test_upload_checksum_and_approval_rules(client, tmp_path):
    bad = upload(client, sha="0" * 64)
    assert bad.status_code == 400 and "mismatch" in bad.json()["error"]
    assert not any((tmp_path / "firmware").glob("*.swi"))  # rejected file not kept
    unverified = upload(client, sha=None).json()
    assert unverified["integrity_verified"] is False
    r = client.post(f"/api/firmware/images/{unverified['id']}/approve")
    assert r.status_code == 409
    client.delete(f"/api/firmware/images/{unverified['id']}")
    img = upload(client).json()
    assert img["sha256"] == SHA and img["integrity_verified"] and img["status"] == "uploaded"
    assert upload(client).status_code == 409  # duplicate file
    approved = client.post(f"/api/firmware/images/{img['id']}/approve").json()
    assert approved["status"] == "approved"


def test_compatibility_check_is_offline_and_explains(client):
    pid, did = setup_switch(client)
    other = client.post(f"/api/projects/{pid}/devices", json=dict(
        SWITCH, name="sw-other", model="6100", management_address="10.255.0.99")).json()["id"]
    img = upload(client).json()
    res = client.post(f"/api/firmware/images/{img['id']}/compatibility",
                      json={"device_ids": [did, other]}).json()
    assert res[0]["compatible"] is False  # not approved yet
    client.post(f"/api/firmware/images/{img['id']}/approve")
    res = client.post(f"/api/firmware/images/{img['id']}/compatibility",
                      json={"device_ids": [did, other]}).json()
    assert res[0]["compatible"] is True
    assert res[1]["compatible"] is False
    assert res[1]["issues"][0]["code"] == "model_not_compatible"
    assert default_lab().get("10.255.0.11") is None  # no device contacted


def test_full_simulated_firmware_upgrade(client):
    pid, did = setup_switch(client)
    img = upload(client).json()
    client.post(f"/api/firmware/images/{img['id']}/approve")
    h_alice, h_bob = {"X-UNDM-Actor": "alice"}, {"X-UNDM-Actor": "bob"}
    dep = client.post(f"/api/projects/{pid}/firmware-upgrades",
                      json={"device_ids": [did], "image_id": img["id"]}, headers=h_alice).json()
    assert dep["kind"] == "firmware" and dep["state"] == "awaiting_approval", dep
    t = dep["targets"][0]
    assert t["from_version"] == "sim-10.0.0" and t["to_version"] == "10.1.0"
    assert client.post(f"/api/deployments/{dep['id']}/approve", json=window(),
                       headers=h_alice).status_code == 403  # creator cannot approve
    assert client.post(f"/api/deployments/{dep['id']}/approve",
                       headers=h_bob).status_code == 403  # window required
    ok = client.post(f"/api/deployments/{dep['id']}/approve", json=window(), headers=h_bob)
    assert ok.status_code == 200 and ok.json()["state"] == "ready"
    out = client.post(f"/api/deployments/{dep['id']}/execute", headers=h_bob).json()
    assert out["state"] == "succeeded", out["events"]
    assert out["targets"][0]["state"] == "verified" and out["targets"][0]["backup_version_id"]
    assert default_lab().get("10.255.0.11").os_version == "10.1.0"
    device = client.get(f"/api/devices/{did}").json()
    assert device["observed_facts"]["os_version"] == "10.1.0"
    assert device["firmware_version"] == ""  # declared value untouched
    assert client.delete(f"/api/firmware/images/{img['id']}").status_code == 409


def test_window_and_retirement_enforced_at_execution(client):
    pid, did = setup_switch(client)
    img = upload(client).json()
    client.post(f"/api/firmware/images/{img['id']}/approve")
    dep = client.post(f"/api/projects/{pid}/firmware-upgrades",
                      json={"device_ids": [did], "image_id": img["id"]},
                      headers={"X-UNDM-Actor": "alice"}).json()
    client.post(f"/api/deployments/{dep['id']}/approve", json=window(start_min=120),
                headers={"X-UNDM-Actor": "bob"})
    r = client.post(f"/api/deployments/{dep['id']}/execute")
    assert r.status_code == 409 and "maintenance window" in r.json()["error"]
    dep2 = client.post(f"/api/projects/{pid}/firmware-upgrades",
                       json={"device_ids": [did], "image_id": img["id"]},
                       headers={"X-UNDM-Actor": "alice"}).json()
    client.post(f"/api/deployments/{dep2['id']}/approve", json=window(),
                headers={"X-UNDM-Actor": "bob"})
    client.post(f"/api/firmware/images/{img['id']}/retire")
    r = client.post(f"/api/deployments/{dep2['id']}/execute")
    assert r.status_code == 409 and "no longer approved" in r.json()["error"]


def test_incompatible_plan_rejected_with_details(client):
    pid, did = setup_switch(client)
    img = upload(client, models="8360").json()
    client.post(f"/api/firmware/images/{img['id']}/approve")
    r = client.post(f"/api/projects/{pid}/firmware-upgrades",
                    json={"device_ids": [did], "image_id": img["id"]})
    assert r.status_code == 409 and "sw1" in r.json()["details"]
