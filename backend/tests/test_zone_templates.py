"""Team templates by zone (D-111). Synthetic files only: fictional zones 41 and 42, RFC 1918 /
RFC 5737 addresses and made-up names. The rules are the team's numbering convention as
shown by two zones' files; these tests prove the engine, not any real file."""

import pytest
from api_helpers import make_client

from undm.configgen import zone as zr

ZONE41 = """; Example switch file v03
hostname "z041labsw01"
banner exec "z041 Lab Switch"
ip route 0.0.0.0 0.0.0.0 10.168.248.254
ip authorized-managers 192.168.1.1 255.255.255.0 access manager
logging 10.168.201.65
; route 10.41.233.0/24 => 10.168.248.100
sntp server priority 1 10.0.41.49
vlan 222
   ip address 192.168.1.1 255.255.255.0
   exit
vlan 168
   ip address 10.168.248.240 255.255.255.0
   exit
set dst 130.41.1.0 255.255.255.0
set subnet 10.0.244.8 255.255.255.248
"""


def zone42() -> str:
    return (ZONE41.replace("z041", "z042").replace("10.168.", "10.169.")
            .replace("10.41.", "10.42.").replace("10.0.41.", "10.0.42.")
            .replace("130.41.", "130.42."))


def test_the_five_rules_give_the_other_zone_exactly_and_leave_the_rest():
    t = zr.templatize(ZONE41, 41)
    assert t.counts == {"zone_tag": 2, "ten_plus127": 4, "ten_zone": 1, "ten_zero_zone": 1,
                        "onethirty_zone": 1}
    assert zr.render(t.text, 42) == zone42()
    assert zr.render(t.text, 41) == ZONE41
    out = zr.render(t.text, 7)
    assert "z007labsw01" in out and "10.134.248.254" in out and "10.0.7.49" in out
    # Not the zone's: bench addresses, 192.168.x (168 = 127 + 41 only counts after "10."),
    # VLAN numbers and other networks stay as they are.
    assert "192.168.1.1" in out and "vlan 168" in out and "10.0.244.8" in out
    # "vlan 168" holds 127 + 41 in another form: kept, and listed for a person to check.
    assert t.to_check == [(12, "vlan 168")]


def test_zone_bounds_and_the_zone_in_a_name():
    with pytest.raises(zr.ZoneError):
        zr.render("x", 0)
    with pytest.raises(zr.ZoneError):
        zr.render("x", 129)
    assert zr.zone_from_text("Lab-z007-system") == 7 and zr.zone_from_text("B001z045") == 45
    assert zr.zone_from_text("z041 and z042") is None
    assert zr.zone_from_text("no zone") is None


def test_other_forms_of_the_zone_are_listed_for_a_person():
    t = zr.templatize(ZONE41 + 'name "Port-41"\nset priority 168\n', 41)
    assert [n for n, _ in t.to_check] == [12, 17, 18]


def test_compare_lists_the_first_differences():
    t = zr.templatize(ZONE41, 41)
    c = zr.compare(zr.render(t.text, 42), zone42().replace("10.169.201.65", "10.169.201.66"))
    assert not c.same and c.differences[0][0] == 6


@pytest.fixture
def client(tmp_path):
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c


def imp(c, role="bhdmz", text=ZONE41, filename="z041-LabSw-v03.pcc", **kw):
    return c.post("/api/templates", json={"role": role, "filename": filename, "text": text,
                                          **kw})


def test_import_verify_preview_and_audit(client):
    r = imp(client, verify={"filename": "z042-LabSw-v03.pcc", "text": zone42()})
    assert r.status_code == 201, r.text
    tpl = r.json()["template"]
    assert tpl["role"] == "bhdmz" and tpl["version"] == "v03" and tpl["reference_zone"] == 41
    assert tpl["verified_zone"] == 42 and tpl["filename"] == "${zone_tag}-LabSw-v03.pcc"
    listed = client.get("/api/templates").json()
    assert [t["role"] for t in listed] == ["bhdmz"] and "text" not in listed[0]
    pre = client.get("/api/templates/bhdmz/preview?zone=7").json()
    assert pre["filename"] == "z007-LabSw-v03.pcc" and 'hostname "z007labsw01"' in pre["text"]
    assert "10.134.248.254" in pre["text"]
    # A mismatching second file keeps nothing.
    bad = imp(client, verify={"filename": "z042-LabSw-v03.pcc",
                              "text": zone42().replace("z042lab", "z042lap")})
    assert bad.status_code == 409 and "line 2" in bad.json()["details"][0]
    assert len(client.get("/api/templates").json()) == 1
    # A newer version replaces the current one; the older is counted.
    imp(client, filename="z041-LabSw-v04.pcc")
    assert client.get("/api/templates").json()[0]["version"] == "v04"
    assert client.get("/api/templates").json()[0]["older"] == 1
    entry = next(a for a in client.get("/api/audit").json() if a["action"] == "template.import")
    assert "text" not in entry["details"] and entry["details"]["role"] == "bhdmz"


