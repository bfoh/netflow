"""Export a system to a .undm package and import it on another copy (D-087). Synthetic data."""

import hashlib
import io
import json
import zipfile

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

PASSWORD = "Example-Only-Secret-1"
FILE = ("hostname lab-bbsw01\nvlan 1001\n!\ninterface vlan 1\n"
        " ip address 192.0.2.1 255.255.255.0\n!\nend\n")


@pytest.fixture
def two_copies(tmp_path):
    """Two copies of UNDM (two databases and data folders) on one keyring."""
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    a, _ = make_client(data_dir=str(tmp_path / "a"))
    b, _ = make_client(data_dir=str(tmp_path / "b"))
    with a, b:
        yield a, b
    keyring.set_keyring(previous)


def make_system(c):
    pid = c.post("/api/projects", json={"name": "Site 12", "site": "Bench",
                                        "purpose": "Staging"}).json()["id"]
    ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
    c.put(f"/api/credential-refs/{ref['id']}/secret",
          json={"username": "admin", "password": PASSWORD})
    bb = c.post(f"/api/projects/{pid}/devices", json={
        "name": "site12-bb", "manufacturer": "Black Box", "category": "switch", "model": "LIG1014A",
        "driver_id": "mock.blackbox.switch", "management_address": "192.0.2.1",
        "credential_ref_id": ref["id"], "tags": ["bench"]}).json()
    sw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "site12-sw-a", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "mock.aruba.aos_switch", "management_address": "192.168.1.1",
        "bootstrap_profile": {"vlan_id": 222, "vlan_name": "OOBM", "untagged_port": "2",
                              "address": "192.168.1.1/24"}}).json()
    assert c.post(f"/api/devices/{bb['id']}/configs/import",
                  json={"filename": "team-bb.txt", "text": FILE}).status_code == 201
    c.post(f"/api/projects/{pid}/topology/links", json={
        "a_device_id": bb["id"], "a_interface": "1/3", "b_device_id": sw["id"], "b_interface": "2",
        "mode": "access", "vlans": [222], "notes": ""})
    return pid


def test_a_system_moves_to_another_copy_without_its_passwords(two_copies):
    a, b = two_copies
    pid = make_system(a)
    r = a.get(f"/api/projects/{pid}/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="Site_12.undm"' in r.headers["content-disposition"]
    package = r.content
    assert PASSWORD.encode() not in package  # never a password
    with zipfile.ZipFile(io.BytesIO(package)) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["logins"] == ["approved"] and len(manifest["files"]) == 1

    r = b.post("/api/systems/import", files={"file": ("Site_12.undm", package, "application/zip")})
    assert r.status_code == 201, r.json()
    out = r.json()
    assert out["project"]["name"] == "Site 12" and out["summary"]["devices"] == 2
    assert out["summary"]["logins"] == ["approved"]
    new = out["project"]["id"]
    devices = {d["name"]: d for d in b.get(f"/api/projects/{new}/devices").json()}
    assert devices["site12-sw-a"]["bootstrap_profile"]["untagged_port"] == "2"
    assert devices["site12-bb"]["tags"] == ["bench"]
    refs = b.get(f"/api/projects/{new}/credential-refs").json()
    assert [(x["name"], x["has_secret"]) for x in refs] == [("approved", False)]  # to be stored
    assert devices["site12-bb"]["credential_ref_id"] == refs[0]["id"]
    files = b.get(f"/api/devices/{devices['site12-bb']['id']}/configs").json()
    assert [f["reference"] for f in files] == ["team-bb.txt"]
    topo = b.get(f"/api/projects/{new}/topology").json()
    assert [(x["a_interface"], x["b_interface"], x["vlans"]) for x in topo["links"]] == [
        ("1/3", "2", [222])]
    actions = [x["action"] for c in (a, b) for x in c.get("/api/audit").json()]
    assert "system.export" in actions and "system.import" in actions


def test_an_existing_name_needs_another_name(two_copies):
    a, _ = two_copies
    pid = make_system(a)
    package = a.get(f"/api/projects/{pid}/export").content
    r = a.post("/api/systems/import", files={"file": ("p.undm", package)})
    assert r.status_code == 409 and "another name" in r.json()["error"]
    r = a.post("/api/systems/import", files={"file": ("p.undm", package)},
               data={"name": "Site 12 copy"})
    assert r.status_code == 201 and r.json()["project"]["name"] == "Site 12 copy"


def _rewrite(package: bytes, change) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(package))
    entries = {n: src.read(n) for n in src.namelist()}
    change(entries)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n, data in entries.items():
            z.writestr(n, data)
    return out.getvalue()


