"""The addresses a device's files give it, read offline (D-125), and the suggestion for its
network address. Synthetic files only: fictional names, RFC 1918 / RFC 5737 addresses."""

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.drivers.aruba.config_files import file_addresses as aruba
from undm.drivers.blackbox.config_files import blackbox_file_addresses as blackbox
from undm.drivers.fortinet.config_files import file_addresses as fortios
from undm.drivers.nokia.sar_files import file_addresses as sros
from undm.services import reach

ARUBA = """; JL260A Configuration Editor; Created on release #WC.16.10.0025
hostname "abc-sw-a"
vlan 1
   name "DEFAULT_VLAN"
   no untagged 2
   no ip address
   exit
vlan 222
   name "OOBM"
   untagged 2
   ip address 192.168.1.1 255.255.255.0
   exit
vlan 310
   name "MGMT"
   tagged 49
   ip address 198.51.100.11 255.255.255.0
   exit
ip authorized-managers 192.168.1.0 255.255.255.0 access manager
ip authorized-managers 198.51.100.0 255.255.255.0 access manager access-method ssh
"""

BLACKBOX = """hostname abc-tetra
!
interface GigabitEthernet 1/3
 switchport access vlan 168
!
interface vlan 168
 ip address 192.0.2.1 255.255.255.0
!
interface vlan 400
 ip address 198.51.100.21 255.255.255.0
!
access management
access management 1 168 192.0.2.50 to 192.0.2.60 ssh
access management 2 400 198.51.100.0 to 198.51.100.255
end
"""

FORTIOS = """config system admin
    edit "admin"
        set trusthost1 198.51.100.0 255.255.255.0
        set trusthost2 0.0.0.0 0.0.0.0
    next
end
config system interface
    edit "mgmt"
        set vdom "root"
        set ip 192.168.1.99 255.255.255.0
        set allowaccess ping https ssh
    next
    edit "port3"
        set vdom "root"
        set ip 198.51.100.1 255.255.255.0
        set allowaccess ping https ssh
    next
    edit "port4"
        set vdom "root"
        set ip 203.0.113.1 255.255.255.248
        set allowaccess ping
    next
    edit "port5"
        set vdom "root"
    next
end
config system snmp community
    edit 1
        config hosts
            edit 1
                set ip 198.51.100.200 255.255.255.255
            next
        end
    next
end
"""

SROS = """# TiMOS-B-20.5.R1 both/hops NOKIA SAR-Hmc
exit all
configure
    system
        name "abc-modem"
    exit
    router Base
        interface "system"
            address 203.0.113.30/32
            no shutdown
        exit
    exit
    service
        ies 1 name "ies-1" customer 1 create
            interface "mgmt" create
                address 198.51.100.31/24
            exit
        exit
    exit
exit all
"""


def test_the_2930f_file_gives_its_vlan_addresses_and_managers():
    got = aruba(ARUBA)
    assert [(a.address, a.prefix, a.where) for a in got.addresses] == [
        ("192.168.1.1", 24, "VLAN 222"), ("198.51.100.11", 24, "VLAN 310")]
    assert ARUBA.splitlines()[got.addresses[1].line - 1].strip().startswith("ip address 198.")
    assert [(m.first, m.last) for m in got.managers] == [
        ("192.168.1.0", "192.168.1.255"), ("198.51.100.0", "198.51.100.255")]


def test_the_black_box_file_gives_its_vlan_interfaces_and_access_ranges():
    got = blackbox(BLACKBOX)
    assert got is not None
    assert [(a.address, a.where) for a in got.addresses] == [
        ("192.0.2.1", "VLAN 168"), ("198.51.100.21", "VLAN 400")]
    assert [(m.first, m.last) for m in got.managers] == [
        ("192.0.2.50", "192.0.2.60"), ("198.51.100.0", "198.51.100.255")]
    assert blackbox("<?xml version='1.0'?><configuration/>") is None  # LE2700A: typed


def test_the_fortios_file_gives_interfaces_with_vdom_and_access_not_snmp_hosts():
    got = fortios(FORTIOS)
    assert [(a.address, a.prefix, a.where, a.vdom, a.allows) for a in got.addresses] == [
        ("192.168.1.99", 24, 'interface "mgmt"', "root", "ping https ssh"),
        ("198.51.100.1", 24, 'interface "port3"', "root", "ping https ssh"),
        ("203.0.113.1", 29, 'interface "port4"', "root", "ping")]
    # Trusted hosts of the admins; 0.0.0.0/0 means any and is not a limit.
    assert [(m.first, m.last, m.text) for m in got.managers] == [
        ("198.51.100.0", "198.51.100.255", "198.51.100.0/24 (admin admin)")]


def test_the_modem_file_gives_its_interface_addresses():
    got = sros(SROS)
    assert [(a.address, a.prefix, a.where) for a in got.addresses] == [
        ("203.0.113.30", 32, 'interface "system"'), ("198.51.100.31", 24, 'interface "mgmt"')]
    assert got.managers == ()


