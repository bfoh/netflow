"""Files that depend on the zone and the system: the LTE modem's configuration and the Flexi
BBU's SCF, with PCIs from the team's PCI table (D-114).

Synthetic data only: made-up systems B007 and B009, zones 41 and 42, a made-up site prefix
"ABC" and password; RFC 1918 addresses. The rules are the team's convention as shown by two
real systems' files; these tests prove the engine, not any real file."""

import io
import json
import zipfile
from urllib.parse import unquote

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.configgen import pci_table
from undm.configgen import zone as zr

PASSWORD = "Example-Only-Pass-77"  # noqa: S105 - a made-up test value


def modem(system: int, zone: int, password: str = PASSWORD) -> str:
    return (f'# example modem file\r\nexit all\r\nconfigure\r\n    system\r\n'
            f'        name "LTEmodemABCB{system:03d}-Zone{zone:03d}"\r\n    exit\r\n'
            f'            user "admin"\r\n                password "{password}"\r\n'
            f"        interface \"pdn-loopback\"\r\n            address 130.{zone}.1.221/32\r\n"
            f"        static-route-entry 10.{127 + zone}.201.65/32\r\n"
            f"            next-hop 10.{127 + zone}.202.230\r\n"
            f"    snmp community example r\r\nadmin save\r\n")  # written with CRLF


def scf(system: int, zone: int, pcis: tuple[int, int] = (1, 2),
        label: str | None = None) -> str:
    s3, z3 = f"{system:03d}", f"{zone:03d}"
    cells = "".join(
        f'    <managedObject class="NOKLTE:LNCEL" distName="MRBTS-{system}/LNBTS-1/LNCEL-{k}">\n'
        f'      <p name="cellName">eNB-B{s3}-Z{z3}-Cell{k}</p>\n'
        f'      <p name="phyCellId">{pci}</p>\n      <p name="tac">{zone}</p>\n'
        f'      <list name="drxProfile7"><item><p name="drxProfileIndex">7</p></item></list>\n'
        f"    </managedObject>\n" for k, pci in enumerate(pcis, 1))
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<raml xmlns="raml21.xsd" version="2.1">\n'
            f'  <cmData type="actual">\n'
            f'    <managedObject class="com.nokia.srbts:MRBTS" distName="MRBTS-{system}">\n'
            f'      <p name="btsName">eNB1-ABCB-{s3}-Z{z3}</p>\n'
            f'      <p name="fingerprint">B7:00:07:3D</p>\n    </managedObject>\n'
            f"{cells}"
            f'    <managedObject class="MRBTSDESC" distName="MRBTS-{system}/MRBTSDESC-0">\n'
            f'      <p name="descriptiveName">{label or f"ABCB-{s3}-Z{z3} LTE B1/B3"}</p>\n'
            f'    </managedObject>\n'
            f'    <managedObject class="IPADDRESSV4" distName="MRBTS-{system}/IPIF-1">\n'
            f'      <p name="localIpAddr">10.{127 + zone}.202.101</p>\n'
            f"    </managedObject>\n  </cmData>\n</raml>\n")


