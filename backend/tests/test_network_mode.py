"""After staging: a system reached in the network through its BFW (D-125).

Fictional systems, RFC 5737 addresses and simulated devices; real-driver devices are only
built, never connected (no program is started, no device is contacted)."""

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.db.models import Device, Project
from undm.drivers.mock.lab import default_lab
from undm.drivers.registry import default_registry
from undm.drivers.ssh import base as ssh_base
from undm.services import devices as devsvc
from undm.services import reach
from undm.services.errors import ConflictError

BENCH_FW, BENCH_SW = "192.168.1.99", "192.168.1.1"
TEAM_FILE = ("; JL260A Configuration Editor; Created on release #WC.16.10.0025\n"
             "hostname \"abc-sw-a\"\nvlan 222\n   name \"OOBM\"\n   untagged 2\n"
             "   ip address 192.168.1.1 255.255.255.0\n   exit\n")
NET_FW, NET_SW = "198.51.100.1", "198.51.100.11"


@pytest.fixture
def env(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, factory = make_client(data_dir=str(tmp_path), enable_real_device_writes=True)
    with c:
        yield c, factory
    keyring.set_keyring(previous)


def make_system(c, *, real=False, name="Practice B007"):
    pid = c.post("/api/projects", json={"name": name}).json()["id"]
    ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
    c.put(f"/api/credential-refs/{ref['id']}/secret",
          json={"username": "admin", "password": "Example-Only-1"})
    env = "lab" if real else "simulated"
    fw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-fw", "manufacturer": "Fortinet", "category": "firewall",
        "model": "FortiGate-101F", "environment": env, "credential_ref_id": ref["id"],
        "driver_id": "ssh.fortinet.fortios" if real else "mock.fortinet.fortios",
        "management_address": BENCH_FW}).json()
    sw = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-sw-a", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "environment": env, "credential_ref_id": ref["id"],
        "driver_id": "ssh.aruba.aos_switch" if real else "mock.aruba.aos_switch",
        "management_address": BENCH_SW}).json()
    return pid, fw["id"], sw["id"], ref["id"]


def to_network(c, pid, fw, sw):
    assert c.put(f"/api/devices/{fw}/network-address", json={"address": NET_FW}).status_code \
        == 200
    assert c.put(f"/api/devices/{sw}/network-address",
                 json={"address": NET_SW, "file": "abc-sw-a.pcc", "line": 12}).status_code == 200
    r = c.put(f"/api/projects/{pid}/reached-via", json={"via": "network"})
    assert r.status_code == 200, r.text
    return r.json()


