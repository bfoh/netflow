"""Guided staging of the Nokia Flexi BBU (D-117): UNDM checks its portal answers, hands out
the approved software package and the generated SCF with their SHA-256, and records each
step a person does in the portal. UNDM never logs in to the BBU.

Synthetic values only: made-up systems, zones, files and an RFC 5737 address."""

import hashlib

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring
from test_system_templates import imp, scf, system, table

from undm.drivers.base import Capability, DeviceTarget
from undm.drivers.nokia import flexi
from undm.drivers.nokia.flexi import NokiaFlexiGuided

PACKAGE = b"synthetic software package for the guided steps\n" * 64


@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def bbu(c, pid, driver="guided.nokia.flexi", name="lab-bbu"):
    r = c.post(f"/api/projects/{pid}/devices", json={
        "name": name, "manufacturer": "Nokia", "category": "other", "model": "FSMF",
        "driver_id": driver, "environment": "simulated" if driver.startswith("mock") else "lab",
        "management_address": "192.0.2.129", "management_protocol": "https_api",
        "management_port": 443})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def package(c):
    img = c.post("/api/firmware/images", data={
        "vendor": "Nokia", "platform": "flexi_sbts", "version": "SBTS-EXAMPLE",
        "compatible_models": "FSMF", "vendor_sha256": hashlib.sha256(PACKAGE).hexdigest()},
        files={"file": ("SBTS_EXAMPLE_downloadable.zip", PACKAGE,
                        "application/octet-stream")}).json()
    return img


def steps(c, did):
    return {s["key"]: s for s in c.get(f"/api/devices/{did}/guided").json()["steps"]}


def test_the_driver_only_checks_that_the_portal_answers(monkeypatch):
    seen = []
    monkeypatch.setattr(flexi, "tcp_port_open", lambda h, p, t: seen.append((h, p)) or True)
    d = NokiaFlexiGuided(DeviceTarget("d1", "192.0.2.129"))
    ok = d.connect()
    assert ok.ok and "nothing was logged in to" in ok.message and seen == [("192.0.2.129", 443)]
    monkeypatch.setattr(flexi, "tcp_port_open", lambda h, p, t: False)
    no = d.connect()
    assert not no.ok and "192.168.255.126/24" in no.message
    assert NokiaFlexiGuided.info.capabilities == frozenset({Capability.GUIDED_STAGING})
    assert not d.apply_configuration("x", None).ok  # never changes the BBU  # type: ignore[arg-type]


def test_the_steps_are_recorded_in_order_with_the_files_handed_out(client, monkeypatch):
    monkeypatch.setattr(flexi, "tcp_port_open", lambda h, p, t: False)
    # The SCF from the team's template (written with CRLF), for zone 42, system B009.
    imp(client, "bbu_scf", scf(7, 41, (5, 6)).replace("\n", "\r\n"),
        "Full_scf_MRBTS-7_eNB1-ABCB-007-Z041_20260102-1000.xml")
    table(client)
    pid = system(client)
    did = bbu(client, pid)  # no login: UNDM never logs in to it
    made = client.post(f"/api/projects/{pid}/generate-files",
                       json={"assignments": {"bbu_scf": did}})
    assert made.status_code == 201, made.text
    version = made.json()[0]["version_id"]
    first = steps(client, did)
    assert list(first) == ["portal", "software", "scf", "state"]
    assert all(s["done_by"] is None for s in first.values())
    early = client.post(f"/api/devices/{did}/guided/scf", json={"version_id": version})
    assert early.status_code == 409 and "Do 'Its portal answers' first" in early.json()["error"]
    silent = client.post(f"/api/devices/{did}/guided/portal", json={})
    assert silent.status_code == 409 and "No answer on 192.0.2.129:443" in silent.json()["error"]
    monkeypatch.setattr(flexi, "tcp_port_open", lambda h, p, t: True)
    assert client.post(f"/api/devices/{did}/guided/portal", json={}).status_code == 200
    # The software package: approved, for this model.
    img = package(client)
    unapproved = client.post(f"/api/devices/{did}/guided/software",
                             json={"image_id": img["id"], "note": "Software page, version x"})
    assert unapproved.status_code == 409 and "not approved" in unapproved.json()["error"]
    client.post(f"/api/firmware/images/{img['id']}/approve")
    no_note = client.post(f"/api/devices/{did}/guided/software", json={"image_id": img["id"]})
    assert no_note.status_code == 409 and "Write what you saw" in no_note.json()["error"]
    r = client.post(f"/api/devices/{did}/guided/software",
                    json={"image_id": img["id"], "note": "Software page; shows SBTS-EXAMPLE"})
    assert r.status_code == 200
    soft = steps(client, did)["software"]
    assert soft["file_sha256"] == hashlib.sha256(PACKAGE).hexdigest()
    assert soft["done_by"] and soft["note"].startswith("Software page")
    assert client.get(f"/api/firmware/images/{img['id']}/file").content == PACKAGE
    # The SCF: handed out byte for byte as the team writes it (CRLF), its SHA-256 recorded.
    handed = client.get(f"/api/devices/{did}/guided-file/{version}")
    expected = scf(9, 42, (16, 17)).replace("\n", "\r\n").encode()
    assert handed.content == expected
    assert "Full_scf_MRBTS-9_eNB1-ABCB-009-Z042_" in handed.headers["content-disposition"]
    client.post(f"/api/devices/{did}/guided/scf",
                json={"version_id": version, "note": "Commissioning; plan activated"})
    assert steps(client, did)["scf"]["file_sha256"] == hashlib.sha256(expected).hexdigest()
    # Finish staging waits for the last step.
    finish = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert finish.status_code == 409 and "Its state checked" in finish.json()["error"]
    client.post(f"/api/devices/{did}/guided/state", json={"note": "On air, no alarms"})
    assert client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]}).status_code \
        == 200
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert actions.count("guided.step_done") == 4


def test_undo_clears_the_step_and_those_after_it(client, monkeypatch):
    monkeypatch.setattr(flexi, "tcp_port_open", lambda h, p, t: True)
    pid = client.post("/api/projects", json={"name": "Practice"}).json()["id"]
    did = bbu(client, pid)
    img = package(client)
    client.post(f"/api/firmware/images/{img['id']}/approve")
    client.post(f"/api/devices/{did}/guided/portal", json={})
    client.post(f"/api/devices/{did}/guided/software",
                json={"image_id": img["id"], "note": "loaded"})
    again = client.post(f"/api/devices/{did}/guided/software",
                        json={"image_id": img["id"], "note": "again"})
    assert again.status_code == 409 and "undo it first" in again.json()["error"]
    left = client.delete(f"/api/devices/{did}/guided/portal").json()["steps"]
    assert all(s["done_by"] is None for s in left)
    undone = next(a for a in client.get("/api/audit").json()
                  if a["action"] == "guided.step_undone")
    assert undone["details"]["steps"] == ["portal", "software"]


def test_the_simulated_bbu_and_other_devices(client):
    pid = client.post("/api/projects", json={"name": "Practice"}).json()["id"]
    sim = bbu(client, pid, driver="mock.nokia.flexi")
    assert client.post(f"/api/devices/{sim}/guided/portal", json={}).status_code == 200
    sw = client.post(f"/api/projects/{pid}/devices", json={
        "name": "sw", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "mock.aruba.aos_switch"}).json()["id"]
    assert client.get(f"/api/devices/{sw}/guided").status_code == 404