def test_damaged_or_unsafe_packages_create_nothing(two_copies):
    a, b = two_copies
    package = a.get(f"/api/projects/{make_system(a)}/export").content

    def tamper(entries):
        name = next(n for n in entries if n.startswith("files/"))
        entries[name] = entries[name].replace(b"vlan 1001", b"vlan 666")

    def escape(entries):
        m = json.loads(entries["manifest.json"])
        m["files"][0]["path"] = "../../evil.txt"
        entries["manifest.json"] = json.dumps(m).encode()

    def unknown_driver(entries):
        m = json.loads(entries["manifest.json"])
        m["devices"][0]["driver_id"] = "ssh.unknown.thing"
        entries["manifest.json"] = json.dumps(m).encode()

    cases = [(_rewrite(package, tamper), "does not match its checksum"),
             (_rewrite(package, escape), "unsafe file name"),
             (_rewrite(package, unknown_driver), "does not have"),
             (b"not a zip", "not a zip file")]
    for data, words in cases:
        r = b.post("/api/systems/import", files={"file": ("x.undm", data)})
        assert r.status_code in (400, 422) and words in r.json()["error"], (words, r.json())
    assert b.get("/api/projects").json() == []  # nothing was created


def test_firmware_travels_on_request_and_arrives_unapproved(two_copies):
    a, b = two_copies
    pid = make_system(a)
    image = b"SYNTHETIC LIG1014A IMAGE v00.01.01\n" + b"\0" * 1000
    img = a.post("/api/firmware/images", data={
        "vendor": "Black Box", "platform": "blackbox", "version": "v00.01.01",
        "compatible_models": "LIG1014A", "vendor_sha256": hashlib.sha256(image).hexdigest()},
        files={"file": ("LIG1014A_v00.01.01.dat", image)}).json()
    a.post(f"/api/firmware/images/{img['id']}/approve")
    without = a.get(f"/api/projects/{pid}/export").content
    assert image not in without
    package = a.get(f"/api/projects/{pid}/export?include_firmware=true").content
    out = b.post("/api/systems/import", files={"file": ("p.undm", package)}).json()
    assert out["summary"]["firmware_added"] == 1
    imported = b.get("/api/firmware/images").json()
    assert [(i["version"], i["status"], i["integrity_verified"]) for i in imported] == [
        ("v00.01.01", "uploaded", True)]


# -- a system's backups as files (D-097) --------------------------------------------------

def test_backups_of_a_system_come_as_one_zip_with_a_folder_per_device(two_copies):
    a, _ = two_copies
    pid = make_system(a)
    devices = {d["name"]: d["id"] for d in a.get(f"/api/projects/{pid}/devices").json()}
    for did in devices.values():
        r = a.post(f"/api/devices/{did}/operations/backup_configuration").json()
        assert r["status"] == "success", r
    r = a.get(f"/api/projects/{pid}/backups.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="Site_12-backups.zip"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "README.txt" in names and "CONFIDENTIAL" in z.read("README.txt").decode()
    files = [n for n in names if n != "README.txt"]
    assert sorted({n.split("/")[0] for n in files}) == ["site12-bb", "site12-sw-a"]
    assert all("-before-" in n and n.endswith(".txt") for n in files) and len(files) == 2
    stored = a.get(f"/api/devices/{devices['site12-bb']}/configs").json()
    backup = next(v for v in stored if v["kind"] == "backup")
    text = a.get(f"/api/configs/{backup['id']}").json()["text"]
    assert z.read(next(n for n in files if n.startswith("site12-bb/"))).decode() == text
    entry = next(x for x in a.get("/api/audit?limit=20").json()
                 if x["action"] == "system.backups_export")
    assert entry["details"] == {"devices": 2, "backups": 2, "since": None}  # counts only


def test_backups_zip_of_a_system_without_backups_and_of_no_system(two_copies):
    a, _ = two_copies
    pid = make_system(a)
    z = zipfile.ZipFile(io.BytesIO(a.get(f"/api/projects/{pid}/backups.zip").content))
    assert z.namelist() == ["README.txt"]
    assert a.get("/api/projects/nope/backups.zip").status_code == 404