def test_on_the_bench_nothing_changes(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    device = c.get(f"/api/devices/{sw}").json()
    assert device["connection"]["via"] == "bench"
    assert device["connection"]["address"] == BENCH_SW
    assert c.get(f"/api/projects/{pid}").json()["reached_via"] == "bench"
    assert c.post(f"/api/devices/{sw}/operations/check_reachability").json()["status"] \
        == "success"


def test_in_the_network_devices_are_reached_at_their_network_address(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    facts = c.post(f"/api/devices/{sw}/operations/get_facts").json()["data"]
    project = to_network(c, pid, fw, sw)
    assert project["reached_via"] == "network" and project["network_gateway_id"] == fw
    device = c.get(f"/api/devices/{sw}").json()
    assert device["connection"] == {
        "via": "network", "address": NET_SW, "port": None, "driver_id": "mock.aruba.aos_switch",
        "capabilities": device["capabilities"], "problem": None}
    assert device["management_address"] == BENCH_SW  # the bench address is kept
    again = c.post(f"/api/devices/{sw}/operations/get_facts").json()["data"]
    assert again["serial_number"] == facts["serial_number"]  # the same simulated unit
    assert default_lab().get(NET_SW) is default_lab().get(BENCH_SW)
    # Simulated devices stay simulated in the network.
    assert device["environment"] == "simulated"
    back = c.put(f"/api/projects/{pid}/reached-via", json={"via": "bench"}).json()
    assert back["reached_via"] == "bench"
    assert c.get(f"/api/devices/{sw}").json()["connection"]["address"] == BENCH_SW
    actions = [a for a in c.get("/api/audit").json() if a["action"] in (
        "system.reached_via_changed", "device.network_address_set")]
    assert {a["action"] for a in actions} == {"system.reached_via_changed",
                                              "device.network_address_set"}
    by_file = [a for a in actions if (a.get("details") or {}).get("file") == "abc-sw-a.pcc"]
    assert by_file and by_file[0]["details"]["line"] == 12


def test_moving_needs_the_bfw_and_its_network_address(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    r = c.put(f"/api/projects/{pid}/reached-via", json={"via": "network"})
    assert r.status_code == 409 and "network address of abc-fw" in r.json()["error"]
    c.put(f"/api/devices/{sw}/network-address", json={"address": NET_SW})
    r = c.put(f"/api/projects/{pid}/reached-via",
              json={"via": "network", "gateway_device_id": sw})
    assert r.status_code == 200 and r.json()["network_gateway_id"] == sw  # a person's choice
    r = c.put(f"/api/projects/{pid}/reached-via",
              json={"via": "network", "gateway_device_id": "not-a-device"})
    assert r.status_code == 404


def test_a_device_without_a_network_address_says_so(env, monkeypatch):
    c, _ = env
    pid, fw, sw, _ = make_system(c, real=True)
    c.put(f"/api/devices/{fw}/network-address", json={"address": NET_FW})
    assert c.put(f"/api/projects/{pid}/reached-via", json={"via": "network"}).status_code == 200
    device = c.get(f"/api/devices/{sw}").json()
    assert device["connection"]["address"] == "" and "no network address yet" in \
        device["connection"]["problem"]
    asked: list[str] = []
    monkeypatch.setattr(ssh_base, "tcp_port_open",
                        lambda host, port, timeout=3.0: asked.append(host) or False)
    states = {r["device_id"]: r["state"] for r in
              c.get(f"/api/projects/{pid}/reachability").json()}
    assert states == {fw: "no_answer", sw: "no_network_address"}
    assert asked == [NET_FW]  # never the bench address


def test_network_addresses_are_checked(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    for bad in ("fw.example", "198.51.100.0/24", "224.0.0.1", "0.0.0.0", "198.51.100.255",
                "-198.51.100.1", "127.0.0.1"):
        r = c.put(f"/api/devices/{fw}/network-address", json={"address": bad})
        assert r.status_code == 409, bad
    c.put(f"/api/devices/{fw}/network-address", json={"address": NET_FW})
    r = c.put(f"/api/devices/{sw}/network-address", json={"address": NET_FW})
    assert r.status_code == 409 and "abc-fw" in r.json()["error"]
    cleared = c.put(f"/api/devices/{fw}/network-address", json={"address": None}).json()
    assert cleared["network_address"] is None


def test_real_devices_are_production_in_the_network_and_lab_on_the_bench(env):
    c, factory = env
    pid, fw, sw, _ = make_system(c, real=True)
    to_network(c, pid, fw, sw)
    assert {c.get(f"/api/devices/{d}").json()["environment"] for d in (fw, sw)} == \
        {"production"}
    # UNDM's own logins to them need the start-up switch (no device is contacted here).
    r = c.post(f"/api/devices/{sw}/operations/check_reachability")
    assert r.status_code == 403 and "UNDM_ALLOW_PRODUCTION_READ_ONLY" in r.json()["error"]
    # A person cannot make them lab devices while the system is in the network...
    r = c.patch(f"/api/devices/{sw}", json={"environment": "lab"})
    assert r.status_code == 409 and "back to the bench" in r.json()["error"]
    # ...and a real device added there is a production device.
    added = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-sw-b", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "driver_id": "ssh.aruba.aos_switch", "environment": "lab",
        "management_address": "192.168.1.2"}).json()
    assert added["environment"] == "production"
    with factory() as s:  # built for the network address, not connected
        device = s.get(Device, sw)
        assert devsvc.build_driver(device, default_registry()).target.management_address \
            == NET_SW
        assert devsvc.build_driver(device, default_registry(), via="bench").target \
            .management_address == BENCH_SW
    c.put(f"/api/projects/{pid}/reached-via", json={"via": "bench"})
    assert c.get(f"/api/devices/{sw}").json()["environment"] == "lab"


def test_every_plan_is_refused_in_the_network(env):
    c, _ = env
    pid, fw, sw, ref = make_system(c)
    version = c.post(f"/api/devices/{sw}/configs/import", json={
        "filename": "abc-sw-a.pcc", "text": TEAM_FILE}).json()["id"]
    to_network(c, pid, fw, sw)
    attempts = [
        c.post(f"/api/projects/{pid}/deployments", json={
            "device_ids": [sw], "dry_run": False, "apply_mode": "replace",
            "config_versions": {sw: version}}),
        c.post(f"/api/projects/{pid}/deployments", json={
            "device_ids": [sw], "dry_run": True, "apply_mode": "merge"}),
        c.post(f"/api/projects/{pid}/first-login", json={"device_id": fw}),
        c.post(f"/api/devices/{sw}/restart-plan"),
        c.post(f"/api/projects/{pid}/firmware-upgrades", json={
            "device_ids": [sw], "image_id": "none", "dry_run": False}),
        c.post(f"/api/projects/{pid}/device-staging", json={
            "device_id": sw, "steps": [{"kind": "configuration", "version_id": version}]}),
        c.post(f"/api/projects/{pid}/staging-plans", json={
            "device_id": fw, "base_version_id": "a", "site_version_id": "b"}),
        c.post(f"/api/devices/{sw}/license-plan", json={"version_id": "none"}),
    ]
    for r in attempts:
        assert r.status_code == 409 and "only on the bench" in r.json()["error"], r.text
    assert c.get(f"/api/projects/{pid}/deployments").json() == []


def test_a_plan_made_on_the_bench_does_not_run_in_the_network(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    version = c.post(f"/api/devices/{sw}/configs/import", json={
        "filename": "abc-sw-a.pcc", "text": TEAM_FILE}).json()["id"]
    plan = c.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [sw], "dry_run": False, "apply_mode": "replace",
        "config_versions": {sw: version}}).json()
    assert plan["state"] == "awaiting_approval", plan
    other = c.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [sw], "dry_run": False, "apply_mode": "replace",
        "config_versions": {sw: version}}).json()
    assert c.post(f"/api/deployments/{other['id']}/approve").status_code == 200
    to_network(c, pid, fw, sw)
    r = c.post(f"/api/deployments/{plan['id']}/approve")
    assert r.status_code == 409 and "only on the bench" in r.json()["error"]
    r = c.post(f"/api/deployments/{other['id']}/execute")
    assert r.status_code == 409 and "only on the bench" in r.json()["error"]
    device = c.get(f"/api/devices/{sw}").json()
    assert device["management_address"] == BENCH_SW and device["network_address"] == NET_SW
    assert device["deployment_status"] == "never_deployed"


