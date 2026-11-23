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
    assert "sets the switch's login" in notes and "here without a value" in notes
    assert "choose the login valid after loading" in notes
    assert "1 SNMP community string(s)" in notes
    assert "Example staging file" not in notes  # comment lines are never quoted


def test_duplicate_vlan_is_reported():
    notes = " ".join(inspect_aos_switch_file(sample(vlan_twice=True)).notes)
    assert "VLAN 168 is defined 2 times (names 'DMZ', 'OTHER'; the last one wins)" in notes


def test_address_after_loading_follows_the_subnet():
    assert address_after_loading(sample(), "192.168.1.2") == "192.168.1.1"  # temporary address
    assert address_after_loading(sample(), "192.168.1.1") == "192.168.1.1"
    assert address_after_loading(sample(), "203.0.113.5") is None  # no subnet in common


def test_load_message_says_where_to_connect_after_the_restart():
    """Bench 2026-11-23: the bootstrap used another port than the file's OOBM port."""
    from undm.drivers.aruba.config_files import where_after_loading

    assert where_after_loading(sample(), "192.168.1.1") == \
        "192.168.1.1 (VLAN 222, untagged on port 2)"
    assert where_after_loading(sample(), "203.0.113.5") is None


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


def test_switch_restarting_with_a_silent_session_is_not_waited_for(rig):
    """Bench 2026-11-23: after taking the file the switch restarted, but the SSH session
    stayed open and silent; UNDM waited for the transfer timeout (40 minutes)."""
    import time

    rig.switch.silent_restart = True
    began = time.monotonic()
    r = rig.driver.apply_configuration(sample(), ApplyMode.REPLACE)
    assert r.ok, (r.message, r.diagnostics)
    assert time.monotonic() - began < 10
    assert "is restarting (the session went quiet)" in r.message
    assert r.data["restarting"] is True and rig.switch.restarts == 1


def test_save_question_during_the_load_is_answered_no(rig):
    """\"y\" would write the old running configuration over the file just fetched."""
    rig.switch.ask_save_before_load = True
    r = rig.driver.apply_configuration(sample(), ApplyMode.REPLACE)
    assert r.ok, (r.message, r.diagnostics)
    assert rig.switch.keys == ["n", "y"]
    assert rig.switch.hostname == "lab-oobm-sw01"  # the switch started with the file


def test_switch_back_at_prompt_without_the_file_is_not_restarted(rig):
    rig.switch.config_load_mode = "prompt"
    rig.switch.refuse_config = True
    r = rig.driver.apply_configuration(sample(), ApplyMode.REPLACE)
    assert not r.ok
    assert "startup configuration does not contain it" in r.message
    assert 'no hostname "lab-oobm-sw01"' in r.message
    assert rig.switch.restarts == 0  # never restarted into the old configuration
    assert "Configuration file not accepted" in r.diagnostics["device_output"]


def test_switch_back_at_prompt_with_the_file_is_restarted_by_undm(rig):
    rig.switch.config_load_mode = "prompt"
    r = rig.driver.apply_configuration(sample(), ApplyMode.REPLACE)
    assert r.ok, (r.message, r.diagnostics)
    assert "show config" in rig.switch.commands
    assert "UNDM restarted it" in r.message and rig.switch.restarts == 1


def test_file_is_loaded_into_startup_and_the_switch_restarts(rig):
    text = sample(oobm_address="127.0.0.2", mask="255.0.0.0")  # same subnet as 127.0.0.1
    r = rig.driver.apply_configuration(text, ApplyMode.REPLACE)
    assert r.ok, (r.message, r.diagnostics)
    assert {k: r.data[k] for k in ("restarting", "address_after")} == \
        {"restarting": True, "address_after": "127.0.0.2"}
    assert r.data["notes"][0].startswith('switch output during the load (UNDM answered "y"): ')
    assert "Device may be rebooted" in r.data["notes"][0] and "\r" not in r.data["notes"][0]
    assert "after the restart it answers at 127.0.0.2 (VLAN 222, untagged on port 2)" in r.message
    assert 'is restarting ("Rebooting switch")' in r.message
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
        # The sample file is HTTPS-only: the project needs a certificate subject (D-053).
        assert client.patch(f"/api/projects/{pid}",
                            json={"certificate_subject": SUBJECT}).status_code == 200
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
    assert "it answers at 127.0.0.2 (VLAN 222" in events and "same serial number" in events
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


