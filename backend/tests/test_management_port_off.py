"""Make room (D-107): the first 2930F of a system switches off its management port in its
running configuration only, so the second can take the address they share.

The switch is a fake with synthetic wording: by default the session ends with the port and
the address goes quiet; it can also ignore or reject the command. Proves the procedure's
decisions, not hardware (the command is the vendor's CLI, not yet run on the bench).
"""

import pytest
from fake_aos_switch import FakeArubaSwitch
from fake_netmiko import Scenario, factory_for

from undm.drivers.base import Capability, Credentials, DeviceTarget, ResultStatus
from undm.drivers.ssh import base as ssh_base
from undm.drivers.ssh.base import SshCliDriver
from undm.drivers.ssh.platforms import ArubaOSSwitchSsh

RUNNING = """hostname "lab-oobm-sw01"
vlan 1
   name "DEFAULT_VLAN"
   no untagged 2
   untagged 1,3-52
   no ip address
   exit
vlan 222
   name "OOBM_VLAN"
   untagged 2
   ip address 127.0.0.1 255.0.0.0
   exit
"""


@pytest.fixture
def switch(monkeypatch):
    sw = FakeArubaSwitch(tftp_port=lambda: 0)
    sw.running_config, sw.addresses = RUNNING, {"127.0.0.1"}
    sw.startup_config = RUNNING
    monkeypatch.setattr(SshCliDriver, "connection_factory",
                        staticmethod(factory_for(Scenario(prompt="lab-oobm-sw01#", device=sw))))
    monkeypatch.setattr(ssh_base, "tcp_port_open",
                        lambda host, port, timeout=3.0: host in (sw.addresses or set()))
    monkeypatch.setattr(ArubaOSSwitchSsh, "port_off_wait", 0.2)
    return sw


def driver():
    d = ArubaOSSwitchSsh(DeviceTarget("d1", "127.0.0.1", None), Credentials("manager", ""))
    assert d.connect().ok
    return d


def test_the_driver_says_it_can():
    assert Capability.MANAGEMENT_PORT_OFF in ArubaOSSwitchSsh.info.capabilities


def test_preview_names_the_port_and_sends_nothing(switch):
    r = driver().free_address_commands()
    assert r.ok and r.data == {"vlan": 222, "port": "2", "commands": ["interface 2 disable"]}
    assert "port 2 (VLAN 222, 127.0.0.1)" in r.message
    assert not switch.ports_off and not switch.unsaved_changes


def test_a_vlan_with_more_than_one_untagged_port_is_refused(switch):
    switch.running_config = RUNNING.replace("   untagged 2\n", "   untagged 2,5\n")
    r = driver().free_address_commands()
    assert r.status is ResultStatus.FAILED and "2 untagged ports (2, 5)" in r.message


def test_the_port_goes_off_unsaved_and_the_address_goes_quiet(switch):
    r = driver().free_address()
    assert r.ok, r.message
    assert r.data["port"] == "2" and "127.0.0.1 no longer answers" in r.message
    assert switch.ports_off == {"2"} and switch.saves == 0
    assert switch.startup_config == RUNNING
    assert not any(c.startswith("write") for c in switch.commands)


def test_a_switch_that_still_answers_is_left_as_it_was(switch):
    switch.port_off_mode = "ignore"
    r = driver().free_address()
    assert r.status is ResultStatus.FAILED and r.diagnostics["unchanged"]
    assert "still answers at 127.0.0.1" in r.message


def test_a_rejected_command_changes_nothing_and_quotes_the_switch(switch):
    switch.port_off_mode = "reject"
    r = driver().free_address()
    assert r.status is ResultStatus.FAILED and r.diagnostics["unchanged"]
    assert "rejected 'interface 2 disable'" in r.message and "invalid port" in r.message


def test_other_drivers_do_not_support_it():
    from undm.drivers.ssh.platforms import ArubaAOSCXSsh

    d = ArubaAOSCXSsh(DeviceTarget("d1", "192.0.2.10", None), Credentials("u", "p"))
    assert d.free_address().status is ResultStatus.UNSUPPORTED
    assert d.free_address_commands().status is ResultStatus.UNSUPPORTED


