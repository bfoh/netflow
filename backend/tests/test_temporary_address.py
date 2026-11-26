"""A switch moved to a spare address in its running configuration only (D-096).

Both 2930F of a system end at the same management address; the first one staged is moved
aside, unsaved, so the second can take the address. The switch is a fake with synthetic
wording that models both behaviours of a second 'ip address' in a VLAN (replace or add):
which one a real unit shows is not verified (Q-45). Proves the procedure's decisions, not
hardware.
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
    return sw


def driver():
    d = ArubaOSSwitchSsh(DeviceTarget("d1", "127.0.0.1", None), Credentials("manager", ""))
    assert d.connect().ok
    return d


def test_the_driver_says_it_can():
    assert Capability.TEMPORARY_ADDRESS in ArubaOSSwitchSsh.info.capabilities


def test_preview_lists_the_commands_and_sends_nothing(switch):
    r = driver().temporary_address_commands("127.0.0.3")
    assert r.ok and r.data["vlan"] == 222 and r.data["previous"] == "127.0.0.1"
    assert r.data["commands"] == ["vlan 222", "ip address 127.0.0.3 255.0.0.0",
                                  "no ip address 127.0.0.1 255.0.0.0"]
    assert switch.running_config == RUNNING and not switch.unsaved_changes


@pytest.mark.parametrize("replaces", [False, True])
def test_switch_moves_aside_unsaved_whichever_way_it_treats_a_second_address(switch, replaces):
    switch.ip_address_replaces = replaces
    d = driver()
    r = d.set_temporary_address("127.0.0.3")
    assert r.ok, r.message
    assert r.data == {"address": "127.0.0.3", "previous": "127.0.0.1", "vlan": 222,
                      "notes": r.data["notes"]}
    assert ("replaced" in r.data["notes"][0]) is replaces
    assert switch.addresses == {"127.0.0.3"} and d.target.management_address == "127.0.0.3"
    assert "ip address 127.0.0.3 255.0.0.0" in switch.running_config
    assert "127.0.0.1" not in switch.running_config
    assert switch.startup_config == RUNNING and switch.saves == 0  # nothing saved
    assert not any(c.startswith("write") for c in switch.commands)
    assert "returns to its saved configuration at the next power-on" in r.message


def test_a_spare_address_in_use_or_outside_the_network_changes_nothing(switch):
    switch.addresses.add("127.0.0.3")  # e.g. another device already there
    r = driver().set_temporary_address("127.0.0.3")
    assert r.status is ResultStatus.FAILED and "already answers at 127.0.0.3" in r.message
    r = driver().set_temporary_address("127.255.255.255")
    assert r.status is ResultStatus.FAILED and "cannot be a spare address" in r.message
    assert switch.running_config == RUNNING


def test_a_rejected_removal_is_reported_with_what_still_holds(switch):
    switch.reject = {"no ip address 127.0.0.1 255.0.0.0"}
    r = driver().set_temporary_address("127.0.0.3")
    assert r.status is ResultStatus.FAILED
    assert "127.0.0.1 is still in use by it" in r.message and switch.saves == 0


def test_a_second_address_in_the_same_network_refused_by_the_switch_changes_nothing(switch):
    """Bench 2026-11-26: the step reported "took the command but does not answer" because the
    refusal's wording was not recognised. It is a rejection now; the switch keeps its
    address."""
    switch.refuse_overlap = True
    r = driver().set_temporary_address("127.0.0.3")
    assert r.status is ResultStatus.FAILED
    assert "rejected 'ip address 127.0.0.3 255.0.0.0'" in r.message
    assert "overlapping network" in r.diagnostics["device_output"]
    assert switch.running_config == RUNNING and switch.addresses == {"127.0.0.1"}


def test_a_spare_in_another_network_is_added_next_to_the_own_address(switch):
    """D-106: the spare is in another network the PC has, so the switch, which refuses a
    second address in its own network, can hold both for a moment."""
    switch.refuse_overlap = True
    d = driver()
    r = d.set_temporary_address("10.0.0.3")
    assert r.ok, r.message
    assert switch.addresses == {"10.0.0.3"} and "ip address 10.0.0.3 255.0.0.0" in \
        switch.running_config and "127.0.0.1" not in switch.running_config
    assert switch.saves == 0


def test_other_drivers_do_not_support_it():
    from undm.drivers.ssh.platforms import ArubaAOSCXSsh

    d = ArubaAOSCXSsh(DeviceTarget("d1", "192.0.2.10", None), Credentials("u", "p"))
    assert d.set_temporary_address("192.0.2.11").status is ResultStatus.UNSUPPORTED
    assert d.temporary_address_commands("192.0.2.11").status is ResultStatus.UNSUPPORTED


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


def _plan(client, pid, a, b, address="127.0.0.3"):
    return client.post(f"/api/projects/{pid}/device-staging", json={"device_id": b, "steps": [
        {"kind": "free_address", "other_device_id": a, "address": address}]})


def test_api_the_other_switch_is_moved_aside_by_an_approved_step(api, switch):
    client, pid, a, b = api
    made = _plan(client, pid, a, b).json()
    step = made["steps"][0]
    assert step["kind"] == "free_address" and step["state"] == "awaiting_approval", step
    preview = " | ".join(e["message"] for e in step["events"])
    assert "Commands: vlan 222; ip address 127.0.0.3 255.0.0.0; no ip address 127.0.0.1" in preview
    assert switch.running_config == RUNNING  # the preview changed nothing
    sid = made["staging_id"]
    client.post(f"/api/staging-plans/{sid}/approve", json={})
    done = client.post(f"/api/staging-plans/{sid}/execute?background=false").json()["steps"][0]
    events = " | ".join(e["message"] for e in done["events"])
    assert done["state"] == "succeeded", events
    assert "running at 127.0.0.3 (VLAN 222) until its next restart" in events
    assert switch.addresses == {"127.0.0.3"} and switch.saves == 0
    dev = client.get(f"/api/devices/{a}").json()
    assert dev["management_address"] == "127.0.0.1"  # its own address stays on record
    assert dev["observed_facts"]["extra"]["temporary_address"] == "127.0.0.3"
    # UNDM now reaches it at the temporary address, and a facts read keeps the note.
    read = client.post(f"/api/devices/{a}/operations/get_facts").json()
    assert read["status"] == "success", read
    assert client.get(f"/api/devices/{a}").json()["observed_facts"]["extra"][
        "temporary_address"] == "127.0.0.3"
    assert _plan(client, pid, a, b).status_code == 409  # already moved
    cleared = client.post(f"/api/devices/{a}/temporary-address/clear").json()
    assert "temporary_address" not in cleared["observed_facts"]["extra"]
    actions = {x["action"] for x in client.get("/api/audit?limit=50").json()}
    assert {"device.temporary_address", "device.temporary_address_cleared"} <= actions


def test_api_a_switch_that_is_off_or_unplugged_needs_no_move(api, switch):
    client, pid, a, b = api
    switch.addresses.clear()  # nothing answers at A's address
    made = _plan(client, pid, a, b).json()
    sid = made["staging_id"]
    assert "nothing to move" in made["steps"][0]["events"][-2]["message"]
    client.post(f"/api/staging-plans/{sid}/approve", json={})
    done = client.post(f"/api/staging-plans/{sid}/execute?background=false").json()["steps"][0]
    assert done["state"] == "succeeded", [e["message"] for e in done["events"]]
    assert "temporary_address" not in (client.get(f"/api/devices/{a}").json()
                                       ["observed_facts"] or {}).get("extra", {})


def test_api_a_failed_move_needs_attention_and_says_a_restart_restores(api, switch):
    client, pid, a, b = api
    switch.reject = {"no ip address 127.0.0.1 255.0.0.0"}
    sid = _plan(client, pid, a, b).json()["staging_id"]
    client.post(f"/api/staging-plans/{sid}/approve", json={})
    done = client.post(f"/api/staging-plans/{sid}/execute?background=false").json()["steps"][0]
    events = " | ".join(e["message"] for e in done["events"])
    assert done["state"] == "recovery_required", events
    assert "restarting it returns it to its saved configuration" in events


def test_api_a_refused_move_fails_cleanly_and_the_switch_keeps_its_address(api, switch):
    client, pid, a, b = api
    switch.refuse_overlap = True
    sid = _plan(client, pid, a, b).json()["staging_id"]
    client.post(f"/api/staging-plans/{sid}/approve", json={})
    done = client.post(f"/api/staging-plans/{sid}/execute?background=false").json()["steps"][0]
    assert done["state"] == "failed", [e["message"] for e in done["events"]]
    assert any("Nothing was changed" in e["message"] for e in done["events"])
    assert switch.running_config == RUNNING and switch.saves == 0


def test_api_only_a_capable_other_device_of_the_system(api):
    client, pid, a, b = api
    assert _plan(client, pid, b, b).status_code == 409  # not itself
    assert _plan(client, pid, a, b, address="not-an-address").status_code == 409

