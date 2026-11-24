"""Black Box LIG1014A SSH driver (read-only, D-074) against a fake switch whose output
layout is the real unit's (see fake_lig1014a.py)."""

import pytest
from fake_lig1014a import FakeLig1014A
from fake_netmiko import Scenario, factory_for

from undm.drivers.base import ApplyMode, Credentials, DeviceTarget, ResultStatus
from undm.drivers.blackbox.lig1014a_ssh import BlackBoxLig1014aSsh
from undm.drivers.registry import default_registry
from undm.drivers.ssh.base import SshCliDriver


@pytest.fixture
def switch(monkeypatch):
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.005)
    monkeypatch.setattr(BlackBoxLig1014aSsh, "command_quiet", 0.3)
    sw = FakeLig1014A()
    monkeypatch.setattr(SshCliDriver, "connection_factory",
                        staticmethod(factory_for(Scenario(device=sw))))
    return sw


def driver(password=""):
    return BlackBoxLig1014aSsh(DeviceTarget("bb1", "192.0.2.1", None),
                               Credentials("admin", password))


def test_factory_login_with_the_empty_password(switch):
    d = driver()
    assert d.connect().ok
    assert driver("wrong").connect().diagnostics.get("login_refused") is True


def test_facts_from_show_version_use_the_mac_as_identity(switch):
    d = driver()
    d.connect()
    r = d.get_device_facts()
    assert r.ok, r.message
    f = r.data
    assert (f.vendor, f.model, f.os_version) == ("Black Box", "LIG1014A", "v00.01.00")
    assert f.serial_number == "00-11-22-33-44-55" and f.hostname == ""
    assert "MAC address" in f.extra["identity"]
    assert f.extra["active_image"] == "LIG1014A_v00.01.00.dat (primary) v00.01.00"
    assert f.extra["port_count"] == "14"
    assert switch.commands == ["show version"]  # nothing else is sent (no paging commands)


def test_a_serial_number_is_used_when_the_unit_reports_one(switch):
    switch.serial, switch.hostname = "LIG00TEST", "lab-bb"
    d = driver()
    d.connect()
    f = d.get_device_facts().data
    assert f.serial_number == "LIG00TEST" and f.hostname == "lab-bb"
    assert f.extra["identity"] == "serial number"


def test_backup_is_the_running_configuration_without_the_banner(switch):
    d = driver()
    d.connect()
    r = d.backup_configuration()
    assert r.ok, r.message
    text = r.data.text
    assert text.startswith("username admin privilege 15 password none")
    assert text.rstrip().endswith("end") and "Building configuration" not in text


def test_long_output_continues_at_the_switchs_page_prompt(switch):
    """Bench 2026-11-24: 'show version' paused at "-- more --, next page: Space, continue:
    g, quit: ^C". UNDM presses 'g' (the switch's own option) and removes the pager line."""
    switch.page_after = 12
    d = driver()
    d.connect()
    f = d.get_device_facts()
    assert f.ok, f.message
    assert f.data.model == "LIG1014A" and f.data.serial_number == "00-11-22-33-44-55"
    assert switch.keys == ["g"]
    r = d.backup_configuration()
    assert r.ok, r.message
    text = r.data.text
    assert "more" not in text and "\x08" not in text
    assert "\ninterface GigabitEthernet 1/3\n description Port-3\n" in text  # indentation kept
    assert text.rstrip().endswith("end")


def test_an_incomplete_read_is_never_stored(switch):
    switch.stall_config = True
    d = driver()
    d.connect()
    r = d.backup_configuration()
    assert r.status is ResultStatus.FAILED and "no prompt" in r.message


def test_registered_and_listed_for_the_lig1014a():
    assert "ssh.blackbox.lig1014a" in default_registry()
    from undm.inventory.catalog import CATALOG
    model = next(m for m in CATALOG if m.model == "LIG1014A")
    assert "ssh.blackbox.lig1014a" in model.drivers


def test_a_failed_ssh_handshake_is_not_reported_as_unreachable(monkeypatch):
    """Bench 2026-11-24: Test connection said "Timed out ... unreachable" although PuTTY
    logged in: Netmiko reports a failed handshake (no common SSH method) as a timeout."""
    from netmiko.exceptions import NetmikoTimeoutException

    def factory(**kwargs):
        raise NetmikoTimeoutException(
            "A paramiko SSHException occurred during connection creation:\n\n"
            "Incompatible ssh peer (no acceptable kex algorithm)")
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory))
    r = driver().connect()
    assert r.status is ResultStatus.FAILED and r.diagnostics.get("ssh_handshake") is True
    assert "SSH handshake failed" in r.message and "no acceptable kex algorithm" in r.message


