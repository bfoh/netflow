import pytest
from api_helpers import FIREWALL, FIREWALL_INTENT, SWITCH, SWITCH_INTENT, make_client

from undm.db.models import DeploymentRecord, Device
from undm.drivers.mock.lab import default_lab
from undm.services.deployments import recover_interrupted_deployments


@pytest.fixture
def ctx():
    client, factory = make_client()
    with client:
        yield client, factory


@pytest.fixture
def client(ctx):
    return ctx[0]


def project(client, name="Lab A"):
    r = client.post("/api/projects", json={"name": name, "site": "Site 1"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def device(client, pid, body, intent=None):
    r = client.post(f"/api/projects/{pid}/devices", json=body)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    if intent:
        assert client.put(f"/api/devices/{did}/intent", json=intent).status_code == 200
    return did


def generate(client, did):
    r = client.post(f"/api/devices/{did}/configs/generate")
    assert r.status_code == 200 and r.json()["ok"], r.text
    return r.json()["version"]


def test_health_drivers_models(client):
    assert client.get("/api/health").json()["status"] == "ok"
    drivers = client.get("/api/drivers").json()
    assert {d["driver_id"] for d in drivers} == {
        "mock.aruba.aoscx", "mock.fortinet.fortios", "mock.cisco.iosxe", "mock.aruba.aos_switch",
        "mock.blackbox.switch", "mock.nokia.sar", "console.nokia.sar", "mock.nokia.flexi",
        "guided.nokia.flexi",
        "ssh.aruba.aoscx", "ssh.fortinet.fortios", "ssh.cisco.iosxe", "ssh.aruba.aos_switch",
        "ssh.blackbox.lig1014a"}
    for d in drivers:
        assert d["simulated"] == d["driver_id"].startswith("mock.")
        assert d["maturity"] == ("simulation" if d["simulated"] else "experimental")
    assert client.get("/api/policy").json()["enable_real_device_writes"] is False
    models = client.get("/api/device-models").json()
    support = {m["model_id"]: m["support"] for m in models}
    assert support.pop("aruba-2930f") == "lab_read_only"  # acceptance phase A, 2026-11-19
    assert support.pop("blackbox-lig1014a") == "lab_read_only"  # read-only bench, 2026-11-24
    assert support.pop("fortinet-fg-101f") == "lab_read_only"  # base + site on a bench unit
    assert set(support.values()) == {"simulated_only"}


def test_project_crud(client):
    pid = project(client)
    assert client.post("/api/projects", json={"name": "Lab A"}).status_code == 409
    r = client.patch(f"/api/projects/{pid}", json={"description": "updated"})
    assert r.json()["description"] == "updated"
    assert [p["id"] for p in client.get("/api/projects").json()] == [pid]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_timestamps_carry_their_time_zone(client):
    """SQLite keeps no zone; the API must still say the times are UTC (browsers showed
    zone-less times as local time, an hour off on the bench in CET)."""
    from datetime import datetime

    pid = project(client)
    body = client.get(f"/api/projects/{pid}").json()
    for key in ("created_at", "updated_at"):
        value = datetime.fromisoformat(body[key])
        assert value.utcoffset() is not None and value.utcoffset().total_seconds() == 0, body[key]
    did = device(client, pid, SWITCH)
    assert client.post(f"/api/devices/{did}/operations/get_facts").status_code == 200
    seen = client.get(f"/api/devices/{did}").json()["last_connection_at"]
    assert datetime.fromisoformat(seen).utcoffset() is not None


def test_device_inventory_and_validation(client):
    pid = project(client)
    sw = device(client, pid, SWITCH)
    fw = device(client, pid, FIREWALL)
    listed = client.get(f"/api/projects/{pid}/devices").json()
    assert [d["name"] for d in listed] == ["fw1", "sw1"]
    sw_out = client.get(f"/api/devices/{sw}").json()
    assert sw_out["environment"] == "simulated"
    assert "supports_configuration_rollback" in sw_out["capabilities"]
    assert sw_out["observed_facts"] is None  # nothing discovered yet
    assert client.post(f"/api/projects/{pid}/devices", json=SWITCH).status_code == 409
    bad = dict(SWITCH, name="x", driver_id="nope")
    assert client.post(f"/api/projects/{pid}/devices", json=bad).status_code == 400
    r = client.patch(f"/api/devices/{fw}", json={"environment": "production"})
    assert r.status_code == 400 and "simulation" in r.json()["error"]
    assert client.patch(f"/api/devices/{fw}", json={"role": "core-fw"}).json()["role"] == "core-fw"


def test_intent_validation_errors_are_reported(client):
    pid = project(client)
    fw = device(client, pid, FIREWALL, {
        "hostname": "fw1", "static_routes": [{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"}]})
    r = client.post(f"/api/devices/{fw}/configs/generate").json()
    assert not r["ok"] and r["version"] is None
    assert "egress_interface_required" in {i["code"] for i in r["issues"]}
    bad = client.put(f"/api/devices/{fw}/intent", json={"hostname": "bad name"})
    assert bad.status_code == 422


def test_generate_and_version_configs(client):
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    v = generate(client, sw)
    assert "interface vlan 99" in v["text"]
    assert v["verification"] == "docs_reviewed_not_lab_verified"
    generate(client, sw)
    assert len(client.get(f"/api/devices/{sw}/configs").json()) == 2


def test_read_only_operations_and_impacting_forbidden(client):
    pid = project(client)
    sw = device(client, pid, SWITCH)
    r = client.post(f"/api/devices/{sw}/operations/get_facts").json()
    assert r["status"] == "success" and r["data"]["extra"]["simulated"] is True
    dev = client.get(f"/api/devices/{sw}").json()
    assert dev["observed_facts"]["serial_number"].startswith("SIM-")
    assert client.post(f"/api/devices/{sw}/operations/backup_configuration").json()["status"] \
        == "success"
    r = client.post(f"/api/devices/{sw}/operations/reboot")
    assert r.status_code == 403 and "approved deployment" in r.json()["error"]


def test_full_simulated_deployment_flow(client):
    """Directive section 28, steps 3-14."""
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    fw = device(client, pid, FIREWALL, FIREWALL_INTENT)
    generate(client, sw)
    generate(client, fw)
    r = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw, fw]},
                    headers={"X-UNDM-Actor": "alice"})
    assert r.status_code == 201, r.text
    dep = r.json()
    assert dep["state"] == "awaiting_approval"
    assert all(t["diff"] for t in dep["targets"])
    # cannot execute before approval
    assert client.post(f"/api/deployments/{dep['id']}/execute").status_code == 409
    r = client.post(f"/api/deployments/{dep['id']}/approve", headers={"X-UNDM-Actor": "bob"})
    assert r.json()["state"] == "ready" and r.json()["approved_by"] == "bob"
    r = client.post(f"/api/deployments/{dep['id']}/execute", headers={"X-UNDM-Actor": "bob"})
    out = r.json()
    assert out["state"] == "succeeded", out["events"]
    assert {t["state"] for t in out["targets"]} == {"verified"}
    assert all(t["backup_version_id"] for t in out["targets"])
    stages = [e["status"] for e in out["events"] if e["stage"] == "lifecycle"]
    assert stages[-5:] == ["preflight", "backing_up", "deploying", "verifying", "succeeded"]
    sw_after = client.get(f"/api/devices/{sw}").json()
    assert sw_after["deployment_status"] == "in_sync"
    assert sw_after["last_connection_at"] and sw_after["last_backup_at"]
    assert default_lab().get("10.255.0.11").hostname == "sw1"
    actions = {a["action"] for a in client.get("/api/audit").json()}
    assert {"deployment.create", "deployment.approve", "deployment.execute"} <= actions
    actors = {a["actor"] for a in client.get("/api/audit", params={"target_id": dep["id"]}).json()}
    assert actors == {"alice", "bob"}


def test_dry_run_changes_nothing(client):
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    generate(client, sw)
    dep = client.post(f"/api/projects/{pid}/deployments",
                      json={"device_ids": [sw], "dry_run": True}).json()
    assert dep["state"] == "ready"
    out = client.post(f"/api/deployments/{dep['id']}/execute").json()
    assert out["state"] == "succeeded"
    assert default_lab().get("10.255.0.11").running_config == ""
    assert client.get(f"/api/devices/{sw}").json()["deployment_status"] == "never_deployed"


def test_separate_approver_policy():
    client, _ = make_client(require_separate_approver=True)
    with client:
        pid = project(client)
        sw = device(client, pid, SWITCH, SWITCH_INTENT)
        generate(client, sw)
        h = {"X-UNDM-Actor": "alice"}
        dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]},
                          headers=h).json()
        assert client.post(f"/api/deployments/{dep['id']}/approve", headers=h).status_code == 403