def test_moving_is_refused_while_a_plan_runs_on_a_device(env):
    c, factory = env
    pid, fw, sw, _ = make_system(c)
    c.put(f"/api/devices/{fw}/network-address", json={"address": NET_FW})
    with factory() as s:
        s.get(Device, sw).locked_by_deployment_id = "running-plan"
        s.commit()
    r = c.put(f"/api/projects/{pid}/reached-via", json={"via": "network"})
    assert r.status_code == 409 and "abc-sw-a" in r.json()["error"]
    r = c.put(f"/api/devices/{sw}/network-address", json={"address": NET_SW})
    assert r.status_code == 409


def test_console_setup_and_guided_steps_stay_on_the_bench(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    to_network(c, pid, fw, sw)
    r = c.post(f"/api/devices/{sw}/provisioning/console-bootstrap/preview", json={})
    assert r.status_code == 409 and "only on the bench" in r.json()["error"]
    r = c.post(f"/api/devices/{sw}/provisioning/console-bootstrap", json={
        "serial_port": "SIMULATED", "confirm_device_name": "abc-sw-a",
        "profile": {"vlan_id": 222, "vlan_name": "OOBM", "untagged_port": "2",
                    "address": "192.168.1.1/24"}})
    assert r.status_code == 409 and "only on the bench" in r.json()["error"]
    bbu = c.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-bbu", "manufacturer": "Nokia", "category": "other", "model": "FSMF",
        "driver_id": "mock.nokia.flexi", "environment": "simulated",
        "management_address": "192.168.255.1", "management_port": 443}).json()
    assert "id" in bbu, bbu
    if True:
        step = c.get(f"/api/devices/{bbu['id']}/guided").json()["steps"][0]["key"]
        r = c.post(f"/api/devices/{bbu['id']}/guided/{step}", json={"note": "seen it"})
        assert r.status_code == 409 and "only on the bench" in r.json()["error"]


