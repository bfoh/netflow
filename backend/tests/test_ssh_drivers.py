import keyring
import pytest
from api_helpers import make_client
from fake_netmiko import (
    AOSCX_SHOW_SYSTEM,
    AOSCX_SHOW_VERSION,
    FORTIOS_STATUS,
    IOSXE_SHOW_VERSION,
    Scenario,
    factory_for,
)
from memory_keyring import MemoryKeyring
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from undm.drivers.base import ApplyMode, Credentials, DeviceTarget, ResultStatus
from undm.drivers.ssh.base import SshCliDriver
from undm.drivers.ssh.platforms import ArubaAOSCXSsh, CiscoIOSXESsh, FortiOSSsh

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
    (NetmikoAuthenticationException("bad"), "Authentication failed"),
    (NetmikoTimeoutException("slow"), "Timed out"),
    (OSError("No route to host"), "No route to host"),
])
def test_connect_errors_are_reported(scenario, error, needle):
    scenario.connect_error = error
    r = drv().connect()
    assert r.status is ResultStatus.FAILED and needle in r.message


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
    assert r.ok and "not checked" in r.message


def test_no_rollback_or_firmware_declared():
    for cls in (CiscoIOSXESsh, ArubaAOSCXSsh, FortiOSSsh):
        d = drv(cls)
        assert d.rollback_configuration(None).status is ResultStatus.UNSUPPORTED  # type: ignore[arg-type]
        assert d.install_firmware().status is ResultStatus.UNSUPPORTED


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


def test_lab_device_read_only_and_writes_gated(scenario, mem_keyring):
    client, _ = make_client()
    with client:
        pid, did = _setup(client)
        facts = client.post(f"/api/devices/{did}/operations/get_facts").json()
        assert facts["status"] == "success" and facts["data"]["serial_number"] == "FDO0000TEST"
        r = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [did]})
        assert r.status_code == 403 and "UNDM_ENABLE_REAL_DEVICE_WRITES" in r.json()["error"]
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
