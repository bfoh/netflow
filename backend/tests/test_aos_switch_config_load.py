"""2930F complete configuration files: offline check and loading over TFTP.

The sample file is SYNTHETIC: written for these tests in the layout of the team's
2930F files (header line, ';' comments, interfaces, VLANs, authorized managers, the
TFTP client switched off, bare password lines), with fictional names and RFC 1918 /
RFC 5737 addresses. The switch is a fake (synthetic wording) that really downloads
the file from UNDM's TFTP server. Proves the procedure's decisions, not hardware.
"""

from dataclasses import dataclass

import pytest
from fake_aos_switch import FakeArubaSwitch
from fake_netmiko import Scenario, factory_for

from undm.drivers.aruba.config_files import address_after_loading, inspect_aos_switch_file
from undm.drivers.base import ApplyMode, Credentials, DeviceTarget, ResultStatus
from undm.drivers.ssh.base import SshCliDriver
from undm.drivers.ssh.platforms import ArubaOSSwitchSsh
from undm.transfer.hub import TransferHub


def sample(oobm_address="192.168.1.1", mask="255.255.255.0", vlan_twice=False):
    return f"""; JL260A Configuration Editor; Created on release #WC.16.08.0026
; Ver #14:00.00.00.00:04
; Example staging file - comments may name sites and addresses
; Caution! https certificate shall be created before this configuration is loaded.
hostname "lab-oobm-sw01"
module 1 type jl260a
no telnet-server
web-management ssl
no web-management
ip ssh
ip ssh filetransfer
ip authorized-managers 192.168.1.1 255.255.255.0 access manager
ip authorized-managers 198.51.100.10 255.255.255.255 access manager access-method ssh
interface 1
   name "uplink"
   exit
interface 2
   name "OOBM"
   exit
interface 3
  disable
  exit
snmp-server community "x" Operator
vlan 1
   name "DEFAULT_VLAN"
   no untagged 1-3
   no ip address
   exit
vlan 168
   name "DMZ"
   tagged 1
   ip address 198.51.100.240 255.255.255.0
   exit
vlan 222
   name "OOBM_VLAN"
   untagged 2
   ip address {oobm_address} {mask}
   exit
""" + ("""vlan 168
   name "OTHER"
   exit
""" if vlan_twice else "") + """no tftp client
no tftp server
password manager
password operator
"""


def test_complete_file_is_described_without_secrets_or_comments():
    r = inspect_aos_switch_file(sample())
    assert r.file_type == "full_config" and r.apply_mode is ApplyMode.REPLACE
    assert r.facts["product_number"] == "JL260A"
    assert r.facts["written_by_release"] == "WC.16.08.0026"
    assert r.facts["hostname"] == "lab-oobm-sw01" and r.facts["ports"] == "3"
    notes = " ".join(r.notes)
    assert ("VLAN 168 198.51.100.240 / 255.255.255.0 (tagged on port 1); "
            "VLAN 222 192.168.1.1 / 255.255.255.0 (untagged on port 2)") in notes
    assert "192.168.1.1 / 255.255.255.0 (manager, all methods)" in notes
    assert "HTTPS-only" in notes and "comments say to create it before loading" in notes
    assert "switches off the switch's TFTP client" in notes
    assert "'password manager' and 'password operator' without a value" in notes
    assert "1 SNMP community string(s)" in notes
    assert "Example staging file" not in notes  # comment lines are never quoted


def test_duplicate_vlan_is_reported():
    notes = " ".join(inspect_aos_switch_file(sample(vlan_twice=True)).notes)
    assert "VLAN 168 is defined 2 times (names 'DMZ', 'OTHER'; the last one wins)" in notes


def test_address_after_loading_follows_the_subnet():
    assert address_after_loading(sample(), "192.168.1.2") == "192.168.1.1"  # temporary address
    assert address_after_loading(sample(), "192.168.1.1") == "192.168.1.1"
    assert address_after_loading(sample(), "203.0.113.5") is None  # no subnet in common


@dataclass
class Rig:
    driver: ArubaOSSwitchSsh
    switch: FakeArubaSwitch
    scenario: Scenario


@pytest.fixture
def rig(monkeypatch):
    hub = TransferHub("127.0.0.1", 0)
    switch = FakeArubaSwitch(tftp_port=lambda: hub.port)
    sc = Scenario(prompt="lab-2930f#", device=switch)
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory_for(sc)))
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.01)
    monkeypatch.setattr(ArubaOSSwitchSsh, "question_timeout", 0.3)
    monkeypatch.setattr(ArubaOSSwitchSsh, "reboot_quiet_timeout", 0.3)
    with hub.session() as files:
        d = ArubaOSSwitchSsh(DeviceTarget("d1", "127.0.0.1", None), Credentials("manager", ""))
        d.file_server = files
        assert d.connect().ok
        yield Rig(d, switch, sc)