def test_the_system_package_carries_network_addresses_not_where_it_is_reached(env):
    c, _ = env
    pid, fw, sw, _ = make_system(c, real=True)
    to_network(c, pid, fw, sw)
    package = c.get(f"/api/projects/{pid}/export").content
    r = c.post("/api/systems/import", files={"file": ("p.undm", package)},
               data={"name": "Copy B009"})
    assert r.status_code == 201, r.text
    copy = r.json()["project"]
    assert copy["reached_via"] == "bench"
    devices = {d["name"]: d for d in c.get(f"/api/projects/{copy['id']}/devices").json()}
    assert devices["abc-sw-a"]["network_address"] == NET_SW
    assert devices["abc-sw-a"]["environment"] == "lab"  # a copy starts on the bench


def test_ssh_window_uses_the_network_address_and_needs_ssh(env, monkeypatch):
    c, factory = env
    pid, fw, sw, _ = make_system(c, real=True)
    to_network(c, pid, fw, sw)
    with factory() as s:
        argv = devsvc.ssh_command(s.get(Device, sw), default_registry())
    assert argv[-1] == f"admin@{NET_SW}" and BENCH_SW not in argv


def test_reach_of_follows_the_system_unless_told():
    project = Project(name="P", reached_via="network")
    device = Device(name="abc-sw-a", driver_id="mock.aruba.aos_switch",
                    management_address=BENCH_SW, network_address=NET_SW)
    device.project = project
    registry = default_registry()
    assert reach.reach_of(device, registry).address == NET_SW
    assert reach.reach_of(device, registry, "bench").address == BENCH_SW
    with pytest.raises(ConflictError, match="only on the bench"):
        reach.require_bench(project, "plans are made")
    reach.require_bench(Project(name="Q", reached_via="bench"), "plans are made")


def test_in_the_network_every_endpoint_that_reaches_a_device_uses_its_network_address(
        env, monkeypatch):
    c, _ = env
    pid, fw, sw, _ = make_system(c)
    to_network(c, pid, fw, sw)
    from undm.drivers.registry import DriverRegistry

    reached: list[str] = []
    create = DriverRegistry.create

    def recording(self, driver_id, target, credentials=None):
        reached.append(target.management_address)
        return create(self, driver_id, target, credentials)

    monkeypatch.setattr(DriverRegistry, "create", recording)
    monkeypatch.setattr(ssh_base, "tcp_port_open",
                        lambda host, port, timeout=3.0: reached.append(host) or True)
    for device in (fw, sw):
        for op in ("check_reachability", "get_facts", "backup_configuration",
                   "get_firmware_information"):
            r = c.post(f"/api/devices/{device}/operations/{op}")
            assert r.status_code == 200, (op, r.text)
    c.get(f"/api/projects/{pid}/reachability")
    assert reached and set(reached) <= {NET_FW, NET_SW}, reached
    assert BENCH_FW not in reached and BENCH_SW not in reached