def workbook(rows: list[list[object]]) -> bytes:
    """A minimal .xlsx with one sheet (strings shared, numbers inline), as Excel writes."""
    strings: list[str] = []

    def cell(ref: str, value: object) -> str:
        if isinstance(value, int):
            return f'<c r="{ref}"><v>{value}</v></c>'
        strings.append(str(value))
        return f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    body = "".join(f'<row r="{i}">' + "".join(cell(f"{chr(65 + j)}{i}", v)
                                               for j, v in enumerate(r)) + "</row>"
                   for i, r in enumerate(rows, 1))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{body}"
                                               "</sheetData></worksheet>")
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(
            f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
    return buf.getvalue()


HEADER = ["System ID", "Compact Sector 1", "Compact Sector 2", "Spaced Sector 1",
          "Spaced Sector 2"]
TABLE = [HEADER, ["B7", 12, 13, 24, 25], ["B9", 16, 17, 32, 33], ["B10", 18, "N/A", 36, 37]]


# -- the engine ---------------------------------------------------------------------------
def test_pci_table_reads_xlsx_and_csv_and_refuses_what_it_cannot_trust():
    assert pci_table.parse(workbook(TABLE)) == {"B7": [12, 13], "B9": [16, 17],
                                                "B10": [18, None]}
    csv_text = "\n".join(";".join(str(c) for c in r) for r in TABLE).encode()
    assert pci_table.parse(csv_text)["B9"] == [16, 17]
    for bad, words in [([["Name", "x"], ["B7", 1]], "No header row"),
                       ([HEADER, ["B7", 600, 1, 1, 1]], "not a valid PCI"),
                       ([HEADER, ["B7", 1, 2, 3, 4], ["B07", 1, 2, 3, 4]], "listed twice"),
                       ([HEADER, ["Seven", 1, 2, 3, 4]], "not a system ID")]:
        with pytest.raises(pci_table.PciTableError, match=words):
            pci_table.parse(workbook(bad))
    with pytest.raises(pci_table.PciTableError, match="DOCTYPE"):
        pci_table._xml(b'<!DOCTYPE x [<!ENTITY a "b">]><x/>')  # noqa: SLF001


def test_system_rules_give_the_other_systems_files():
    b7, b9 = zr.SystemRef("B", 7), zr.SystemRef("B", 9)
    t = zr.templatize(scf(7, 41, (12, 13)).replace("\r\n", "\n"), 41, b7, cells=True)
    assert t.cells == 2 and t.counts["pci"] == 2 and t.counts["tac"] == 2
    assert zr.render(t.text, 42, b9, (16, 17)) == scf(9, 42, (16, 17))
    assert "B7:00:07:3D" in t.text  # the B + 3 digits rule leaves a hex value alone
    hexes = zr.templatize("serial 4FB007A1\nname B007-x\n", 41, b7).text
    assert "4FB007A1" in hexes and "B${sys3}-x" in hexes
    assert zr.needs(t.text) == {"system", "pci"} and zr.cells_of(t.text) == 2
    with pytest.raises(zr.ZoneError, match="needs the system"):
        zr.render(t.text, 42)
    with pytest.raises(zr.ZoneError, match="PCI table"):
        zr.render(t.text, 42, b9)
    m = zr.templatize(modem(7, 41).replace("\r\n", "\n"), 41, b7, secrets=True)
    assert PASSWORD not in m.text and m.counts["secret"] == 1 and zr.needs(m.text) == {
        "system", "secret"}
    assert zr.render(m.text, 42, b9, secret=PASSWORD) == modem(9, 42).replace("\r\n", "\n")
    assert '"${admin_password}"' in zr.render(m.text, 42, b9, keep_secret=True)
    with pytest.raises(zr.ZoneError, match="modem's login"):
        zr.render(m.text, 42, b9)
    # A zone below 100 keeps three digits in the names; the system its own form.
    out = zr.render(m.text, 7, zr.SystemRef("B", 11), secret="x")
    assert "LTEmodemABCB011-Zone007" in out and "10.134.201.65" in out
    assert zr.parse_system("b7").tag == "B007" and zr.system_from_text("x-MRBTS-9_y") == b9
    with pytest.raises(zr.ZoneError, match="Only B"):
        zr.parse_system("C7")


# -- through the API ----------------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def imp(c, role, text, filename, **kw):
    return c.post("/api/templates", json={"role": role, "filename": filename, "text": text,
                                          **kw})


def system(c, name="Lab B9z042", zone=42, system_id="b9"):
    pid = c.post("/api/projects", json={"name": name}).json()["id"]
    r = c.patch(f"/api/projects/{pid}", json={"zone": zone, "system_id": system_id})
    assert r.status_code == 200, r.text
    return pid


def table(c, rows=TABLE):
    return c.post("/api/settings/pci-mapping",
                  files={"file": ("pci.xlsx", workbook(rows), "application/octet-stream")})


def test_pci_table_import_and_lookup(client):
    assert client.get("/api/settings/pci-mapping").json() is None
    r = table(client)
    assert r.status_code == 201 and r.json()["systems"] == 3 and r.json()["cells"] == 2
    assert client.get("/api/settings/pci-mapping/b07").json() == {"system": "B007",
                                                                  "pcis": [12, 13]}
    assert client.get("/api/settings/pci-mapping/B8").status_code == 404
    bad = client.post("/api/settings/pci-mapping", files={"file": ("x.csv", b"nothing")})
    assert bad.status_code == 400
    entry = next(a for a in client.get("/api/audit").json()
                 if a["action"] == "settings.pci_mapping")
    assert entry["details"]["systems"] == 3 and "rows" not in entry["details"]


def test_import_checks_against_another_system_and_keeps_no_password(client):
    r = imp(client, "modem", modem(7, 41), "LTEModemz041.txt",
            verify={"filename": "LTEModemz42.txt", "text": modem(9, 42)})
    assert r.status_code == 201, r.text
    t = r.json()["template"]
    assert t["reference_system"] == "B007" and t["verified_system"] == "B009"
    assert t["reference_zone"] == 41 and t["verified_zone"] == 42 and r.json()["verified_bytes"]
    assert t["line_ending"] == "crlf" and t["filename"] == "LTEModemz${zone}.txt"
    assert PASSWORD not in json.dumps(client.get("/api/audit").json())
    pre = client.get("/api/templates/modem/preview?zone=42&system=B009").json()
    assert PASSWORD not in pre["text"] and '"${admin_password}"' in pre["text"]
    # The SCF: one line differs by the team's own hand (a free-text site label).
    other = {"filename": "Full_scf_MRBTS-9_eNB1-ABCB-009-Z042_20260101-0900.xml",
             "text": scf(9, 42, (90, 91), label="Test site LTE B1/B3")}
    name = "Full_scf_MRBTS-7_eNB1-ABCB-007-Z041_20260102-1000.xml"
    r = imp(client, "bbu_scf", scf(7, 41, (5, 6)), name, verify=other)
    assert r.status_code == 409 and "1 line(s) differ" in r.json()["error"]
    assert "descriptiveName" in r.json()["details"][0]
    r = imp(client, "bbu_scf", scf(7, 41, (5, 6)), name, verify=other, accept_differences=True)
    assert r.status_code == 201 and len(r.json()["accepted"]) == 1
    t = r.json()["template"]
    assert t["counts"]["accepted_differences"] == 1 and t["verified_system"] == "B009"
    assert t["filename"] == "Full_scf_MRBTS-${sys}_eNB1-ABCB-${sys3}-Z${zone3}_${stamp}.xml"
    no_cells = imp(client, "bbu_scf", scf(7, 41).replace("phyCellId", "x"), name)
    assert no_cells.status_code == 400 and "phyCellId" in no_cells.json()["error"]
    unknown = imp(client, "modem", modem(7, 41).replace("ABCB007", "ABC"), "modem.txt", zone=41)
    assert unknown.status_code == 400 and "Say which system" in unknown.json()["error"]


def test_a_systems_files_byte_for_byte_with_pcis_from_the_table_and_the_modems_login(client):
    imp(client, "modem", modem(7, 41), "LTEModemz041.txt")
    imp(client, "bbu_scf", scf(7, 41, (5, 6)),
        "Full_scf_MRBTS-7_eNB1-ABCB-007-Z041_20260102-1000.xml")
    pid = system(client)
    assert client.get(f"/api/projects/{pid}").json()["system_id"] == "B009"
    assert client.patch(f"/api/projects/{pid}", json={"system_id": "X1"}).status_code == 422
    dev = client.post(f"/api/projects/{pid}/devices", json={
        "name": "lab-modem", "manufacturer": "Nokia", "category": "router",
        "model": "7705 SAR-Hmc", "driver_id": "mock.nokia.sar"}).json()["id"]
    body = {"assignments": {"modem": dev}}
    # No PCI table, no modem login yet: both are left out, and the reasons say why.
    r = client.post(f"/api/projects/{pid}/files.zip", json=body)
    skipped = json.loads(unquote(r.headers["x-undm-skipped"]))
    assert r.status_code == 200 and len(skipped) == 2
    assert any("PCI table" in s for s in skipped) and any("modem's login" in s for s in skipped)
    table(client)
    ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
    client.put(f"/api/credential-refs/{ref['id']}/secret",
               json={"username": "admin", "password": PASSWORD})
    client.patch(f"/api/devices/{dev}", json={"credential_ref_id": ref["id"]})
    r = client.post(f"/api/projects/{pid}/files.zip", json=body)
    assert json.loads(unquote(r.headers["x-undm-skipped"])) == []
    files = zipfile.ZipFile(io.BytesIO(r.content))
    names = files.namelist()  # in the roles' order: the modem, then the SCF
    assert names[0] == "LTEModemz42.txt" and names[1].startswith(
        "Full_scf_MRBTS-9_eNB1-ABCB-009-Z042_") and names[1].endswith(".xml")
    assert files.read("LTEModemz42.txt") == modem(9, 42).encode()  # CRLF, its own password
    assert files.read(names[1]) == scf(9, 42, (16, 17)).encode()  # PCIs from the table
    export = next(a for a in client.get("/api/audit").json()
                  if a["action"] == "template.files_export")
    assert export["details"]["modem_login_used"] is True
    assert PASSWORD not in json.dumps(export)
    # Settings: no system's login, so the modem file is not handed out there.
    assert client.get("/api/templates/modem/file?zone=42&system=B9").status_code == 409
    r = client.get("/api/templates/files.zip?zone=42&system=B9")
    in_settings = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(in_settings) == 1 and in_settings[0].startswith("Full_scf_MRBTS-9_")
    assert "modem's login" in unquote(r.headers["x-undm-skipped"])
    # Generated onto the modem device, its file keeps the password slot (filled at load).
    made = client.post(f"/api/projects/{pid}/generate-files", json=body)
    assert made.status_code == 201, made.text
    text = client.get(f"/api/configs/{made.json()[0]['version_id']}").json()["text"]
    assert PASSWORD not in text and '"${admin_password}"' in text and "ABCB009-Zone042" in text
    compared = client.post(f"/api/projects/{pid}/compare-files", json=body).json()[0]
    assert compared["file_name"] is None  # only the generated file is on the device


def test_the_system_travels_with_its_export(client):
    pid = system(client)
    package = client.get(f"/api/projects/{pid}/export").content
    out = client.post("/api/systems/import", files={"file": ("p.undm", package)},
                      data={"name": "Lab copy"}).json()
    assert client.get(f"/api/projects/{out['project']['id']}").json()["system_id"] == "B009"