def test_file_is_loaded_into_startup_and_the_switch_restarts(rig):
    text = sample(oobm_address="127.0.0.2", mask="255.0.0.0")  # same subnet as 127.0.0.1
    r = rig.driver.apply_configuration(text, ApplyMode.REPLACE)
    assert r.ok, (r.message, r.diagnostics)
    assert r.data == {"restarting": True, "address_after": "127.0.0.2"}
    assert "it will answer at 127.0.0.2" in r.message
    assert rig.driver.target.management_address == "127.0.0.2"
    assert rig.switch.keys == ["y"] and rig.switch.restarts == 1
    assert rig.switch.hostname == "lab-oobm-sw01" and rig.switch.startup_config == text
    assert any(c.startswith("copy tftp startup-config 127.0.0.1 undm-") and c.endswith(" unix")
               for c in rig.switch.commands)
    assert not rig.driver.connect().ok  # still restarting
    assert rig.driver.connect().ok
    host = [c for c in rig.scenario.calls if c[0] == "connect"][-1][1]["host"]
    assert host == "127.0.0.2"  # reconnected at the address the file set
    v = rig.driver.verify_configuration(text, ApplyMode.REPLACE)
    assert v.ok and "hostname lab-oobm-sw01" in v.message
    assert "lines of the file appear" in v.message


def test_when_the_switch_does_not_restart_itself_the_old_config_is_never_saved(rig):
    rig.switch.config_load_mode = "prompt"  # copies, returns to the prompt, running != startup
    r = rig.driver.apply_configuration(sample(), ApplyMode.REPLACE)
    assert r.ok, (r.message, r.diagnostics)
    assert rig.switch.saved_on_reboot is False  # "save current configuration?" -> n
    assert rig.switch.hostname == "lab-oobm-sw01"  # restarted into the new file
    assert "boot system flash primary" in rig.switch.commands


def test_file_for_another_model_is_refused(rig):
    r = rig.driver.apply_configuration(sample().replace("JL260A", "JL259A"), ApplyMode.REPLACE)
    assert r.status is ResultStatus.FAILED and "written for a JL259A" in r.message
    assert not any(c.startswith("copy") for c in rig.switch.commands)


def test_hostname_mismatch_fails_verification(rig):
    assert rig.driver.apply_configuration(sample(), ApplyMode.REPLACE).ok
    rig.switch.hostname = "someone-else"
    rig.driver.connect()
    rig.driver.connect()
    v = rig.driver.verify_configuration(sample(), ApplyMode.REPLACE)
    assert v.status is ResultStatus.FAILED and "the file sets lab-oobm-sw01" in v.message


# -- through the API --------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_path):
    import keyring
    from api_helpers import make_client
    from memory_keyring import MemoryKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.01)
    monkeypatch.setattr(ArubaOSSwitchSsh, "question_timeout", 0.3)
    monkeypatch.setattr(ArubaOSSwitchSsh, "reboot_quiet_timeout", 0.3)
    client, _ = make_client(data_dir=str(tmp_path), tftp_host="127.0.0.1", tftp_port=0,
                            firmware_reboot_wait_seconds=0, firmware_reboot_wait_attempts=4,
                            enable_real_device_writes=True)
    with client:
        hub = client.app.state.transfer_hub
        switch = FakeArubaSwitch(tftp_port=lambda: hub.port)
        switch.serial = "SG00FAKE01"
        scenario = Scenario(prompt="lab-2930f#", device=switch)
        monkeypatch.setattr(SshCliDriver, "connection_factory",
                            staticmethod(factory_for(scenario)))
        pid = client.post("/api/projects", json={"name": "2930F"}).json()["id"]
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "m"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "manager", "password": ""})
        did = client.post(f"/api/projects/{pid}/devices", json={
            "name": "lab-2930f", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
            "os_family": "ArubaOS-Switch", "driver_id": "ssh.aruba.aos_switch",
            "environment": "lab", "management_address": "127.0.0.1",
            "credential_ref_id": ref["id"]}).json()["id"]
        yield client, pid, did, switch, hub
    keyring.set_keyring(previous)


def _load(client, pid, did, text):
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "oobm-switch.pcc", "text": text}).json()
    assert v["inspection"]["apply_mode"] == "replace"
    dep = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]}}).json()
    assert dep["state"] == "awaiting_approval", dep
    client.post(f"/api/deployments/{dep['id']}/approve")
    return client.post(f"/api/deployments/{dep['id']}/execute").json()


def test_api_load_follows_the_new_address_and_checks_identity(api):
    client, pid, did, switch, hub = api
    out = _load(client, pid, did, sample(oobm_address="127.0.0.2", mask="255.0.0.0"))
    events = " | ".join(e["message"] for e in out["events"])
    assert out["state"] == "succeeded", events
    assert "it will answer at 127.0.0.2" in events and "same serial number" in events
    assert client.get(f"/api/devices/{did}").json()["management_address"] == "127.0.0.2"
    audit = client.get("/api/audit?limit=50").json()
    moved = next(a for a in audit if a["action"] == "device.address_changed")
    assert moved["details"]["from"] == "127.0.0.1" and moved["details"]["to"] == "127.0.0.2"
    start = next(a for a in audit if a["action"] == "deployment.execute.start")
    assert start["details"]["tftp"] is True and not hub.running


def test_api_another_switch_answering_after_the_restart_is_not_accepted(api):
    client, pid, did, switch, hub = api
    switch.serial_after_restart = "SG00OTHER9"  # e.g. a second switch already at that address
    out = _load(client, pid, did, sample())
    assert out["state"] == "recovery_required", [e["message"] for e in out["events"]]
    assert "a different device answers" in out["targets"][0]["message"]
    assert client.get(f"/api/devices/{did}").json()["management_address"] == "127.0.0.1"
