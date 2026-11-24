"""Plans that need attention: cleared by a later success or a recorded check; deleting
plans (D-088). Simulated devices."""

import time

import pytest
from api_helpers import FIREWALL, FIREWALL_INTENT, SWITCH, SWITCH_INTENT, make_client

from undm.db.models import DeploymentRecord, Device


@pytest.fixture
def ctx():
    client, factory = make_client()
    with client:
        yield client, factory


def setup(client):
    pid = client.post("/api/projects", json={"name": "Lab A"}).json()["id"]
    ids = []
    for body, intent in ((SWITCH, SWITCH_INTENT), (FIREWALL, FIREWALL_INTENT)):
        did = client.post(f"/api/projects/{pid}/devices", json=body).json()["id"]
        client.put(f"/api/devices/{did}/intent", json=intent)
        client.post(f"/api/devices/{did}/configs/generate")
        ids.append(did)
    return pid, ids


def plan(client, pid, devices, dry_run=False):
    dep = client.post(f"/api/projects/{pid}/deployments",
                      json={"device_ids": devices, "dry_run": dry_run}).json()
    assert dep["state"] in ("awaiting_approval", "ready"), dep
    return dep


def run(client, dep):
    if dep["state"] == "awaiting_approval":
        client.post(f"/api/deployments/{dep['id']}/approve")
    return client.post(f"/api/deployments/{dep['id']}/execute").json()


def needs_attention(factory, dep_id):
    with factory() as s:  # as left by a run that stopped while changing the device
        s.get(DeploymentRecord, dep_id).state = "recovery_required"
        s.commit()


def flags(client, pid, dep_id):
    rows = {r["id"]: r for r in client.get(f"/api/projects/{pid}/deployments").json()}
    return rows[dep_id]["needs_attention"], rows[dep_id]["attention_cleared"]


def test_waits_until_a_later_real_plan_succeeds_on_all_its_devices(ctx):
    client, factory = ctx
    pid, (sw, fw) = setup(client)
    bad = plan(client, pid, [sw, fw])
    needs_attention(factory, bad["id"])
    assert flags(client, pid, bad["id"]) == (True, None)
    assert client.get("/api/deployments").json()[0]["needs_attention"] is True
    time.sleep(0.01)
    assert run(client, plan(client, pid, [sw], dry_run=True))["state"] == "succeeded"
    assert flags(client, pid, bad["id"]) == (True, None)  # a dry run changes nothing
    assert run(client, plan(client, pid, [sw]))["state"] == "succeeded"
    assert flags(client, pid, bad["id"]) == (True, None)  # one device of two only
    later = run(client, plan(client, pid, [sw, fw]))
    assert later["state"] == "succeeded"
    assert flags(client, pid, bad["id"]) == (False, f"superseded:{later['id']}")
    out = client.get(f"/api/deployments/{bad['id']}").json()
    assert out["state"] == "recovery_required"  # its own outcome is kept
    assert out["attention_cleared"] == f"superseded:{later['id']}"


def test_a_person_marks_it_checked_with_a_note(ctx):
    client, factory = ctx
    pid, (sw, _) = setup(client)
    dep = plan(client, pid, [sw])
    r = client.post(f"/api/deployments/{dep['id']}/checked", json={"note": "looked at it"})
    assert r.status_code == 409 and "needs attention" in r.json()["error"]  # not that state
    needs_attention(factory, dep["id"])
    r = client.post(f"/api/deployments/{dep['id']}/checked", json={"note": "  ok "})
    assert r.status_code == 409 and "what you checked" in r.json()["error"]
    r = client.post(f"/api/deployments/{dep['id']}/checked", headers={"X-UNDM-Actor": "bob"},
                    json={"note": "show running-config matches the file"})
    out = r.json()
    assert r.status_code == 200 and out["state"] == "recovery_required"
    assert (out["needs_attention"], out["attention_cleared"]) == (False, "checked")
    assert out["events"][-1]["message"] == ("device checked by bob: show running-config "
                                            "matches the file")
    audit = client.get("/api/audit").json()
    assert any(a["action"] == "deployment.checked" and a["actor"] == "bob" for a in audit)


def test_a_finished_plan_can_be_deleted_and_the_audit_keeps_it(ctx):
    client, _ = ctx
    pid, (sw, _) = setup(client)
    dep = run(client, plan(client, pid, [sw]))
    assert client.delete(f"/api/deployments/{dep['id']}").status_code == 204
    assert client.get(f"/api/deployments/{dep['id']}").status_code == 404
    gone = [a for a in client.get("/api/audit").json() if a["action"] == "deployment.delete"]
    assert gone[0]["details"]["state"] == "succeeded" and gone[0]["details"]["devices"] == [sw]


def test_a_running_plan_cannot_be_deleted(ctx):
    client, factory = ctx
    pid, (sw, _) = setup(client)
    dep = plan(client, pid, [sw])
    with factory() as s:
        s.get(DeploymentRecord, dep["id"]).state = "deploying"
        s.get(Device, sw).locked_by_deployment_id = dep["id"]
        s.commit()
    r = client.delete(f"/api/deployments/{dep['id']}")
    assert r.status_code == 409 and "running" in r.json()["error"]


def test_deleting_a_step_deletes_its_whole_staging_plan(ctx):
    client, factory = ctx
    pid, (sw, _) = setup(client)
    a, b = plan(client, pid, [sw]), plan(client, pid, [sw])
    with factory() as s:  # two steps of one staging plan
        for n, d in enumerate((a, b), 1):
            rec = s.get(DeploymentRecord, d["id"])
            rec.staging_id, rec.staging_step = "stg-1", n
        s.commit()
    assert client.delete(f"/api/deployments/{a['id']}").status_code == 204
    assert client.get(f"/api/deployments/{b['id']}").status_code == 404  # step 2 went too
