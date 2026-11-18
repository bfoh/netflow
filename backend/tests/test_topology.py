from ipaddress import IPv4Interface

import pytest
from api_helpers import FIREWALL, SWITCH, make_client

from undm.domain.topology import LinkInfo, NodeInfo, validate_topology


def codes(issues):
    return [i.code for i in issues]


A = NodeInfo("a", "core",
             {"gi1": IPv4Interface("10.0.0.1/30"), "gi2": IPv4Interface("10.9.9.1/24")},
             frozenset({10, 20}))
B = NodeInfo("b", "edge", {"port1": IPv4Interface("10.0.0.2/30")}, frozenset({10}))
C = NodeInfo("c", "lonely")


def test_valid_routed_link():
    assert validate_topology([A, B], [LinkInfo("l1", "a", "Gi1", "b", "port1", "routed")]) == []


def test_rules():
    issues = validate_topology(
        [A, B, C, NodeInfo("d", "dup", {"x": IPv4Interface("10.0.0.1/24")})],
        [LinkInfo("l1", "a", "gi2", "b", "port1", "routed"),     # subnet mismatch
         LinkInfo("l2", "a", "GI2", "c", "e1", "trunk", (10, 30)),  # gi2 reused; vlan 30 undefined
         LinkInfo("l3", "b", "p2", "b", "p3", "routed"),          # self link
         LinkInfo("l4", "a", "gi3", "b", "p4", "access", (10, 20))])  # access with 2 VLANs
    found = codes(issues)
    for code in ("subnet_mismatch", "interface_used_twice", "vlan_not_defined", "self_link",
                 "access_link_vlan_count", "duplicate_ip", "isolated_device"):
        assert code in found, (code, found)


@pytest.fixture
def client():
    c, _ = make_client()
    with c:
        yield c


def test_topology_api(client):
    pid = client.post("/api/projects", json={"name": "Topo"}).json()["id"]
    sw = client.post(f"/api/projects/{pid}/devices", json=SWITCH).json()["id"]
    fw = client.post(f"/api/projects/{pid}/devices", json=FIREWALL).json()["id"]
    client.put(f"/api/devices/{sw}/intent", json={
        "hostname": "sw1", "vlans": [{"vlan_id": 99}],
        "interfaces": [{"interface": "vlan99", "address": "10.255.0.11/24"}]})
    topo = client.get(f"/api/projects/{pid}/topology").json()
    assert len(topo["nodes"]) == 2 and topo["links"] == []
    assert codes_of(topo) == ["isolated_device", "isolated_device"]
    r = client.post(f"/api/projects/{pid}/topology/links", json={
        "a_device_id": sw, "a_interface": "1/1/48", "b_device_id": fw, "b_interface": "internal1",
        "mode": "trunk", "vlans": [99, 100]})
    assert r.status_code == 201, r.text
    link = r.json()
    topo = client.get(f"/api/projects/{pid}/topology").json()
    assert "vlan_not_defined" in codes_of(topo) and "isolated_device" not in codes_of(topo)
    assert client.post(f"/api/projects/{pid}/topology/links", json={
        "a_device_id": sw, "a_interface": "x", "b_device_id": sw, "b_interface": "y"}
    ).status_code == 400
    assert client.post(f"/api/projects/{pid}/topology/links", json={
        "a_device_id": sw, "a_interface": "x", "b_device_id": fw, "b_interface": "y",
        "mode": "routed", "vlans": [5]}).status_code == 422
    moved = client.put(f"/api/projects/{pid}/topology/positions",
                       json={sw: {"x": 10, "y": 20}}).json()
    assert next(n for n in moved["nodes"] if n["device_id"] == sw)["x"] == 10
    upd = client.put(f"/api/topology/links/{link['id']}", json={
        **{k: link[k] for k in ("a_device_id", "a_interface", "b_device_id", "b_interface")},
        "mode": "access", "vlans": [99]}).json()
    assert upd["mode"] == "access"
    assert client.delete(f"/api/topology/links/{link['id']}").status_code == 204
    assert client.get(f"/api/projects/{pid}/topology").json()["links"] == []
    actions = {a["action"] for a in client.get("/api/audit").json()}
    assert {"topology.link.create", "topology.link.update", "topology.link.delete"} <= actions


def codes_of(topo):
    return [i["code"] for i in topo["issues"]]