# -- through the lifecycle and the API ----------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_path, switch):
    import keyring
    from api_helpers import make_client
    from memory_keyring import MemoryKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    client, _ = make_client(data_dir=str(tmp_path), enable_real_device_writes=True)
    with client:
        pid = client.post("/api/projects", json={"name": "Bench"}).json()["id"]
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "m"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": "manager", "password": ""})

        def add(name, address):
            return client.post(f"/api/projects/{pid}/devices", json={
                "name": name, "manufacturer": "Aruba", "category": "switch", "model": "2930F",
                "os_family": "ArubaOS-Switch", "driver_id": "ssh.aruba.aos_switch",
                "environment": "lab", "management_address": address,
                "credential_ref_id": ref["id"]}).json()["id"]
        yield client, pid, add("sw-a", "127.0.0.1"), add("sw-b", "127.0.0.2")
    keyring.set_keyring(previous)


def _plan(client, pid, a, b):
    return client.post(f"/api/projects/{pid}/device-staging", json={"device_id": b, "steps": [
        {"kind": "free_address", "other_device_id": a}]})


def _run(client, made):
    sid = made["staging_id"]
    client.post(f"/api/staging-plans/{sid}/approve", json={})
    return client.post(f"/api/staging-plans/{sid}/execute?background=false").json()["steps"][0]


def test_api_the_other_switch_goes_off_the_network_by_an_approved_step(api, switch):
    client, pid, a, b = api
    made = _plan(client, pid, a, b).json()
    step = made["steps"][0]
    assert step["kind"] == "free_address" and step["state"] == "awaiting_approval", step
    preview = " | ".join(e["message"] for e in step["events"])
    assert "Commands: interface 2 disable" in preview and not switch.ports_off
    done = _run(client, made)
    events = " | ".join(e["message"] for e in done["events"])
    assert done["state"] == "succeeded", events
    assert "port 2 switched off" in events and "no longer answers" in events
    assert switch.saves == 0
    dev = client.get(f"/api/devices/{a}").json()
    assert dev["management_address"] == "127.0.0.1"
    assert dev["observed_facts"]["extra"]["management_port_off"]["port"] == "2"
    # Switched off and on: it answers again, and UNDM clears the note itself.
    switch.addresses.add("127.0.0.1")
    assert client.post(f"/api/devices/{a}/operations/check_reachability").json()["status"] \
        == "success"
    dev = client.get(f"/api/devices/{a}").json()
    assert "management_port_off" not in dev["observed_facts"]["extra"]
    actions = {x["action"] for x in client.get("/api/audit?limit=50").json()}
    assert {"device.management_port_off", "device.management_port_on"} <= actions


def test_api_the_note_can_be_cleared_by_hand(api, switch):
    client, pid, a, b = api
    assert _run(client, _plan(client, pid, a, b).json())["state"] == "succeeded"
    cleared = client.post(f"/api/devices/{a}/port-off/clear").json()
    assert "management_port_off" not in cleared["observed_facts"]["extra"]


def test_api_a_switch_that_is_off_or_unplugged_needs_no_move(api, switch):
    client, pid, a, b = api
    switch.addresses.clear()  # nothing answers at A's address
    made = _plan(client, pid, a, b).json()
    assert "nothing to move" in made["steps"][0]["events"][-2]["message"]
    done = _run(client, made)
    assert done["state"] == "succeeded", [e["message"] for e in done["events"]]
    assert not switch.ports_off


def test_api_a_switch_left_as_it_was_fails_cleanly(api, switch):
    client, pid, a, b = api
    switch.port_off_mode = "ignore"
    done = _run(client, _plan(client, pid, a, b).json())
    events = " | ".join(e["message"] for e in done["events"])
    assert done["state"] == "failed", events
    assert "still answers at 127.0.0.1" in events and "nothing was changed on it" in events


def test_api_only_a_capable_other_device_of_the_system(api):
    client, pid, a, b = api
    assert _plan(client, pid, b, b).status_code == 409  # not itself