def test_older_ssh_methods_only_for_the_lig1014a(monkeypatch):
    """Bench 2026-11-24: "Incompatible ssh peer (no acceptable host key)" with paramiko 5.
    The LIG1014A may use the older methods; other drivers keep them switched off."""
    from fake_netmiko import Scenario as Sc
    from fake_netmiko import factory_for as ff

    from undm.drivers.fortinet.fortios_ssh import FortiOSSsh
    from undm.drivers.ssh.platforms import ArubaOSSwitchSsh
    seen = {}
    for cls in (BlackBoxLig1014aSsh, ArubaOSSwitchSsh, FortiOSSsh):
        sc = Sc()
        monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(ff(sc)))
        cls(DeviceTarget("d", "192.0.2.1", None), Credentials("admin", "x")).connect()
        seen[cls.__name__] = sc.calls[0][1].get("disabled_algorithms")
    assert seen["BlackBoxLig1014aSsh"] is None
    assert seen["FortiOSSsh"] is None  # Netmiko's own FortiGate choice is kept
    assert "ssh-rsa" in seen["ArubaOSSwitchSsh"]["keys"]
    assert "diffie-hellman-group14-sha1" in seen["ArubaOSSwitchSsh"]["kex"]


# -- loading the team's file (D-077) --------------------------------------------------------
APPROVED = "Example-Only-Approved-9"


@pytest.fixture
def api(monkeypatch, tmp_path):
    import keyring
    from api_helpers import make_client
    from memory_keyring import MemoryKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.005)
    monkeypatch.setattr(BlackBoxLig1014aSsh, "command_quiet", 0.5)
    client, _ = make_client(data_dir=str(tmp_path), tftp_host="127.0.0.1", tftp_port=0,
                            firmware_reboot_wait_seconds=0, firmware_reboot_wait_attempts=4,
                            enable_real_device_writes=True)
    with client:
        hub = client.app.state.transfer_hub
        sw = FakeLig1014A(tftp_port=lambda: hub.port, password_after_load=APPROVED,
                          page_after=20)
        monkeypatch.setattr(SshCliDriver, "connection_factory",
                            staticmethod(factory_for(Scenario(device=sw))))
        pid = client.post("/api/projects", json={"name": "BB"}).json()["id"]
        refs = {}
        for name, pw in (("factory", ""), ("approved", APPROVED)):
            refs[name] = client.post(f"/api/projects/{pid}/credential-refs",
                                     json={"name": name}).json()["id"]
            client.put(f"/api/credential-refs/{refs[name]}/secret",
                       json={"username": "admin", "password": pw})
        did = client.post(f"/api/projects/{pid}/devices", json={
            "name": "lab-bb", "manufacturer": "Black Box", "category": "switch",
            "model": "LIG1014A", "os_family": "Black Box managed switch",
            "driver_id": "ssh.blackbox.lig1014a", "environment": "lab",
            "management_address": "127.0.0.1", "credential_ref_id": refs["factory"]}).json()
        assert "id" in did, did
        yield client, pid, did["id"], sw, refs, hub
    keyring.set_keyring(previous)


def _load(client, pid, did, refs, after=True):
    from test_blackbox_files import SAMPLE
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "lab-bbsw.txt", "text": SAMPLE}).json()
    assert v["inspection"]["apply_mode"] == "replace", v
    body = {"device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]}}
    if after:
        body["credentials_after"] = {did: refs["approved"]}
    dep = client.post(f"/api/projects/{pid}/deployments", json=body).json()
    assert dep["state"] == "awaiting_approval", dep
    client.post(f"/api/deployments/{dep['id']}/approve")
    out = client.post(f"/api/deployments/{dep['id']}/execute").json()
    return out, " | ".join(e["message"] for e in out["events"])


def test_api_team_file_is_loaded_into_the_startup_config_and_the_switch_restarts(api):
    client, pid, did, sw, refs, hub = api
    out, events = _load(client, pid, did, refs)
    assert out["state"] == "succeeded", events
    assert sw.fetched and sw.fetched[0].startswith("undm-") and sw.restarts == 1
    assert "fetches it from this PC into its startup configuration and restarts" in events
    assert "into its startup configuration and is restarting with it" in events
    assert "same serial number" in events  # the MAC address, checked after the restart
    assert "restarted with the file: name lab-bbsw01" in events
    assert client.get(f"/api/devices/{did}").json()["credential_ref_id"] == refs["approved"]
    assert not hub.running and APPROVED not in repr(out)


def test_a_refused_file_does_not_restart_the_switch(api):
    client, pid, did, sw, refs, hub = api
    sw.copy_refusal = "% Invalid file content"  # synthetic
    out, events = _load(client, pid, did, refs)
    assert out["state"] != "succeeded" and sw.restarts == 0
    assert "refused it" in events and "Invalid file content" in events


def test_a_switch_that_does_not_restart_is_reported(api):
    client, pid, did, sw, refs, hub = api
    sw.reload_ignored = True
    out, events = _load(client, pid, did, refs)
    assert out["state"] != "succeeded" and sw.restarts == 0
    assert "takes effect at its next restart" in events


def test_merge_is_not_offered(switch):
    d = driver()
    d.connect()
    assert d.apply_configuration("hostname x\nend\n", ApplyMode.MERGE).status \
        is ResultStatus.UNSUPPORTED

