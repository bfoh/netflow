from pathlib import Path

import keyring
import pytest
from api_helpers import make_client
from fake_netmiko import (
    AOSCX_SHOW_SYSTEM,
    AOSCX_SHOW_VERSION,
    FORTIOS_STATUS,
    IOSXE_SHOW_VERSION,
    FakeConnection,
    Scenario,
    factory_for,
)
from memory_keyring import MemoryKeyring
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from undm.domain.operations import DeviceOperation
from undm.drivers.base import ApplyMode, Credentials, DeviceTarget, ResultStatus
from undm.drivers.ssh.base import SshCliDriver
from undm.drivers.ssh.platforms import ArubaAOSCXSsh, ArubaOSSwitchSsh, CiscoIOSXESsh, FortiOSSsh

CREDS = Credentials("netops", "Example-Only-1")


@pytest.fixture
def scenario(monkeypatch):
    sc = Scenario(outputs={"show version": IOSXE_SHOW_VERSION})
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory_for(sc)))
    return sc


def drv(cls=CiscoIOSXESsh, creds=CREDS):
    return cls(DeviceTarget("d1", "192.0.2.10", None), creds)


def test_connect_requires_credentials(scenario):
    r = drv(creds=None).connect()
    assert r.status is ResultStatus.FAILED and "credential" in r.message
    assert scenario.calls == []


def test_connect_passes_parameters_without_leaking_password(scenario):
    d = drv()
    assert d.connect().ok
    params = scenario.calls[0][1]
    assert params["device_type"] == "cisco_xe" and params["host"] == "192.0.2.10"
    assert params["port"] == 22 and params["username"] == "netops"
    assert "Example-Only-1" not in repr(d.__dict__)


@pytest.mark.parametrize("error,needle", [
    (NetmikoAuthenticationException("bad"), "The device refused the login (user 'netops')"),
    (NetmikoTimeoutException("slow"), "No answer from 192.0.2.10 on port 22 (SSH)"),
    (OSError("No route to host"), "No route to host"),
])
def test_connect_errors_are_reported(scenario, error, needle):
    scenario.connect_error = error
    r = drv().connect()
    assert r.status is ResultStatus.FAILED and needle in r.message


def test_no_answer_is_said_in_plain_words_with_the_library_text_kept_aside(scenario):
    """Bench 2026-11-25: the message showed the library's text and driver type."""
    scenario.connect_error = NetmikoTimeoutException(
        "TCP connection to device failed. Device settings: aruba_osswitch 192.0.2.10:22")
    r = drv().connect()
    assert "No answer from 192.0.2.10 on port 22 (SSH)" in r.message
    assert "Wi-Fi" in r.message and "aruba_osswitch" not in r.message
    assert "aruba_osswitch" in r.diagnostics["detail"]


def test_iosxe_facts_and_backup(scenario):
    d = drv()
    d.connect()
    f = d.get_device_facts().data
    assert (f.hostname, f.model, f.os_version, f.serial_number) == (
        "lab-r1", "ISR4331/K9", "17.09.04a", "FDO0000TEST")
    assert f.extra["parser"] == "best_effort_not_lab_verified"
    b = d.backup_configuration()
    assert b.ok and b.data.text == scenario.running and "nothing written" in b.message
    assert not any(c[0] == "send_config_set" for c in scenario.calls)  # read-only


def test_aoscx_and_fortios_facts(scenario):
    scenario.outputs.update({"show version": AOSCX_SHOW_VERSION, "show system": AOSCX_SHOW_SYSTEM,
                             "get system status": FORTIOS_STATUS})
    a = drv(ArubaAOSCXSsh)
    a.connect()
    fa = a.get_device_facts().data
    assert (fa.hostname, fa.os_version, fa.serial_number) == (
        "lab-sw1", "FL.10.13.1000", "SG00TEST01")
    f = drv(FortiOSSsh)
    f.connect()
    ff = f.get_device_facts().data
    assert (ff.hostname, ff.model, ff.os_version, ff.serial_number) == (
        "lab-fw1", "FortiGate-60F", "v7.2.8", "FGT60FTK00000000")


def test_config_lines_strip_file_headers(scenario):
    text = "Building configuration...\nCurrent configuration : 99 bytes\n!\nhostname r1\n!\nend\n"
    assert drv().config_lines(text) == ["hostname r1"]
    assert drv(FortiOSSsh).config_lines("#config-version=FGT60F\nconfig system global\n") == [
        "config system global"]


