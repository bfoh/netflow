"""Offline recognition of FortiOS files.

The samples are SYNTHETIC: written for these tests in the layout of FortiOS
backups and CLI scripts, with fictional names and RFC 5737 addresses. They are
not taken from any real system.
"""

import pytest
from api_helpers import FIREWALL, make_client

from undm.drivers.base import ApplyMode
from undm.drivers.fortinet.config_files import inspect_fortios_file
from undm.drivers.mock.drivers import MockArubaAOSCXDriver, MockFortiGateDriver
from undm.drivers.ssh.platforms import FortiOSSsh

BACKUP = """#config-version=FG101F-7.2.7-FW-build1577-240131:opmode=0:vdom=1:user=admin
#conf_file_ver=1234567890
#buildno=1577
#global_vdom=1

config vdom
edit root
next
end

config global
config system global
    set hostname "lab-fw-base"
    set vdom-mode multi-vdom
end
config system interface
    edit "mgmt"
        set vdom "root"
        set ip 192.0.2.99 255.255.255.0
        set allowaccess ping https ssh
    next
end
config system admin
    edit "admin"
        set accprofile "super_admin"
        set password ENC EXAMPLEONLYnotarealhash
    next
end
config certificate local
    edit "Example_Cert"
        set password ENC EXAMPLEONLYnotarealhash
        set private-key "-----BEGIN ENCRYPTED PRIVATE KEY-----
config is not a statement here
end
-----END ENCRYPTED PRIVATE KEY-----"
    next
end
end

config vdom
edit root
config system settings
end
config router static
end
end
"""

SCRIPT = """# -----------------------------------------------------------------
# Example site script. The base configuration must be restored first.
# -----------------------------------------------------------------
end
# an error message for the line above is expected
config global
  config system global
    set hostname "lab-fw-site"
    set admin-scp enable
  end
  config system admin
    edit admin
      set trusthost1 192.0.2.0 255.255.255.0
      set trusthost2 198.51.100.7 255.255.255.255
    next
  end
  config system interface
    edit "port5"
      set vdom "root"
      set ip 203.0.113.1 255.255.255.0
    next
  end
end
config vdom
  edit root
    config vpn ipsec phase1-interface
      edit "example-tunnel"
        set interface "port5"
        set psksecret example-only-not-a-secret
      next
    end
    config router static
      edit 10
        # comments may sit inside a block
        set dst 198.51.100.0 255.255.255.0
        set device "example-tunnel"
      next
    end
  next
end
"""


def test_full_backup_is_recognised_from_its_header():
    r = inspect_fortios_file(BACKUP)
    assert r.file_type == "full_backup" and r.apply_mode is ApplyMode.REPLACE
    assert r.problems == ()
    assert r.facts["platform_code"] == "FG101F"
    assert r.facts["written_by_version"] == "7.2.7" and r.facts["build"] == "1577"
    assert r.facts["vdom_mode"] == "multi-vdom"
    assert "FG101F" in r.summary and "7.2.7" in r.summary
    assert any("replaces the entire configuration" in n for n in r.notes)
    assert any("before or after a firmware upgrade" in n for n in r.notes)


def test_multi_line_keys_do_not_confuse_the_structure_check():
    # The private key above contains lines that look like statements.
    assert inspect_fortios_file(BACKUP).problems == ()


def test_secrets_are_counted_and_never_copied_into_the_report():
    for sample in (BACKUP, SCRIPT):
        r = inspect_fortios_file(sample)
        text = " ".join([r.summary, *r.notes, *r.problems, *r.facts.values()])
        assert "EXAMPLEONLY" not in text and "example-only-not-a-secret" not in text
        assert any(n.startswith("Confidential") for n in r.notes)
    backup = inspect_fortios_file(BACKUP)
    assert "2 encrypted secret(s)" in " ".join(backup.notes)
    assert "1 private key(s)" in " ".join(backup.notes)
    assert "1 secret(s) in clear text" in " ".join(inspect_fortios_file(SCRIPT).notes)


def test_cli_script_is_recognised_with_what_matters_for_running_it():
    r = inspect_fortios_file(SCRIPT)
    assert r.file_type == "cli_script" and r.apply_mode is ApplyMode.MERGE
    assert r.problems == ()
    notes = " ".join(r.notes)
    assert "Starts with a bare 'end'" in notes
    assert "multi-VDOM mode" in notes and r.facts["vdom_mode"] == "multi-vdom"
    assert "prompt changes" in notes
    assert "192.0.2.0 255.255.255.0; 198.51.100.7 255.255.255.255" in notes
    assert "'mgmt' interface" not in notes
    assert r.facts["statements"] == "35"


def test_script_that_touches_the_management_port_or_runs_commands_is_flagged():
    script = ('config system interface\n  edit "mgmt"\n    set ip 192.0.2.5 255.255.255.0\n'
              "  next\nend\nexecute reboot\nconfig firewall address\n  delete old\nend\n")
    notes = " ".join(inspect_fortios_file(script).notes)
    assert "Changes the 'mgmt' interface" in notes
    assert "1 line(s) are not configuration statements (first: line 6, 'execute ...')" in notes
    assert "1 statement(s) delete existing configuration" in notes


@pytest.mark.parametrize(("text", "expected"), [
    ("config system global\n  set hostname x\n", "never closed"),
    ("config system global\nend\nend\n", "line 3: 'end' without an open 'config' block"),
    ("config firewall address\n  next\nend\n", "line 2: 'next' without an open 'edit'"),
])
def test_unbalanced_blocks_are_problems(text, expected):
    assert any(expected in p for p in inspect_fortios_file(text).problems)


