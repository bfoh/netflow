import pytest

from undm.domain.lifecycle import DeploymentState as S
from undm.domain.operations import DeviceOperation as Op
from undm.drivers.base import ApplyMode, DeviceTarget
from undm.drivers.mock.lab import SimulatedDevice, default_lab
from undm.drivers.registry import default_registry
from undm.orchestration.deployment import (
    ApprovalRequiredError,
    Deployment,
    DeploymentOrchestrator,
    DeploymentTarget,
    TargetState,
)

REG = default_registry()
CFG = "hostname {name}\nvlan 10\n name users\n"


def lab_device(addr, running="", **kw):
    kw.setdefault("serial_number", "S-" + addr)
    return default_lab().add(SimulatedDevice(
        address=addr, vendor="Sim", model="SIM", os_version="1", running_config=running, **kw))


def target(name, addr, driver_id="mock.aruba.aoscx", **kw):
    drv = REG.create(driver_id, DeviceTarget(name, addr))
    return DeploymentTarget(name, name, drv, CFG.format(name=name), **kw)


def run(targets, *, dry_run=False, mode=ApplyMode.MERGE):
    orch = DeploymentOrchestrator()
    dep = Deployment("d1", targets, created_by="alice", dry_run=dry_run, apply_mode=mode)
    assert orch.prepare(dep), [e.message for e in dep.events]
    if not dry_run:
        assert dep.state is S.AWAITING_APPROVAL
        orch.approve(dep, "bob")
    return dep, orch.execute(dep)


def test_successful_multi_device_deployment():
    a, b = lab_device("10.0.0.1"), lab_device("10.0.0.2")
    dep, state = run([target("sw1", "10.0.0.1"), target("sw2", "10.0.0.2")])
    assert state is S.SUCCEEDED
    assert all(t.state is TargetState.VERIFIED for t in dep.targets)
    assert "hostname sw1" in a.startup_config and "hostname sw2" in b.running_config
    assert dep.approved_by == "bob"
    lifecycle = [e.status for e in dep.events if e.stage == "lifecycle"]
    assert lifecycle == ["validating", "awaiting_approval", "ready", "preflight", "backing_up",
                         "deploying", "verifying", "succeeded"]


def test_dry_run_is_read_only_and_needs_no_approval():
    dev = lab_device("10.0.0.1", running="hostname old\n")
    dep, state = run([target("sw1", "10.0.0.1")], dry_run=True)
    assert state is S.SUCCEEDED
    assert dev.running_config == "hostname old\n"
    assert dev.checkpoints == {}  # not even a backup checkpoint was written
    assert dep.targets[0].diff.changed


def test_live_execution_requires_approval():
    lab_device("10.0.0.1")
    orch = DeploymentOrchestrator()
    dep = Deployment("d1", [target("sw1", "10.0.0.1")], created_by="alice")
    orch.prepare(dep)
    with pytest.raises(ApprovalRequiredError):
        orch.execute(dep)


def test_separate_approver_policy():
    lab_device("10.0.0.1")
    orch = DeploymentOrchestrator(require_separate_approver=True)
    dep = Deployment("d1", [target("sw1", "10.0.0.1")], created_by="alice")
    orch.prepare(dep)
    with pytest.raises(ApprovalRequiredError):
        orch.approve(dep, "alice")


def test_identity_mismatch_blocks_deployment():
    dev = lab_device("10.0.0.1", running="hostname a\n", serial_number="REAL-1")
    dep, state = run([target("sw1", "10.0.0.1", expected_serial="OTHER-9")])
    assert state is S.FAILED
    assert "identity mismatch" in dep.targets[0].message
    assert dev.running_config == "hostname a\n"


def test_backup_failure_touches_no_device():
    a = lab_device("10.0.0.1", running="hostname a\n")
    lab_device("10.0.0.2", fail_on={Op.BACKUP_CONFIGURATION})
    dep, state = run([target("sw1", "10.0.0.1"), target("sw2", "10.0.0.2")])
    assert state is S.FAILED
    assert a.running_config == "hostname a\n"
    assert not any(t.touched for t in dep.targets)


def test_apply_failure_rolls_back_touched_devices():
    a = lab_device("10.0.0.1", running="hostname a\n")
    lab_device("10.0.0.2", fail_on={Op.APPLY_CONFIGURATION})
    c = lab_device("10.0.0.3", running="hostname c\n")
    dep, state = run([target("sw1", "10.0.0.1"), target("sw2", "10.0.0.2"),
                      target("sw3", "10.0.0.3")])
    assert state is S.ROLLED_BACK
    assert a.running_config == "hostname a\n"
    assert c.running_config == "hostname c\n"  # never attempted
    assert [t.state for t in dep.targets] == [
        TargetState.ROLLED_BACK, TargetState.ROLLED_BACK, TargetState.SKIPPED]


def test_driver_without_rollback_requires_manual_recovery():
    lab_device("10.0.0.1", running="hostname fw\n", ignored_lines={"vlan 10"})
    dep, state = run([target("fw1", "10.0.0.1", "mock.fortinet.fortios")])
    assert state is S.RECOVERY_REQUIRED
    assert dep.targets[0].state is TargetState.MANUAL_RECOVERY_REQUIRED


def test_verification_detects_partial_apply_and_recovers():
    dev = lab_device("10.0.0.1", running="hostname old\n", ignored_lines={"vlan 10"})
    dep, state = run([target("sw1", "10.0.0.1")])
    assert state is S.ROLLED_BACK
    assert dev.running_config == "hostname old\n"
    assert any(e.stage == "verify" and e.status == "error" for e in dep.events)


def test_already_compliant_device_is_not_touched():
    lab_device("10.0.0.1", running=CFG.format(name="sw1"))
    dep, state = run([target("sw1", "10.0.0.1")])
    assert state is S.SUCCEEDED
    assert dep.targets[0].state is TargetState.NO_CHANGE and not dep.targets[0].touched


def test_replace_mode_rejected_for_driver_without_replace():
    lab_device("10.0.0.1")
    orch = DeploymentOrchestrator()
    dep = Deployment("d1", [target("fw1", "10.0.0.1", "mock.fortinet.fortios")],
                     created_by="alice", apply_mode=ApplyMode.REPLACE)
    assert not orch.prepare(dep)
    assert dep.state is S.FAILED


def test_replace_mode_removes_unintended_lines():
    dev = lab_device("10.0.0.1", running="hostname x\nsnmp-server community public\n")
    _, state = run([target("r1", "10.0.0.1", "mock.cisco.iosxe")], mode=ApplyMode.REPLACE)
    assert state is S.SUCCEEDED
    assert "snmp-server" not in dev.running_config


def test_unreachable_device_fails_preview():
    lab_device("10.0.0.1", reachable=False)
    orch = DeploymentOrchestrator()
    dep = Deployment("d1", [target("sw1", "10.0.0.1")], created_by="alice")
    assert not orch.prepare(dep)
    assert dep.state is S.FAILED
    assert dep.targets[0].state is TargetState.PREVIEW_FAILED


def test_events_are_emitted_to_sink():
    lab_device("10.0.0.1")
    seen = []
    orch = DeploymentOrchestrator(sink=lambda d, e: seen.append(e))
    dep = Deployment("d1", [target("sw1", "10.0.0.1")], created_by="alice")
    orch.prepare(dep)
    orch.approve(dep, "bob")
    orch.execute(dep)
    assert seen == dep.events