def test_apply_merge_save_and_rejections(scenario):
    d = drv()
    d.connect()
    assert d.apply_configuration("x\n", ApplyMode.REPLACE).status is ResultStatus.UNSUPPORTED
    assert d.apply_configuration("hostname r2\n", ApplyMode.MERGE).ok
    assert d.save_configuration().ok and scenario.saved == 1
    scenario.bad_lines = {"bogus command"}
    r = d.apply_configuration("ip domain name lab.example\nbogus command\n", ApplyMode.MERGE)
    assert r.status is ResultStatus.FAILED and "partially applied" in r.message
    assert "ip domain name lab.example" in scenario.running  # partial apply is real


def test_fortios_save_is_not_claimed_as_device_save(scenario):
    f = drv(FortiOSSsh)
    f.connect()
    r = f.save_configuration()
    # The save mode could not be read here: UNDM says it assumed it, never that it checked.
    assert r.ok and "assumed automatic, not readable" in r.message


def test_no_rollback_declared_and_firmware_only_where_implemented():
    for cls in (CiscoIOSXESsh, ArubaAOSCXSsh, ArubaOSSwitchSsh, FortiOSSsh):
        d = drv(cls)
        assert d.rollback_configuration(None).status is ResultStatus.UNSUPPORTED  # type: ignore[arg-type]
        assert d.rollback_firmware().status is ResultStatus.UNSUPPORTED
    for cls in (CiscoIOSXESsh, ArubaAOSCXSsh):
        assert drv(cls).install_firmware().status is ResultStatus.UNSUPPORTED
        assert drv(cls).stage_firmware(None).status is ResultStatus.UNSUPPORTED  # type: ignore[arg-type]
    # Experimental procedures exist for the 2930F and FortiOS (see their own test files).
    for cls in (ArubaOSSwitchSsh, FortiOSSsh):
        assert not drv(cls).missing_capabilities(DeviceOperation.INSTALL_FIRMWARE)


def test_verification_ignores_indentation_and_hidden_defaults():
    d = drv()
    expected = d.expected_lines(
        "interface Gi1\n ip address 192.0.2.1 255.255.255.0\n no shutdown\n")
    assert expected == ["interface Gi1", "ip address 192.0.2.1 255.255.255.0"]
    assert "ip address 192.0.2.1 255.255.255.0" in d.present_lines(
        "interface Gi1\n   ip address 192.0.2.1 255.255.255.0\n")


# --- end-to-end through the API with policy gates -----------------------------

@pytest.fixture
def mem_keyring():
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield
    keyring.set_keyring(previous)


ROUTER = {"name": "lab-r1", "manufacturer": "Cisco", "category": "router",
          "driver_id": "ssh.cisco.iosxe", "environment": "lab",
          "management_address": "192.0.2.10"}
INTENT = {"hostname": "lab-r1",
          "interfaces": [{"interface": "GigabitEthernet1", "address": "192.0.2.10/24"}],
          "static_routes": [{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"}]}


def _setup(client):
    pid = client.post("/api/projects", json={"name": "Lab"}).json()["id"]
    ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "lab"}).json()
    client.put(f"/api/credential-refs/{ref['id']}/secret",
               json={"username": "netops", "password": "Example-Only-1"})
    did = client.post(f"/api/projects/{pid}/devices",
                      json=dict(ROUTER, credential_ref_id=ref["id"])).json()["id"]
    client.put(f"/api/devices/{did}/intent", json=INTENT)
    assert client.post(f"/api/devices/{did}/configs/generate").json()["ok"]
    return pid, did


def test_real_driver_environment_rules():
    client, _ = make_client()
    with client:
        pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
        r = client.post(f"/api/projects/{pid}/devices", json=dict(ROUTER, environment="simulated"))
        assert r.status_code == 400 and "real equipment" in r.json()["error"]


@pytest.mark.parametrize("error,refused", [
    (NetmikoAuthenticationException("bad"), True), (NetmikoTimeoutException("slow"), False)])
def test_test_connection_says_when_the_login_was_refused(scenario, mem_keyring, error, refused):
    client, _ = make_client()
    with client:
        _, did = _setup(client)
        scenario.connect_error = error
        r = client.post(f"/api/devices/{did}/operations/check_reachability").json()
        assert r["status"] == "failed" and r["login_refused"] is refused


def test_lab_device_read_only_and_writes_gated(scenario, mem_keyring):
    client, _ = make_client()
    with client:
        pid, did = _setup(client)
        facts = client.post(f"/api/devices/{did}/operations/get_facts").json()
        assert facts["status"] == "success" and facts["data"]["serial_number"] == "FDO0000TEST"
        r = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [did]})
        assert r.status_code == 403 and "Real-device changes are off" in r.json()["error"]
        dry = client.post(f"/api/projects/{pid}/deployments",
                          json={"device_ids": [did], "dry_run": True}).json()
        out = client.post(f"/api/deployments/{dry['id']}/execute").json()
        assert out["state"] == "succeeded"
        assert not any(c[0] == "send_config_set" for c in scenario.calls)