def test_other_text_is_not_mistaken_for_fortios():
    r = inspect_fortios_file('hostname "lab-2930f"\nvlan 10\n   name "users"\n   exit\n')
    assert r.file_type == "unknown" and r.apply_mode is None and r.problems


def test_drivers_say_what_they_cannot_apply_yet():
    assert MockArubaAOSCXDriver.inspect_config_file(SCRIPT) is None  # not its file format
    assert FortiOSSsh.inspect_config_file(BACKUP).blocked_reason == ""  # restored by TFTP
    assert FortiOSSsh.inspect_config_file(SCRIPT).blocked_reason == ""  # multi-VDOM script ok
    multi_line = ('config vpn certificate local\n  edit "c"\n    set certificate "-----BEGIN\n'
                  'xyz\n-----END"\n  next\nend\n')
    assert "several lines" in FortiOSSsh.inspect_config_file(multi_line).blocked_reason
    assert MockFortiGateDriver.inspect_config_file(SCRIPT).blocked_reason == ""
    assert "simulated" in MockFortiGateDriver.inspect_config_file(BACKUP).blocked_reason


def test_secret_slots_are_listed_without_values():
    r = inspect_fortios_file(SCRIPT)
    assert [(s.slot_id, s.setting, s.line) for s in r.secret_slots] == [
        ("vdom > root > vpn ipsec phase1-interface > example-tunnel > psksecret",
         "psksecret", 29)]
    assert "example-only-not-a-secret" not in repr(r)
    assert inspect_fortios_file(BACKUP).secret_slots == ()  # encrypted values are not slots


@pytest.fixture
def client():
    c, _ = make_client()
    with c:
        yield c


def _device(client):
    pid = client.post("/api/projects", json={"name": "FW files"}).json()["id"]
    did = client.post(f"/api/projects/{pid}/devices", json=FIREWALL).json()["id"]
    return pid, did


def _import(client, did, name, text):
    r = client.post(f"/api/devices/{did}/configs/import", json={"filename": name, "text": text})
    assert r.status_code == 201, r.json()
    return r.json()


def test_import_reports_what_the_file_is(client):
    pid, did = _device(client)
    base = _import(client, did, "base-example.conf", BACKUP)
    assert base["inspection"]["file_type"] == "full_backup"
    assert base["inspection"]["apply_mode"] == "replace"
    again = client.get(f"/api/configs/{base['id']}").json()
    assert again["inspection"]["summary"] == base["inspection"]["summary"]
    audit = client.get("/api/audit?limit=5").json()
    entry = next(a for a in audit if a["action"] == "config.import")
    assert entry["details"]["file_type"] == "full_backup"
    assert "EXAMPLEONLY" not in str(entry)


def test_full_backup_is_never_sent_line_by_line(client):
    pid, did = _device(client)
    base = _import(client, did, "base-example.conf", BACKUP)
    r = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "dry_run": False, "apply_mode": "merge",
        "config_versions": {did: base["id"]}})
    assert r.status_code == 409
    assert "Full FortiOS configuration backup" in r.json()["error"]


def test_broken_script_is_refused_but_a_good_one_runs_in_simulation(client):
    pid, did = _device(client)
    broken = _import(client, did, "broken.cfg", "config system global\n  set hostname x\n")
    r = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "dry_run": False, "apply_mode": "merge",
        "config_versions": {did: broken["id"]}})
    assert r.status_code == 409 and "never closed" in str(r.json()["details"])
    good = _import(client, did, "site-example.cfg", SCRIPT)
    assert good["inspection"]["blocked_reason"] == ""
    r = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [did], "dry_run": False, "apply_mode": "merge",
        "config_versions": {did: good["id"]}})
    assert r.status_code == 201, r.json()


def test_generated_and_other_vendor_files_have_no_report(client):
    pid = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    from api_helpers import SWITCH
    did = client.post(f"/api/projects/{pid}/devices", json=SWITCH).json()["id"]
    v = _import(client, did, "sw.cfg", "hostname sw1\nvlan 10\n")
    assert v["inspection"] is None


def test_simulated_fortigate_runs_the_site_flow_without_ever_holding_the_key(client):
    """The plan/approve/run flow with a secret mapping can be rehearsed in simulation."""
    import keyring
    from memory_keyring import MemoryKeyring

    from undm.drivers.mock.lab import default_lab

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    try:
        pid, did = _device(client)
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "psk"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "psk", "password": "Example-Only-Psk-77"})
        site = _import(client, did, "site-example.cfg", SCRIPT)
        slot = site["inspection"]["secret_slots"][0]["slot_id"]
        dep = client.post(f"/api/projects/{pid}/deployments", json={
            "device_ids": [did], "apply_mode": "merge", "config_versions": {did: site["id"]},
            "secrets": {did: {slot: ref["id"]}}}).json()
        client.post(f"/api/deployments/{dep['id']}/approve")
        out = client.post(f"/api/deployments/{dep['id']}/execute").json()
        assert out["state"] == "succeeded", [e["message"] for e in out["events"]]
        running = default_lab().get("10.255.0.1").running_config
        assert "set psksecret ENC <simulated>" in running
        assert "Example-Only-Psk-77" not in running
    finally:
        keyring.set_keyring(previous)
