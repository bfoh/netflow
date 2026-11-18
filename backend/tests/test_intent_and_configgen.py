import pytest
from pydantic import ValidationError

from undm.configgen.engine import PLATFORMS, generate
from undm.domain.intent import DeviceIntent
from undm.domain.validation import Severity, validate_intent


def intent(**kw):
    base = {"hostname": "core-sw-1"}
    base.update(kw)
    return DeviceIntent.model_validate(base)


def codes(issues):
    return {i.code for i in issues}


def test_hostname_rules():
    with pytest.raises(ValidationError):
        intent(hostname="bad name")
    with pytest.raises(ValidationError):
        intent(hostname="-leading")


def test_vlan_range_enforced():
    with pytest.raises(ValidationError):
        intent(vlans=[{"vlan_id": 4095}])


def test_semantic_validation():
    i = intent(
        vlans=[{"vlan_id": 10}, {"vlan_id": 10}],
        interfaces=[
            {"interface": "vlan10", "address": "10.0.10.1/24"},
            {"interface": "vlan20", "address": "10.0.10.2/25"},
            {"interface": "Gi1", "address": "10.9.9.0/24"},
        ],
        static_routes=[{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"}],
    )
    found = codes(validate_intent(i))
    assert {"duplicate_vlan", "overlapping_subnets", "invalid_host_address",
            "svi_without_vlan", "next_hop_not_connected"} <= found


def test_iosxe_rendering_golden():
    i = intent(
        vlans=[{"vlan_id": 10, "name": "users"}],
        interfaces=[
            {"interface": "vlan10", "address": "10.0.10.1/24", "description": "users gw"},
            {"interface": "GigabitEthernet1", "address": "192.0.2.2/30", "enabled": False},
        ],
        static_routes=[{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"}],
    )
    r = generate(i, "iosxe")
    assert r.ok, r.issues
    assert r.text == (
        "hostname core-sw-1\n"
        "vlan 10\n name users\n"
        "interface Vlan10\n description users gw\n ip address 10.0.10.1 255.255.255.0\n"
        " no shutdown\n"
        "interface GigabitEthernet1\n ip address 192.0.2.2 255.255.255.252\n shutdown\n"
        "ip route 0.0.0.0 0.0.0.0 192.0.2.1\n"
    )
    assert r.verification.value == "docs_reviewed_not_lab_verified"


def test_aoscx_rejects_physical_routed_port():
    r = generate(intent(interfaces=[{"interface": "1/1/1", "address": "10.0.0.1/24"}]), "aoscx")
    assert not r.ok
    assert "feature_not_supported_by_platform" in codes(r.issues)


def test_aoscx_rendering():
    r = generate(
        intent(vlans=[{"vlan_id": 20}],
               interfaces=[{"interface": "vlan20", "address": "10.0.20.1/24"}],
               static_routes=[{"prefix": "0.0.0.0/0", "next_hop": "10.0.20.254"}]),
        "aoscx",
    )
    assert r.ok
    assert "interface vlan 20\n    ip address 10.0.20.1/24\n" in r.text
    assert "ip route 0.0.0.0/0 10.0.20.254" in r.text


def test_fortios_requires_route_egress_and_rejects_vlans():
    r = generate(
        intent(vlans=[{"vlan_id": 5}],
               static_routes=[{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"}]),
        "fortios",
    )
    assert not r.ok
    assert {"egress_interface_required", "feature_not_supported_by_platform"} <= codes(r.issues)


def test_fortios_rendering():
    r = generate(
        intent(hostname="edge-fw-1",
               interfaces=[{"interface": "port1", "address": "192.0.2.2/30"}],
               static_routes=[{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1",
                               "egress_interface": "port1"}]),
        "fortios",
    )
    assert r.ok, r.issues
    assert 'set hostname "edge-fw-1"' in r.text
    assert "set dst 0.0.0.0 0.0.0.0" in r.text and 'set device "port1"' in r.text


def test_warnings_do_not_block_generation():
    r = generate(intent(interfaces=[{"interface": "vlan30", "address": "10.3.0.1/24"}]), "iosxe")
    assert r.ok
    assert all(i.severity is Severity.WARNING for i in r.issues)


@pytest.mark.parametrize("platform", sorted(PLATFORMS))
def test_generation_is_deterministic(platform):
    i = intent()
    assert generate(i, platform).sha256 == generate(i, platform).sha256


def test_aos_switch_rendering_groups_settings_per_vlan():
    r = generate(intent(
        hostname="lab-2930f",
        vlans=[{"vlan_id": 10, "name": "users"}, {"vlan_id": 99, "name": "mgmt"}],
        interfaces=[{"interface": "vlan99", "address": "10.255.0.21/24"}],
        static_routes=[{"prefix": "0.0.0.0/0", "next_hop": "10.255.0.1"}]), "aos_switch")
    assert r.ok, r.issues
    assert r.text == (
        'hostname "lab-2930f"\n'
        'vlan 10\n   name "users"\n   exit\n'
        'vlan 99\n   name "mgmt"\n   ip address 10.255.0.21 255.255.255.0\n   exit\n'
        "ip route 0.0.0.0 0.0.0.0 10.255.0.1\n"
    )
    assert "aos_switch_routes_need_ip_routing" in codes(r.issues)


def test_aos_switch_rejects_routed_ports_and_descriptions():
    r = generate(intent(interfaces=[{"interface": "1", "address": "10.0.0.1/24"},
                                    {"interface": "vlan5", "address": "10.5.0.1/24",
                                     "description": "x"}]), "aos_switch")
    assert not r.ok
    assert codes(r.issues) >= {"feature_not_supported_by_platform"}
