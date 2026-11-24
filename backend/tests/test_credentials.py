import keyring
import pytest
from api_helpers import SWITCH, make_client
from keyring.backends.fail import Keyring as FailKeyring
from memory_keyring import MemoryKeyring


@pytest.fixture
def mem_keyring():
    previous = keyring.get_keyring()
    kr = MemoryKeyring()
    keyring.set_keyring(kr)
    yield kr
    keyring.set_keyring(previous)


@pytest.fixture
def client():
    c, _ = make_client()
    with c:
        yield c


def _project(client):
    return client.post("/api/projects", json={"name": "Cred"}).json()["id"]


def test_keyring_secret_is_stored_outside_db_and_never_returned(client, mem_keyring):
    pid = _project(client)
    ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "lab-admin"}).json()
    assert ref["provider"] == "keyring" and ref["locator"] == f"credential/{ref['id']}"
    assert ref["has_secret"] is False
    r = client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "netops", "password": "S3cret-Example"})
    assert r.status_code == 200 and r.json()["has_secret"] is True
    assert "S3cret-Example" not in r.text
    assert any("S3cret-Example" in v for v in mem_keyring.store.values())
    listed = client.get(f"/api/projects/{pid}/credential-refs").text
    audit = client.get("/api/audit").text
    assert "S3cret-Example" not in listed and "S3cret-Example" not in audit
    # attach to device, delete ref -> device detached and secret removed
    dev = client.post(f"/api/projects/{pid}/devices",
                      json=dict(SWITCH, credential_ref_id=ref["id"])).json()
    assert dev["credential_ref_id"] == ref["id"]
    assert client.delete(f"/api/credential-refs/{ref['id']}").status_code == 204
    assert client.get(f"/api/devices/{dev['id']}").json()["credential_ref_id"] is None
    assert mem_keyring.store == {}


def test_no_os_store_gives_clear_error(client):
    previous = keyring.get_keyring()
    keyring.set_keyring(FailKeyring())
    try:
        pid = _project(client)
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "x"}).json()
        r = client.put(f"/api/credential-refs/{ref['id']}/secret",
                       json={"username": "u", "password": "p"})
        assert r.status_code == 400 and "credential store" in r.json()["error"]
    finally:
        keyring.set_keyring(previous)


def test_env_provider_requires_locator(client):
    pid = _project(client)
    r = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "e", "provider": "env"})
    assert r.status_code == 400
    ok = client.post(f"/api/projects/{pid}/credential-refs",
                     json={"name": "e", "provider": "env", "locator": "lab_sw"}).json()
    assert ok["has_secret"] is False
    r = client.put(f"/api/credential-refs/{ok['id']}/secret",
                   json={"username": "u", "password": "p"})
    assert r.status_code == 400 and "read-only" in r.json()["error"]


def test_deleting_a_system_removes_its_passwords_from_the_store(client, mem_keyring):
    pid = _project(client)
    for name in ("factory", "approved"):
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": name}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "admin", "password": f"Example-{name}"})
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]  # its login stays
    keep = client.post(f"/api/projects/{other}/credential-refs", json={"name": "x"}).json()
    client.put(f"/api/credential-refs/{keep['id']}/secret",
               json={"username": "admin", "password": "Example-other"})
    assert len(mem_keyring.store) == 3
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert len(mem_keyring.store) == 1
    assert all("Example-other" in v for v in mem_keyring.store.values())
    event = next(a for a in client.get("/api/audit").json() if a["action"] == "project.delete")
    assert event["details"]["stored_logins_removed"] == 2
    assert "Example-" not in str(event["details"])