def test_deployment_requires_generated_config(client):
    pid = project(client)
    sw = device(client, pid, SWITCH)
    r = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]})
    assert r.status_code == 409 and "generate" in r.json()["error"]


def test_cancel(client):
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    generate(client, sw)
    dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]}).json()
    assert client.post(f"/api/deployments/{dep['id']}/cancel").json()["state"] == "cancelled"
    assert client.post(f"/api/deployments/{dep['id']}/approve").status_code == 409


def test_locked_device_rejects_second_deployment(ctx):
    client, factory = ctx
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    generate(client, sw)
    dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]}).json()
    client.post(f"/api/deployments/{dep['id']}/approve")
    with factory() as s:  # simulate another deployment holding the device
        s.get(Device, sw).locked_by_deployment_id = "other"
        s.commit()
    r = client.post(f"/api/deployments/{dep['id']}/execute")
    assert r.status_code == 409 and "busy" in r.json()["error"]
    assert client.get(f"/api/deployments/{dep['id']}").json()["state"] == "ready"
    assert client.patch(f"/api/devices/{sw}", json={"role": "x"}).status_code == 409


def test_interrupted_deployment_is_resolved_on_restart(ctx):
    client, factory = ctx
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    generate(client, sw)
    dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]}).json()
    with factory() as s:  # simulate a crash while deploying
        s.get(DeploymentRecord, dep["id"]).state = "deploying"
        s.get(Device, sw).locked_by_deployment_id = dep["id"]
        s.commit()
        assert recover_interrupted_deployments(s) == [dep["id"]]
    out = client.get(f"/api/deployments/{dep['id']}").json()
    assert out["state"] == "recovery_required"
    assert "application stopped" in out["events"][-1]["message"]
    d = client.get(f"/api/devices/{sw}").json()
    assert d["deployment_status"] == "unknown" and d["locked_by_deployment_id"] is None