def test_files_with_no_zone_or_a_wrong_zone_are_refused(client):
    unnamed = ZONE41.replace("z041", "lab")
    r = imp(client, filename="labsw.pcc", text=unnamed)  # no zone named anywhere
    assert r.status_code == 400 and "Say which zone" in r.json()["error"]
    assert imp(client, filename="labsw.pcc", text=unnamed, zone=41).status_code == 201
    r = imp(client, filename="z043-LabSw.pcc")
    assert r.status_code == 400 and "Nothing in this file depends on zone 43" in r.json()["error"]
    base = imp(client, role="fortigate_base", filename="base-v03.conf", text="config x\nend\n")
    assert base.status_code == 201 and base.json()["template"]["reference_zone"] is None


def test_generate_the_files_of_a_system_for_its_zone(client):
    imp(client, role="bhdmz")
    imp(client, role="lte", filename="z041-LteSw-v07.pcc",
        text=ZONE41.replace("labsw", "ltesw"))
    imp(client, role="fortigate_base", filename="base-v03.conf", text="config x\nend\n")
    pid = client.post("/api/projects", json={"name": "Lab z045"}).json()["id"]

    def dev(name, model, driver):
        return client.post(f"/api/projects/{pid}/devices", json={
            "name": name, "manufacturer": "Aruba", "category": "switch", "model": model,
            "driver_id": driver, "management_address": "192.0.2.10"}).json()["id"]
    a = dev("sw-a", "2930F", "mock.aruba.aos_switch")
    b = dev("sw-b", "2930F", "mock.aruba.aos_switch")
    fw = dev("fw", "FortiGate-101F", "mock.fortinet.fortios")
    body = {"assignments": {"bhdmz": a, "lte": b, "fortigate_base": fw}}
    r = client.post(f"/api/projects/{pid}/generate-files", json=body)
    assert r.status_code == 409 and "no zone" in r.json()["error"]
    assert client.patch(f"/api/projects/{pid}", json={"zone": 129}).status_code == 422
    assert client.patch(f"/api/projects/{pid}", json={"zone": 45}).json()["zone"] == 45
    r = client.post(f"/api/projects/{pid}/generate-files", json=body)
    assert r.status_code == 201, r.text
    made = {g["role"]: g for g in r.json()}
    assert made["bhdmz"]["filename"] == "z045-LabSw-v03.pcc"
    assert made["lte"]["filename"] == "z045-LteSw-v07.pcc"
    assert made["fortigate_base"]["filename"] == "base-v03.conf"  # the same for every zone
    v = client.get(f"/api/configs/{made['bhdmz']['version_id']}").json()
    assert v["kind"] == "imported" and 'hostname "z045labsw01"' in v["text"]
    assert "10.172.248.254" in v["text"] and v["verification"] == "generated_from_team_template"
    missing = client.post(f"/api/projects/{pid}/generate-files",
                          json={"assignments": {"tetra": a}})
    assert missing.status_code == 409 and "No template yet" in missing.json()["error"]
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    client.patch(f"/api/projects/{other}", json={"zone": 3})
    assert client.post(f"/api/projects/{other}/generate-files",
                       json=body).status_code == 404
    assert any(x["action"] == "config.generate" for x in client.get("/api/audit").json())


def test_a_systems_zone_travels_with_its_export(client):
    pid = client.post("/api/projects", json={"name": "Lab z045"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"zone": 45})
    package = client.get(f"/api/projects/{pid}/export").content
    out = client.post("/api/systems/import", files={"file": ("p.undm", package)},
                      data={"name": "Lab copy"}).json()
    assert client.get(f"/api/projects/{out['project']['id']}").json()["zone"] == 45


def test_compare_with_the_files_already_on_the_devices(client):
    imp(client, role="bhdmz")
    pid = client.post("/api/projects", json={"name": "Lab z042"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"zone": 42})
    a = client.post(f"/api/projects/{pid}/devices", json={
        "name": "sw-a", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "mock.aruba.aos_switch", "management_address": "192.0.2.10"}).json()["id"]
    body = {"assignments": {"bhdmz": a}}
    none = client.post(f"/api/projects/{pid}/compare-files", json=body).json()[0]
    assert none["file_name"] is None and not none["same"]
    # The team's own zone-42 file on the device: identical line for line.
    client.post(f"/api/devices/{a}/configs/import",
                json={"filename": "z042-LabSw-v03.pcc", "text": zone42()})
    client.post(f"/api/devices/{a}/configs/import",
                json={"filename": "other.cfg", "text": "something else\n"})
    same = client.post(f"/api/projects/{pid}/compare-files", json=body).json()[0]
    assert same["same"] and same["file_name"] == "z042-LabSw-v03.pcc" and same["lines"] == 16
    # A device whose file was changed by hand: the line is found, with both versions.
    b = client.post(f"/api/projects/{pid}/devices", json={
        "name": "sw-b", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "mock.aruba.aos_switch", "management_address": "192.0.2.11"}).json()["id"]
    client.post(f"/api/devices/{b}/configs/import", json={
        "filename": "z042-LabSw-v03.pcc", "text": zone42().replace("10.169.201.65", "10.1.1.1")})
    diff = client.post(f"/api/projects/{pid}/compare-files",
                       json={"assignments": {"bhdmz": b}}).json()[0]
    assert not diff["same"] and diff["differences"] == [
        [6, "logging 10.169.201.65", "logging 10.1.1.1"]]