@pytest.fixture
def client(tmp_path, monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    monkeypatch.setattr(reach, "_pc_address_towards", lambda address: "198.51.100.50")
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def _system(c):
    pid = c.post("/api/projects", json={"name": "Practice B007"}).json()["id"]

    def add(name, category, driver, address, text, filename):
        did = c.post(f"/api/projects/{pid}/devices", json={
            "name": name, "manufacturer": "x", "category": category, "driver_id": driver,
            "management_address": address}).json()["id"]
        c.post(f"/api/devices/{did}/configs/import", json={"filename": filename, "text": text})
        return did

    fw = add("abc-fw", "firewall", "mock.fortinet.fortios", "192.168.1.99", FORTIOS,
             "abc-fw.cfg")
    sw = add("abc-sw-a", "switch", "mock.aruba.aos_switch", "192.168.1.1", ARUBA, "abc-sw-a.pcc")
    modem = add("abc-modem", "router", "mock.nokia.sar", "", SROS, "abc-modem.txt")
    return pid, fw, sw, modem


def test_a_single_address_off_the_bench_is_suggested_with_where_it_is(client):
    pid, fw, sw, modem = _system(client)
    out = client.get(f"/api/devices/{sw}/file-addresses").json()
    assert out["reader"] is True and out["files"][0]["loaded"] is False  # not loaded by UNDM
    assert {a["address"]: a["on_bench"] for a in out["addresses"]} == {
        "192.168.1.1": True, "198.51.100.11": False}
    assert out["suggested"] == "198.51.100.11"
    assert out["pc_address"] == "198.51.100.50" and out["pc_allowed"] is True
    fw_out = client.get(f"/api/devices/{fw}/file-addresses").json()
    assert fw_out["suggested"] == "198.51.100.1"  # the only one off the bench with SSH
    assert "SSH" in fw_out["reason"]


def test_a_tie_is_broken_by_the_bfw_networks_or_left_to_the_person(client):
    pid, fw, sw, modem = _system(client)
    out = client.get(f"/api/devices/{modem}/file-addresses").json()
    assert {a["address"] for a in out["addresses"]} == {"203.0.113.30", "198.51.100.31"}
    # Both lie in networks of the BFW's file (port3 /24 and port4 /29 hold neither /32)...
    assert out["suggested"] == "198.51.100.31" and "BFW" in out["reason"]


def test_the_route_hint_goes_through_the_bfw_and_is_only_shown(client):
    pid, fw, sw, modem = _system(client)
    client.put(f"/api/devices/{fw}/network-address", json={"address": "203.0.113.1"})
    client.put(f"/api/devices/{sw}/network-address", json={"address": "198.51.100.11"})
    out = client.get(f"/api/devices/{sw}/file-addresses").json()
    assert out["route_hint"] == "route add 198.51.100.0 mask 255.255.255.0 203.0.113.1"
    assert client.get(f"/api/devices/{fw}/file-addresses").json()["route_hint"] is None


def test_a_pc_outside_the_files_limits_is_said(client, monkeypatch):
    monkeypatch.setattr(reach, "_pc_address_towards", lambda address: "192.0.2.77")
    pid, fw, sw, modem = _system(client)
    out = client.get(f"/api/devices/{sw}/file-addresses").json()
    assert out["pc_address"] == "192.0.2.77" and out["pc_allowed"] is False


def test_the_files_of_the_latest_staging_plan_are_read_in_step_order(client):
    pid = client.post("/api/projects", json={"name": "Practice B009"}).json()["id"]
    fw = client.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-fw", "manufacturer": "Fortinet", "category": "firewall",
        "driver_id": "mock.fortinet.fortios", "management_address": "192.168.1.99"}).json()["id"]
    base = client.post(f"/api/devices/{fw}/configs/import", json={
        "filename": "base.conf", "text": "#config-version=FG101F-7.6.5\n"
        "config system interface\n    edit \"mgmt\"\n        set ip 192.168.1.99 255.255.255.0\n"
        "        set allowaccess ping https ssh\n    next\nend\n"}).json()["id"]
    site = client.post(f"/api/devices/{fw}/configs/import", json={
        "filename": "site.cfg", "text": FORTIOS.split("config system snmp")[0]}).json()["id"]
    made = client.post(f"/api/projects/{pid}/device-staging", json={"device_id": fw, "steps": [
        {"kind": "configuration", "version_id": base, "apply_mode": "merge"},
        {"kind": "configuration", "version_id": site, "apply_mode": "merge"}]}).json()
    sid = made["staging_id"]
    client.post(f"/api/staging-plans/{sid}/approve")
    done = client.post(f"/api/staging-plans/{sid}/execute?background=false").json()
    assert all(s["state"] == "succeeded" for s in done["steps"]), done
    out = client.get(f"/api/devices/{fw}/file-addresses").json()
    assert [f["name"] for f in out["files"]] == ["base.conf", "site.cfg"]
    assert all(f["loaded"] for f in out["files"])
