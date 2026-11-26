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
                     "aruba": {"login": None, "current": None},
                     "modem": {"login": None}}
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


def test_the_modem_has_a_default_login(client):
    approved = shared(client)
    r = client.put("/api/settings/defaults", json={"modem": {"login": approved}})
    assert r.status_code == 200, r.text
    assert client.get("/api/settings/defaults").json()["modem"] == {"login": approved}
    wrong = client.put("/api/settings/defaults", json={"modem": {"current": approved}})
    assert wrong.status_code == 422
    audit = [a for a in client.get("/api/audit").json() if a["action"] == "settings.defaults"]
    assert audit[0]["details"]["modem"] == {"login": "approved"}
    # Deleting the login clears the modem's default too.
    client.delete(f"/api/credential-refs/{approved}")
    assert client.get("/api/settings/defaults").json()["modem"] == {"login": None}


def test_defaults_stored_before_the_modem_row_read_back_with_it_empty():
    from undm.services import app_settings

    client, factory = make_client()
    with client:
        approved = shared(client)
        with factory() as session:
            # As v78..v93 stored them: no modem entry.
            app_settings.put(session, app_settings.DEFAULTS, {
                "firewall": {"login": approved, "login_after": None, "tunnel_key": None},
                "blackbox": {"login": None, "login_after": None},
                "aruba": {"login": None, "current": None}})
            session.commit()
        out = client.get("/api/settings/defaults").json()
        assert out["firewall"]["login"] == approved
        assert out["modem"] == {"login": None}


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


# Bringing the systems' own logins in (D-115). Made-up systems, logins and passwords only.

OLD = "Example-Only-Old-2"
PSK = "Example-Only-Psk-3"