def test_api_login_after_loading_is_used_and_kept(api):
    """The team's files set the approved manager password (product owner, 2026-11-19)."""
    client, pid, did, switch, hub = api
    switch.password_after_load = "Example-Only-Approved-1"
    after = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
    client.put(f"/api/credential-refs/{after['id']}/secret",
               json={"username": "manager", "password": "Example-Only-Approved-1"})
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "oobm-switch.pcc", "text": sample()}).json()
    dep = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]},
        "credentials_after": {did: after["id"]}}).json()
    assert dep["targets"][0]["credential_after_ref_id"] == after["id"]
    client.post(f"/api/deployments/{dep['id']}/approve")
    out = client.post(f"/api/deployments/{dep['id']}/execute").json()
    events = " | ".join(e["message"] for e in out["events"])
    assert out["state"] == "succeeded", events
    assert "logging in with the credential chosen for after loading" in events
    assert client.get(f"/api/devices/{did}").json()["credential_ref_id"] == after["id"]
    audit = client.get("/api/audit?limit=50").json()
    assert any(a["action"] == "device.credential_changed" for a in audit)
    assert "Example-Only-Approved-1" not in repr(audit) + repr(out)


def test_api_without_the_login_after_loading_the_failure_says_why(api):
    client, pid, did, switch, hub = api
    switch.password_after_load = "Example-Only-Approved-1"
    out = _load(client, pid, did, sample())
    assert out["state"] == "recovery_required"
    assert "Authentication failed" in out["targets"][0]["message"]


def test_api_unknown_login_after_loading_is_refused_at_planning(api):
    client, pid, did, switch, hub = api
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "oobm-switch.pcc", "text": sample()}).json()
    r = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]},
        "credentials_after": {did: "no-such-credential"}})
    assert r.status_code == 409 and "credential not found" in r.json()["error"]


# -- HTTPS certificate before loading (team commands, questions from a real unit) ---------
SUBJECT = {"common_name": "lab-cn", "org_unit": "Example Unit", "org_name": "Example Org",
           "locality": "Example City", "state": "", "country": "XX",
           "profile_name": "Profile", "certificate_name": "certificate"}


def test_certificate_is_created_with_the_teams_commands(rig):
    r = rig.driver.prepare_before_apply(sample(), ApplyMode.REPLACE,
                                        {"certificate_subject": SUBJECT})
    assert r is not None and r.ok, (r.message, r.diagnostics)
    assert "certificate 'certificate' created" in r.message
    assert rig.switch.keys == ["lab-cn", "Example Unit", "Example Org", "Example City", "", "XX"]
    assert rig.switch.subject["Country(C)"] == "XX" and rig.switch.subject["State(ST)"] == ""
    assert rig.switch.certificates == {"certificate"} and rig.switch.web_ssl
    assert rig.switch.saves == 1
    sent = [c for c in rig.switch.commands if not c.startswith("show")]
    assert sent == ["configure", "crypto pki identity-profile Profile subject",
                    "crypto pki enroll-self-signed certificate-name certificate",
                    "web-management ssl", "end", "write memory"]


def test_existing_certificate_is_fine(rig):
    rig.switch.certificates.add("certificate")
    rig.switch.subject = {"x": "y"}
    r = rig.driver.prepare_before_apply(sample(), ApplyMode.REPLACE,
                                        {"certificate_subject": SUBJECT})
    assert r is not None and r.ok and "already existed" in r.message


def test_no_subject_means_a_warning_and_nothing_sent(rig):
    r = rig.driver.prepare_before_apply(sample(), ApplyMode.REPLACE, {})
    assert r is not None and r.ok and "no certificate subject" in r.message
    assert "Create it by hand" in r.data["warnings"][0]
    assert not [c for c in rig.switch.commands if not c.startswith("show")]


def test_certificate_step_only_when_the_file_needs_it(rig):
    plain = sample().replace("no web-management\n", "")
    assert rig.driver.prepare_before_apply(plain, ApplyMode.REPLACE,
                                           {"certificate_subject": SUBJECT}) is None
    assert rig.driver.prepare_before_apply(sample(), ApplyMode.MERGE,
                                           {"certificate_subject": SUBJECT}) is None


