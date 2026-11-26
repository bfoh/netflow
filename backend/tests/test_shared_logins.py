"""Logins and defaults for all systems (D-105). Synthetic names and passwords only."""

import io
import json
import zipfile

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

PASSWORD = "Example-Only-Shared-1"


@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def shared(c, name="approved", password=PASSWORD):
    ref = c.post("/api/credential-refs", json={"name": name}).json()
    c.put(f"/api/credential-refs/{ref['id']}/secret",
          json={"username": "manager", "password": password})
    return ref["id"]


def system(c, name):
    return c.post("/api/projects", json={"name": name}).json()["id"]


def switch(c, pid, name, ref=None):
    return c.post(f"/api/projects/{pid}/devices", json={
        "name": name, "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "mock.aruba.aos_switch", "management_address": "192.0.2.10",
        "credential_ref_id": ref})


def test_a_shared_login_is_offered_to_every_system_and_never_shows_its_password(client):
    ref = shared(client)
    listed = client.get("/api/credential-refs").json()
    assert [(r["name"], r["shared"], r["has_secret"]) for r in listed] == [
        ("approved", True, True)]
    p1, p2 = system(client, "Site 1"), system(client, "Site 2")
    own = client.post(f"/api/projects/{p1}/credential-refs", json={"name": "local"}).json()
    in_p1 = client.get(f"/api/projects/{p1}/credential-refs").json()
    assert [(r["name"], r["shared"]) for r in in_p1] == [("local", False), ("approved", True)]
    assert [r["id"] for r in client.get(f"/api/projects/{p2}/credential-refs").json()] == [ref]
    assert PASSWORD not in client.get("/api/audit").text
    # Any system's device may use it; another system's own login stays refused.
    assert switch(client, p1, "s1-sw", ref).status_code == 201
    assert switch(client, p2, "s2-sw", ref).status_code == 201
    assert switch(client, p2, "s2-sw-b", own["id"]).status_code == 400
    created = [a for a in client.get("/api/audit").json()
               if a["action"] == "credential_ref.create"]
    assert any(a["details"].get("shared") for a in created)


def test_shared_names_are_unique_among_shared_logins(client):
    shared(client)
    assert client.post("/api/credential-refs", json={"name": "approved"}).status_code == 409
    pid = system(client, "Site 1")  # a system may still have its own of that name
    assert client.post(f"/api/projects/{pid}/credential-refs",
                       json={"name": "approved"}).status_code == 201


def test_deleting_a_system_keeps_shared_logins_and_deleting_one_unassigns_everywhere(client):
    ref = shared(client)
    p1, p2 = system(client, "Site 1"), system(client, "Site 2")
    d1 = switch(client, p1, "s1-sw", ref).json()["id"]
    switch(client, p2, "s2-sw", ref)
    assert client.delete(f"/api/projects/{p2}").status_code == 204
    assert [r["id"] for r in client.get("/api/credential-refs").json()] == [ref]
    assert client.delete(f"/api/credential-refs/{ref}").status_code == 204
    assert client.get(f"/api/devices/{d1}").json()["credential_ref_id"] is None


def test_defaults_name_shared_logins_only(client):
    empty = client.get("/api/settings/defaults").json()
    assert empty == {"firewall": {"login": None, "login_after": None, "tunnel_key": None},
                     "blackbox": {"login": None, "login_after": None},
                     "aruba": {"login": None, "current": None}}
    approved, factory, key = shared(client), shared(client, "factory", ""), shared(client, "psk")
    body = {"firewall": {"login": approved, "tunnel_key": key},
            "blackbox": {"login": factory, "login_after": approved},
            "aruba": {"login": approved, "current": factory}}
    r = client.put("/api/settings/defaults", json=body)
    assert r.status_code == 200, r.text
    out = client.get("/api/settings/defaults").json()
    assert out["firewall"] == {"login": approved, "login_after": None, "tunnel_key": key}
    assert out["aruba"]["current"] == factory
    pid = system(client, "Site 1")
    own = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "x"}).json()["id"]
    bad = client.put("/api/settings/defaults", json={"aruba": {"login": own}})
    assert bad.status_code == 400 and "for all systems" in bad.json()["error"]
    assert client.put("/api/settings/defaults",
                      json={"aruba": {"nope": approved}}).status_code == 422
    audit = [a for a in client.get("/api/audit").json() if a["action"] == "settings.defaults"]
    assert audit and audit[0]["details"]["aruba"] == {"login": "approved", "current": "factory"}
    # A deleted login is no longer a default.
    client.delete(f"/api/credential-refs/{key}")
    assert client.get("/api/settings/defaults").json()["firewall"]["tunnel_key"] is None


def test_export_names_shared_logins_and_import_uses_the_shared_one_of_that_name(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    a, _ = make_client(data_dir=str(tmp_path / "a"))
    b, _ = make_client(data_dir=str(tmp_path / "b"))
    try:
        with a, b:
            ref = shared(a)
            pid = system(a, "Site 1")
            switch(a, pid, "s1-sw", ref)
            package = a.get(f"/api/projects/{pid}/export").content
            assert PASSWORD.encode() not in package
            with zipfile.ZipFile(io.BytesIO(package)) as z:
                manifest = json.loads(z.read("manifest.json"))
            assert manifest["logins"] == [] and manifest["shared_logins"] == ["approved"]
            here = shared(b)
            out = b.post("/api/systems/import", files={"file": ("p.undm", package)}).json()
            assert out["summary"]["shared_logins_used"] == ["approved"]
            new = out["project"]["id"]
            dev = b.get(f"/api/projects/{new}/devices").json()[0]
            assert dev["credential_ref_id"] == here
            # A copy without that shared login gets a login of the new system instead.
            c, _ = make_client(data_dir=str(tmp_path / "c"))
            with c:
                out = c.post("/api/systems/import", files={"file": ("p.undm", package)}).json()
                assert out["summary"]["logins"] == ["approved"]
                refs = c.get(f"/api/projects/{out['project']['id']}/credential-refs").json()
                assert [(r["name"], r["shared"]) for r in refs] == [("approved", False)]
    finally:
        keyring.set_keyring(previous)