def test_lab_device_deployment_when_writes_enabled(scenario, mem_keyring):
    client, _ = make_client(enable_real_device_writes=True)
    with client:
        pid, did = _setup(client)
        client.post(f"/api/devices/{did}/operations/get_facts")  # records serial for identity
        dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [did]}).json()
        client.post(f"/api/deployments/{dep['id']}/approve")
        out = client.post(f"/api/deployments/{dep['id']}/execute").json()
        assert out["state"] == "succeeded", out["events"]
        assert out["targets"][0]["state"] == "verified"
        assert scenario.saved == 1
        assert "ip route 0.0.0.0 0.0.0.0 192.0.2.1" in scenario.running


def test_rejected_line_ends_in_manual_recovery(scenario, mem_keyring):
    scenario.bad_lines = {"ip route 0.0.0.0 0.0.0.0 192.0.2.1"}
    client, _ = make_client(enable_real_device_writes=True)
    with client:
        pid, did = _setup(client)
        dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [did]}).json()
        client.post(f"/api/deployments/{dep['id']}/approve")
        out = client.post(f"/api/deployments/{dep['id']}/execute").json()
        assert out["state"] == "recovery_required"
        assert out["targets"][0]["state"] == "manual_recovery_required"
        assert out["targets"][0]["backup_version_id"]  # the stored backup to restore from


def test_production_real_device_blocked(scenario, mem_keyring):
    client, _ = make_client(enable_real_device_writes=True)
    with client:
        pid, did = _setup(client)
        client.patch(f"/api/devices/{did}", json={"environment": "production"})
        r = client.post(f"/api/devices/{did}/operations/get_facts")
        assert r.status_code == 403 and "production" in r.json()["error"]
        r = client.post(f"/api/projects/{pid}/deployments",
                        json={"device_ids": [did], "dry_run": True})
        assert r.status_code == 403


# --- ArubaOS-Switch (2930F) -------------------------------------------------------

def test_aos_switch_session_parameters_and_facts(scenario):
    from fake_netmiko import AOS_SWITCH_SHOW_MODULES, AOS_SWITCH_SHOW_SYSTEM
    scenario.outputs.update({"show system": AOS_SWITCH_SHOW_SYSTEM,
                             "show modules": AOS_SWITCH_SHOW_MODULES})
    d = drv(ArubaOSSwitchSsh)
    assert d.connect().ok
    params = scenario.calls[0][1]
    assert params["device_type"] == "aruba_osswitch"
    assert "secret" not in params  # recorded params exclude secrets in the fake
    f = d.get_device_facts().data
    assert (f.hostname, f.os_version, f.serial_number) == ("lab-2930f", "WC.16.10.0012",
                                                          "CN00TEST01")
    assert f.model == "2930F-24G-4SFPP"
    assert f.extra["product_number"] == "JL259A"


def test_aos_switch_passes_enable_secret(scenario):
    seen = {}

    def factory(**kwargs):
        seen.update(kwargs)
        return FakeConnection(scenario, **kwargs)

    SshCliDriver.connection_factory = staticmethod(factory)  # restored by monkeypatch fixture
    drv(ArubaOSSwitchSsh).connect()
    assert seen["secret"] == CREDS.password


def test_aos_switch_config_lines_and_verification(scenario):
    from fake_netmiko import AOS_SWITCH_RUNNING
    d = drv(ArubaOSSwitchSsh)
    assert d.config_lines(AOS_SWITCH_RUNNING)[0] == 'hostname "lab-2930f"'  # header + ; dropped
    intended = 'hostname "lab-2930f"\nvlan 10\n   name "users"\n   exit\n'
    running = AOS_SWITCH_RUNNING + 'vlan 10\n   name "users"\n   exit\n'
    present = d.present_lines(running)
    assert [ln for ln in d.expected_lines(intended) if ln not in present] == []