def test_audit_details_are_redacted(client):
    pid = project(client)
    sw = device(client, pid, SWITCH)
    client.patch(f"/api/devices/{sw}", json={"notes": "enable password 0 hunter2"})
    entry = client.get("/api/audit", params={"target_id": sw}).json()[0]
    assert "hunter2" not in str(entry["details"])


def test_list_all_deployments_and_config_diff(client):
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    v1 = generate(client, sw)
    client.put(f"/api/devices/{sw}/intent", json=dict(SWITCH_INTENT, hostname="sw1-new"))
    v2 = generate(client, sw)
    d = client.get("/api/configs/diff", params={"from_version": v1["id"],
                                                "to_version": v2["id"]}).json()
    assert d["changed"] and "+hostname sw1-new" in d["unified"]
    client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]})
    all_deps = client.get("/api/deployments").json()
    assert len(all_deps) == 1 and all_deps[0]["project_id"] == pid
    assert client.get("/api/deployments", params={"state": "succeeded"}).json() == []


def test_import_config_and_deploy_it(client):
    pid = project(client)
    sw = device(client, pid, SWITCH)
    text = "﻿hostname imported-sw\r\nvlan 30\r\n    name lab\r\n"
    r = client.post(f"/api/devices/{sw}/configs/import",
                    json={"filename": "../../etc/sw1 running.cfg", "text": text})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["kind"] == "imported" and v["verification"] == "user_supplied_not_validated"
    assert v["text"] == "hostname imported-sw\nvlan 30\n    name lab\n"  # BOM + CRLF normalised
    assert "/" not in v["reference"]
    # No generated config: the imported one is used by default.
    dep = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]}).json()
    assert dep["targets"][0]["config_version_id"] == v["id"]
    client.post(f"/api/deployments/{dep['id']}/approve")
    out = client.post(f"/api/deployments/{dep['id']}/execute").json()
    assert out["state"] == "succeeded", out["events"]
    assert default_lab().get("10.255.0.11").hostname == "imported-sw"
    audit = client.get("/api/audit", params={"target_id": sw}).json()
    entry = next(a for a in audit if a["action"] == "config.import")
    assert "text" not in entry["details"] and entry["details"]["lines"] == 3


def test_explicit_config_version_choice(client):
    pid = project(client)
    sw = device(client, pid, SWITCH, SWITCH_INTENT)
    gen = generate(client, sw)
    imp = client.post(f"/api/devices/{sw}/configs/import",
                      json={"filename": "a.cfg", "text": "hostname from-file\n"}).json()
    default = client.post(f"/api/projects/{pid}/deployments", json={"device_ids": [sw]}).json()
    assert default["targets"][0]["config_version_id"] == gen["id"]  # generated preferred
    chosen = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [sw], "config_versions": {sw: imp["id"]}}).json()
    assert chosen["targets"][0]["config_version_id"] == imp["id"]
    other = device(client, pid, dict(SWITCH, name="sw2", management_address="10.255.0.12"))
    r = client.post(f"/api/projects/{pid}/deployments", json={
        "device_ids": [other], "config_versions": {other: imp["id"]}})
    assert r.status_code == 404  # version belongs to another device


@pytest.mark.parametrize("text,msg", [("", "empty"), ("a\x00b", "binary"),
                                      ("x" * (2 * 1024 * 1024 + 1), "larger")])
def test_import_rejects_bad_files(client, text, msg):
    pid = project(client)
    sw = device(client, pid, SWITCH)
    r = client.post(f"/api/devices/{sw}/configs/import", json={"filename": "f.cfg", "text": text})
    assert r.status_code == 400 and msg in r.json()["error"]


def test_a_real_device_without_a_login_says_so_in_plain_words(client):
    """Bench 2026-11-25: a firmware plan for 2930F switches whose login was not chosen yet."""
    pid = client.post("/api/projects", json={"name": "Bench"}).json()["id"]
    did = client.post(f"/api/projects/{pid}/devices", json={
        "name": "bench-sw-a", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
        "os_family": "ArubaOS-Switch", "driver_id": "ssh.aruba.aos_switch",
        "environment": "lab", "management_address": "192.0.2.10"}).json()["id"]
    r = client.post(f"/api/devices/{did}/operations/check_reachability")
    assert r.status_code == 400
    assert r.json()["error"].startswith("bench-sw-a has no login chosen. Choose one on its "
                                         "device page (Edit)")
    assert "credential reference" not in r.json()["error"]

