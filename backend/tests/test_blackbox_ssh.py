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


def test_an_incomplete_read_is_never_stored(switch):
    switch.truncate_config = True
    d = driver()
    d.connect()
    r = d.backup_configuration()
    assert r.status is ResultStatus.FAILED
    assert "page break" in r.message or "incomplete" in r.message


def test_loading_is_not_offered_yet(switch):
    d = driver()
    d.connect()
    assert d.apply_configuration("hostname x\nend\n", ApplyMode.REPLACE).status \
        is ResultStatus.UNSUPPORTED
    assert d.missing_capabilities(  # plans that load a file are refused at validation
        __import__("undm.domain.operations", fromlist=["DeviceOperation"])
        .DeviceOperation.APPLY_CONFIGURATION)


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