def test_sanitized_diagnostics_after_real_read(scenario, mem_keyring):
    from fake_netmiko import AOS_SWITCH_SHOW_MODULES, AOS_SWITCH_SHOW_SYSTEM
    scenario.outputs.update({"show system": AOS_SWITCH_SHOW_SYSTEM,
                             "show modules": AOS_SWITCH_SHOW_MODULES})
    client, _ = make_client()
    with client:
        pid = client.post("/api/projects", json={"name": "Diag"}).json()["id"]
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "c"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "netops", "password": "Example-Only-1"})
        did = client.post(f"/api/projects/{pid}/devices", json={
            "name": "lab-2930f", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
            "os_family": "ArubaOS-Switch", "driver_id": "ssh.aruba.aos_switch",
            "environment": "lab", "management_address": "192.0.2.21",
            "credential_ref_id": ref["id"]}).json()["id"]
        assert client.post(f"/api/devices/{did}/operations/get_facts").json()["status"] == "success"
        text = client.get(f"/api/devices/{did}/diagnostics").json()["text"]
        assert "== raw output: show system ==" in text and "WC.16.10.0012" in text
        for leaked in ("CN00TEST01", "001122-334455", "192.0.2.21", "lab-2930f", "Example-Only-1"):
            assert leaked not in text, leaked



# --- Real-layout fixture: Aruba 2930F-48G-4SFP, WC.16.10.0025 -----------------------

FIXTURE = Path(__file__).parent / "fixtures" / "aruba_2930f_wc_16_10_0025"


def _fixture_outputs():
    return {"show system": (FIXTURE / "show_system.txt").read_text(),
            "show modules": (FIXTURE / "show_modules.txt").read_text()}


def test_real_2930f_layout_is_parsed(scenario):
    scenario.outputs.update(_fixture_outputs())
    d = drv(ArubaOSSwitchSsh)
    d.connect()
    f = d.get_device_facts().data
    assert (f.hostname, f.model, f.os_version, f.serial_number) == (
        "lab-2930f", "2930F-48G-4SFP", "WC.16.10.0025", "SG00FAKE01")
    assert f.extra["product_number"] == "JL260A"
    assert f.extra["rom_version"] == "WC.16.01.0010"
    assert f.extra["parser"].startswith("checked against real output: 2930F-48G-4SFP")


def test_real_2930f_diagnostics_use_one_placeholder_per_value(scenario, mem_keyring):
    scenario.outputs.update(_fixture_outputs())
    client, _ = make_client()
    with client:
        pid = client.post("/api/projects", json={"name": "Real layout"}).json()["id"]
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "c"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "netops", "password": "Example-Only-1"})
        did = client.post(f"/api/projects/{pid}/devices", json={
            "name": "sw-a", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
            "os_family": "ArubaOS-Switch", "driver_id": "ssh.aruba.aos_switch",
            "environment": "lab", "management_address": "192.0.2.30",
            "credential_ref_id": ref["id"]}).json()["id"]
        client.post(f"/api/devices/{did}/operations/get_facts")
        text = client.get(f"/api/devices/{did}/diagnostics").json()["text"]
        assert "SG00FAKE01" not in text and "001122-334455" not in text and "lab-2930f" not in text
        assert "<serial-2>" not in text and text.count("<serial-1>") == 3  # facts, system, modules
        assert "product_number: JL260A" in text and "rom_version: WC.16.01.0010" in text


def test_2930f_step8_dry_run_preview_lists_only_new_vlan(scenario, mem_keyring):
    """Acceptance step 8: dry run of a test VLAN on a switch with existing config."""
    from fake_netmiko import AOS_SWITCH_RUNNING
    scenario.outputs.update(_fixture_outputs())
    scenario.running = AOS_SWITCH_RUNNING + "interface 1\n   name \"uplink\"\n   exit\n"
    client, _ = make_client()
    with client:
        pid = client.post("/api/projects", json={"name": "Step 8"}).json()["id"]
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "c"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "netops", "password": "Example-Only-1"})
        did = client.post(f"/api/projects/{pid}/devices", json={
            "name": "sw", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
            "os_family": "ArubaOS-Switch", "driver_id": "ssh.aruba.aos_switch",
            "environment": "lab", "management_address": "192.0.2.31",
            "credential_ref_id": ref["id"]}).json()["id"]
        client.post(f"/api/devices/{did}/operations/get_facts")
        client.put(f"/api/devices/{did}/intent", json={
            "hostname": "lab-2930f", "vlans": [{"vlan_id": 3999, "name": "undm-test"}]})
        assert client.post(f"/api/devices/{did}/configs/generate").json()["ok"]
        dep = client.post(f"/api/projects/{pid}/deployments",
                          json={"device_ids": [did], "dry_run": True}).json()
        diff = dep["targets"][0]["diff"].splitlines()
        assert [ln for ln in diff[2:] if ln.startswith("+")] == [
            "+vlan 3999", '+   name "undm-test"']
        assert not any(ln.startswith("-") for ln in diff[2:])
        assert ' hostname "lab-2930f"' in diff  # unchanged: already the switch's hostname
        out = client.post(f"/api/deployments/{dep['id']}/execute").json()
        assert out["state"] == "succeeded"
        assert not any(c[0] == "send_config_set" for c in scenario.calls)  # nothing sent
