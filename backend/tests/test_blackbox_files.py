"""Offline recognition of Black Box switch configuration files.

The sample is SYNTHETIC: written for these tests in the layout of the files the team
loads through the switch's web interface, with fictional names, RFC 5737 addresses
and an example password. It is not taken from any real system.
"""

import base64

import pytest
from api_helpers import make_client

from undm.drivers.base import ApplyMode
from undm.drivers.blackbox.config_files import inspect_blackbox_file
from undm.drivers.mock.drivers import MockBlackBoxSwitchDriver
from undm.drivers.mock.lab import default_lab

EXAMPLE_PASSWORD = "Example-Only-1"
ENCODED = base64.b64encode(EXAMPLE_PASSWORD.encode()).decode()

SAMPLE = f"""hostname lab-bbsw01
logging on
logging host 198.51.100.65
username admin privilege 15 password encrypted {ENCODED}
access management
access management 1 168 198.51.100.1 to 198.51.100.3 web telnet
access management 2 222 192.0.2.0 to 192.0.2.254 web telnet
access management 3 168 198.51.100.65 snmp
!
vlan 168,222,1001
!
ip route 0.0.0.0 0.0.0.0 198.51.100.254
ip http secure-server
no ip telnet
!
interface GigabitEthernet 1/1
 switchport access vlan 1001
 description Port-1
!
interface GigabitEthernet 1/2
 switchport trunk native vlan 168
 switchport trunk allowed vlan 168,1001
 switchport mode trunk
 description Port-2-Trunk
!
interface GigabitEthernet 1/3
 switchport access vlan 222
 description Port-3-OOBM
!
interface GigabitEthernet 1/4
 switchport access vlan 2
 shutdown
!
interface vlan 1
 no ip address
!
interface vlan 168
 ip address 198.51.100.241 255.255.255.0
!
interface vlan 222
 ip address 192.0.2.1 255.255.255.0
!
end
"""


def test_complete_configuration_is_recognised():
    r = inspect_blackbox_file(SAMPLE)
    assert r.file_type == "full_config" and r.apply_mode is ApplyMode.REPLACE
    assert r.problems == ()
    assert r.facts["hostname"] == "lab-bbsw01" and r.facts["ports"] == "4"
    assert r.facts["ports_shut_down"] == "1"


def test_where_the_switch_can_be_managed_after_loading():
    notes = " ".join(inspect_blackbox_file(SAMPLE).notes)
    assert ("VLAN 168 198.51.100.241 / 255.255.255.0 (on trunk port 1/2); "
            "VLAN 222 192.0.2.1 / 255.255.255.0 (untagged on port 1/3)") in notes
    assert "VLAN 222 192.0.2.0–192.0.2.254 (web telnet)" in notes
    assert "VLAN 168 198.51.100.65 (snmp)" in notes
    assert "Whether SSH is covered" in notes
    assert "Telnet is switched off" in notes and "HTTPS" in notes


def test_base64_password_is_flagged_and_never_shown():
    r = inspect_blackbox_file(SAMPLE)
    text = " ".join([r.summary, *r.notes, *r.problems, *r.facts.values()])
    assert "only base64-encoded: anyone with the file can read them" in text
    assert ENCODED not in text and EXAMPLE_PASSWORD not in text
    really_encrypted = SAMPLE.replace(ENCODED, "q8$Zx!")  # not valid base64
    assert "1 encrypted password(s)" in " ".join(inspect_blackbox_file(really_encrypted).notes)


def test_incomplete_and_foreign_files():
    assert "does not end with 'end'" in inspect_blackbox_file(
        SAMPLE.replace("\nend\n", "\n")).problems[0]
    other = inspect_blackbox_file('hostname "lab-2930f"\nvlan 10\n   name "users"\n   exit\n')
    assert other.file_type == "unknown" and other.apply_mode is None


@pytest.fixture
def client():
    c, _ = make_client()
    with c:
        yield c


def test_simulated_lig1014a_imports_and_loads_the_file_as_a_whole(client):
    assert MockBlackBoxSwitchDriver.inspect_config_file(SAMPLE).file_type == "full_config"
    models = {m["model_id"]: m for m in client.get("/api/device-models").json()}
    assert models["blackbox-lig1014a"]["drivers"] == ["mock.blackbox.switch"]
    pid = client.post("/api/projects", json={"name": "BB"}).json()["id"]
    did = client.post(f"/api/projects/{pid}/devices", json={
        "name": "lab-bbsw01", "manufacturer": "Black Box", "category": "switch",
        "model": "LIG1014A", "driver_id": "mock.blackbox.switch",
        "management_address": "192.0.2.1"}).json()["id"]
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "site-switch.txt", "text": SAMPLE}).json()
    assert v["inspection"]["file_type"] == "full_config"
    merge = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "apply_mode": "merge", "config_versions": {did: v["id"]}})
    assert merge.status_code == 409 and "replace mode" in merge.json()["error"]
    dep = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]}}).json()
    client.post(f"/api/deployments/{dep['id']}/approve")
    out = client.post(f"/api/deployments/{dep['id']}/execute").json()
    assert out["state"] == "succeeded", [e["message"] for e in out["events"]]
    assert default_lab().get("192.0.2.1").hostname == "lab-bbsw01"
    client.put(f"/api/devices/{did}/intent", json={"hostname": "lab-bbsw01"})
    gen = client.post(f"/api/devices/{did}/configs/generate")
    assert gen.status_code == 409 and "import a configuration file" in gen.json()["error"]