@pytest.fixture
def client_db(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, factory = make_client(data_dir=str(tmp_path))
    with c:
        yield c, factory
    keyring.set_keyring(previous)


def own(c, pid, name, username=None, password=PASSWORD):
    ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": name}).json()
    if username is not None:
        c.put(f"/api/credential-refs/{ref['id']}/secret",
              json={"username": username, "password": password})
    return ref["id"]


def device(c, pid, name, kind, ref):
    body = {"switch": ("Aruba", "switch", "2930F", "mock.aruba.aos_switch"),
            "blackbox": ("Black Box", "switch", "LIG1014A", "mock.blackbox.switch"),
            "firewall": ("Fortinet", "firewall", "FortiGate-101F", "mock.fortinet.fortios")}[kind]
    r = c.post(f"/api/projects/{pid}/devices", json={
        "name": name, "manufacturer": body[0], "category": body[1], "model": body[2],
        "driver_id": body[3], "management_address": "192.0.2.10", "credential_ref_id": ref})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def plan_target(factory, pid, device_id, state="succeeded", **kw):
    from undm.db.models import DeploymentRecord, DeploymentTargetRecord
    with factory() as s:
        d = DeploymentRecord(project_id=pid, state=state, apply_mode="replace",
                             created_by="tester")
        s.add(d)
        s.flush()
        t = DeploymentTargetRecord(deployment_id=d.id, device_id=device_id, position=0,
                                   state="succeeded", **kw)
        s.add(t)
        s.commit()
        return t.id


def test_the_systems_logins_become_logins_for_all_systems_under_clear_names(client_db):
    c, factory = client_db
    p1, p2 = system(c, "Site 1"), system(c, "Site 2")
    a1 = own(c, p1, "approved", "manager")
    factory_login = own(c, p1, "factory bb", "admin", "")
    key = own(c, p1, "psk", "key", PSK)
    a2 = own(c, p2, "approved", "manager")  # the same login, made again in another system
    current = own(c, p2, "current", "manager", OLD)  # same user, another password
    spare = own(c, p2, "spare")  # no password stored: never merged
    sw1 = device(c, p1, "s1-sw", "switch", a1)
    bb = device(c, p1, "s1-bb", "blackbox", factory_login)
    fw = device(c, p1, "s1-fw", "firewall", None)
    sw2 = device(c, p2, "s2-sw", "switch", a2)
    device(c, p2, "s2-sw-b", "switch", current)
    target = plan_target(factory, p2, sw2, credential_after_ref_id=a2,
                         secret_refs={"vpn > tun1 > psksecret": a2})
    plan_target(factory, p1, fw, secret_refs={"vpn ipsec phase1-interface > tun1 > psksecret": key})
    # The preview: what each becomes, with a suggested name. Nothing changes yet.
    preview = c.get("/api/credential-refs/from-systems").json()
    names = {g["name"]: [m["name"] + "@" + m["system"] for m in g["members"]] for g in preview}
    assert names == {
        "Aruba 2930F – manager (approved)": ["approved@Site 1", "approved@Site 2"],
        "Black Box LIG1014A – admin (no password)": ["factory bb@Site 1"],
        "Fortinet FortiGate-101F – tunnel key": ["psk@Site 1"],
        "Aruba 2930F – manager (current)": ["current@Site 2"],
        "spare": ["spare@Site 2"],
    }
    assert next(g for g in preview if g["id"] == a1)["devices"] == 2
    assert c.get("/api/credential-refs").json() == []
    assert PASSWORD not in json.dumps(preview) and OLD not in json.dumps(preview)
    # Run, with one name changed by the person.
    r = c.post("/api/credential-refs/from-systems", json={"names": {spare: "Lab spare login"}})
    assert r.status_code == 200, r.text
    assert r.json()["replaced"] == {a2: a1}
    listed = {x["name"]: x for x in c.get("/api/credential-refs").json()}
    assert set(listed) == {"Aruba 2930F – manager (approved)", "Aruba 2930F – manager (current)",
                           "Black Box LIG1014A – admin (no password)", "Lab spare login",
                           "Fortinet FortiGate-101F – tunnel key"}
    assert all(x["shared"] for x in listed.values())
    assert all(x["shared"] for x in c.get(f"/api/projects/{p2}/credential-refs").json())
    # Devices and plans keep working: the merged login's users moved to the one kept.
    assert c.get(f"/api/devices/{sw2}").json()["credential_ref_id"] == a1
    assert c.get(f"/api/devices/{sw1}").json()["credential_ref_id"] == a1
    assert c.get(f"/api/devices/{bb}").json()["credential_ref_id"] == factory_login
    from undm.db.models import DeploymentTargetRecord
    with factory() as s:
        t = s.get(DeploymentTargetRecord, target)
        assert t.credential_after_ref_id == a1 and t.secret_refs == {"vpn > tun1 > psksecret": a1}
    assert keyring.get_password("UNDM", f"credential/{a2}") is None  # its copy is gone
    assert keyring.get_password("UNDM", f"credential/{a1}") is not None
    audit = c.get("/api/audit").text
    assert "credential_ref.share_all" in audit
    assert all(secret not in audit + r.text for secret in (PASSWORD, OLD, PSK))
    # Nothing left to bring in; new logins can still be made per system.
    assert c.get("/api/credential-refs/from-systems").json() == []
    assert own(c, p1, "approved") is not None


def test_a_systems_login_joins_the_same_login_for_all_systems(client_db):
    c, _ = client_db
    kept = shared(c, "Approved manager login")
    p1 = system(c, "Site 1")
    mine = own(c, p1, "approved", "manager")
    sw = device(c, p1, "s1-sw", "switch", mine)
    preview = c.get("/api/credential-refs/from-systems").json()
    assert [(g["id"], g["name"], g["existing"]) for g in preview] == [
        (kept, "Approved manager login", True)]
    r = c.post("/api/credential-refs/from-systems", json={})
    assert r.status_code == 200 and r.json()["replaced"] == {mine: kept}
    assert c.get(f"/api/devices/{sw}").json()["credential_ref_id"] == kept
    assert [x["name"] for x in c.get("/api/credential-refs").json()] == ["Approved manager login"]


def test_names_must_be_unique_and_a_running_plan_waits(client_db):
    c, factory = client_db
    shared(c, "Approved manager login", password="Example-Only-Other-4")
    p1 = system(c, "Site 1")
    a = own(c, p1, "approved", "manager")
    b = own(c, p1, "other", "manager", OLD)
    r = c.post("/api/credential-refs/from-systems",
               json={"names": {a: "approved manager LOGIN"}})
    assert r.status_code == 409 and "would be called" in r.json()["error"]
    r = c.post("/api/credential-refs/from-systems", json={"names": {a: "Same", b: "same"}})
    assert r.status_code == 409
    assert c.post("/api/credential-refs/from-systems",
                  json={"names": {a: "  "}}).status_code == 400
    sw = device(c, p1, "s1-sw", "switch", a)
    plan_target(factory, p1, sw, state="deploying")
    r = c.post("/api/credential-refs/from-systems", json={})
    assert r.status_code == 409 and "plan is running" in r.json()["error"]
    assert len(c.get(f"/api/projects/{p1}/credential-refs").json()) == 3  # nothing moved
