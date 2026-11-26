"""The end of staging a system (D-108): finished only when every staged device's latest
staging plan succeeded and no device is still off the network; a new plan reopens it.
Simulated Black Box, synthetic file."""

import pytest
from api_helpers import make_client

FILE = ("hostname lab-bbsw01\nvlan 1001\n!\ninterface vlan 1\n"
        " ip address 192.0.2.1 255.255.255.0\n!\nend\n")


@pytest.fixture
def client(tmp_path):
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c


def system(c):
    pid = c.post("/api/projects", json={"name": "Site 12"}).json()["id"]
    did = c.post(f"/api/projects/{pid}/devices", json={
        "name": "site12-bb", "manufacturer": "Black Box", "category": "switch",
        "model": "LIG1014A", "driver_id": "mock.blackbox.switch",
        "management_address": "192.0.2.1"}).json()["id"]
    vid = c.post(f"/api/devices/{did}/configs/import",
                 json={"filename": "team-bb.txt", "text": FILE}).json()["id"]
    return pid, did, vid


def stage(c, pid, did, vid, *, run=True):
    made = c.post(f"/api/projects/{pid}/device-staging", json={
        "device_id": did, "steps": [{"kind": "configuration", "version_id": vid}]})
    assert made.status_code == 201, made.text
    sid = made.json()["staging_id"]
    if run:
        c.post(f"/api/staging-plans/{sid}/approve", json={})
        done = c.post(f"/api/staging-plans/{sid}/execute?background=false").json()
        assert all(s["state"] == "succeeded" for s in done["steps"]), done
    return sid


def test_finished_only_when_every_device_is_staged_and_reopened_by_a_new_plan(client):
    pid, did, vid = system(client)
    r = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert r.status_code == 409 and "has no staging plan" in r.json()["error"]
    stage(client, pid, did, vid, run=False)
    r = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert r.status_code == 409 and "has not succeeded" in r.json()["error"]
    stage(client, pid, did, vid)
    r = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert r.status_code == 200, r.text
    assert r.json()["staged_at"] and r.json()["staged_by"]
    assert client.get(f"/api/projects/{pid}").json()["staged_at"]
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert "system.staged" in actions
    # Newer work on the system reopens it, so "finished" never hides it.
    stage(client, pid, did, vid, run=False)
    assert client.get(f"/api/projects/{pid}").json()["staged_at"] is None
    assert "system.reopened" in [a["action"] for a in client.get("/api/audit").json()]


def test_reopen_by_hand_and_unknown_devices(client):
    pid, did, vid = system(client)
    stage(client, pid, did, vid)
    assert client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]}).status_code \
        == 200
    out = client.post(f"/api/projects/{pid}/reopen").json()
    assert out["staged_at"] is None and out["staged_by"] == ""
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    assert client.post(f"/api/projects/{other}/finish",
                       json={"device_ids": [did]}).status_code == 404
    assert client.post(f"/api/projects/{pid}/finish", json={"device_ids": []}).status_code == 422


def test_a_device_still_off_the_network_blocks_the_finish(client):
    from undm.db.models import Device
    from undm.services.devices import set_port_off

    pid, did, vid = system(client)
    stage(client, pid, did, vid)
    factory = client.app.state.session_factory
    with factory() as s:
        set_port_off(s.get(Device, did), "2")
        s.commit()
    r = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert r.status_code == 409 and "management port off" in r.json()["error"]