def test_rejected_certificate_command_stops_before_the_file(rig):
    rig.switch.reject.add("web-management ssl")
    r = rig.driver.prepare_before_apply(sample(), ApplyMode.REPLACE,
                                        {"certificate_subject": SUBJECT})
    assert r is not None and r.status is ResultStatus.FAILED
    assert "rejected 'web-management ssl'" in r.message and "not sent" in r.message
    assert "write memory" not in rig.switch.commands


def test_api_certificate_is_created_before_the_file_is_loaded(api):
    client, pid, did, switch, hub = api
    r = client.patch(f"/api/projects/{pid}", json={"certificate_subject": SUBJECT})
    assert r.status_code == 200 and r.json()["certificate_subject"]["common_name"] == "lab-cn"
    bad = client.patch(f"/api/projects/{pid}",
                       json={"certificate_subject": {**SUBJECT, "org_name": 'has"quote'}})
    assert bad.status_code == 422
    out = _load(client, pid, did, sample())
    messages = [e["message"] for e in out["events"]]
    assert out["state"] == "succeeded", messages
    cert = next(i for i, m in enumerate(messages) if "HTTPS certificate 'certificate'" in m)
    fetched = next(i for i, m in enumerate(messages) if "fetched the file" in m)
    assert cert < fetched and switch.certificates == {"certificate"}
    notice = next(i for i, m in enumerate(messages) if m.startswith("loading the file: "))
    assert cert < notice < fetched  # people are told to expect the restart before it starts
    assert messages.count(next(m for m in messages if "fetched the file" in m)) == 1
    assert "back after the restart; configuration saved" in messages
    # The configuration read back from the switch is kept: view it, compare it with the file.
    t = out["targets"][0]
    after = client.get(f"/api/configs/{t['after_version_id']}").json()
    assert 'hostname "lab-oobm-sw01"' in after["text"]
    assert after["reference"].startswith("after deployment ")
    diff = client.get("/api/configs/diff", params={"from_version": t["config_version_id"],
                                                   "to_version": t["after_version_id"]})
    assert diff.status_code == 200, diff.text
    copy_at = next(i for i, c in enumerate(switch.commands) if c.startswith("copy tftp"))
    assert switch.commands.index("web-management ssl") < copy_at


def test_api_https_only_file_needs_the_certificate_subject(api):
    """Team (web page) and bench 2026-11-23: without the HTTPS certificate the switch does
    not take the file and keeps its old configuration, so UNDM refuses to start."""
    client, pid, did, switch, hub = api
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "oobm-switch.pcc", "text": sample()}).json()
    plan = {"device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]}}
    dep = client.post(f"/api/projects/{pid}/deployments", json=plan).json()
    assert dep["state"] == "awaiting_approval"
    client.post(f"/api/deployments/{dep['id']}/approve")
    cleared = client.patch(f"/api/projects/{pid}", json={"certificate_subject": None})
    assert cleared.status_code == 200 and not cleared.json()["certificate_subject"]
    r = client.post(f"/api/deployments/{dep['id']}/execute")
    assert r.status_code == 409, r.text
    assert "without an HTTPS certificate" in r.json()["error"]
    assert "Project settings → HTTPS certificate" in r.json()["error"]
    assert not any(c.startswith("copy") for c in switch.commands)  # nothing was sent
    refused = client.post(f"/api/projects/{pid}/deployments", json=plan)
    assert refused.status_code == 409 and "set it first" in refused.json()["error"]


def test_verification_warnings_are_grouped(rig):
    text = sample() + "interface 5\n   no lacp\n   exit\ninterface 6\n   no lacp\n   exit\n"
    rig.switch.running_config = text.replace("   no lacp\n", "")
    rig.switch.hostname = "lab-oobm-sw01"
    r = rig.driver.verify_configuration(text, ApplyMode.REPLACE)
    assert r is not None and r.ok
    (warning,) = r.data["warnings"]
    assert "no lacp (x2)" in warning and "line(s) of the file are not shown" in warning


def test_api_load_with_a_silent_restart_succeeds(api):
    client, pid, did, switch, hub = api
    switch.silent_restart = True
    out = _load(client, pid, did, sample())
    messages = [e["message"] for e in out["events"]]
    assert out["state"] == "succeeded", messages
    assert any("the session went quiet" in m for m in messages)
    assert any(m.startswith("back after loading: hostname lab-oobm-sw01") for m in messages)
