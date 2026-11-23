from datetime import UTC, datetime, timedelta

import pytest

from undm.domain.lifecycle import DeploymentState as S
from undm.domain.operations import DeviceOperation as Op
from undm.domain.versions import compare
from undm.drivers.base import DeviceTarget, FirmwareImageRef
from undm.drivers.mock.lab import SimulatedDevice, default_lab
from undm.drivers.registry import default_registry
from undm.orchestration.deployment import ApprovalRequiredError, Deployment, DeploymentTarget
from undm.orchestration.deployment import TargetState as T
from undm.orchestration.firmware import FirmwareOrchestrator

REG = default_registry()
IMAGE = FirmwareImageRef("10.1.0", "cx-10.1.0.swi", "a" * 64, 1024, "/tmp/none")


def dev(addr, version="10.0.0", **kw):
    return default_lab().add(SimulatedDevice(address=addr, vendor="Sim", model="SIM",
                                             os_version=version, serial_number="S" + addr, **kw))


def tgt(name, addr, driver="mock.aruba.aoscx"):
    return DeploymentTarget(name, name, REG.create(driver, DeviceTarget(name, addr)), "")


def plan(targets, *, dry_run=False, window=True, min_from=None):
    now = datetime.now(UTC)
    return Deployment("f1", targets, created_by="alice", dry_run=dry_run, firmware=IMAGE,
                      min_from_version=min_from,
                      window_start=now - timedelta(minutes=5) if window else None,
                      window_end=now + timedelta(hours=1) if window else None)


def orch():
    return FirmwareOrchestrator(reboot_wait_attempts=2, reboot_wait_delay_s=0)


def run(dep):
    o = orch()
    assert o.prepare(dep), [e.message for e in dep.events]
    if not dep.dry_run:
        o.approve(dep, "bob")
    return o.execute(dep)


def test_version_compare():
    assert compare("17.09.04a", "17.12.1") == -1
    assert compare("FL.10.13.1000", "FL.10.13.1000") == 0
    assert compare("v7.2.8,build1639", "7.2.5") == 1
    assert compare("abc", "1.0") is None


def test_successful_upgrade_reboots_and_verifies():
    a, b = dev("10.0.1.1"), dev("10.0.1.2")
    dep = plan([tgt("sw1", "10.0.1.1"), tgt("sw2", "10.0.1.2")])
    assert run(dep) is S.SUCCEEDED
    assert a.os_version == b.os_version == "10.1.0"
    assert [t.state for t in dep.targets] == [T.VERIFIED, T.VERIFIED]
    assert any("reachable again" in e.message for e in dep.events)


def test_firmware_requires_separate_approver_and_window():
    dev("10.0.1.1")
    o = orch()
    dep = plan([tgt("sw1", "10.0.1.1")])
    o.prepare(dep)
    with pytest.raises(ApprovalRequiredError):
        o.approve(dep, "alice")  # creator cannot approve firmware
    no_window = plan([tgt("sw1", "10.0.1.1")], window=False)
    o.prepare(no_window)
    with pytest.raises(ApprovalRequiredError, match="maintenance window"):
        o.approve(no_window, "bob")


def test_execution_outside_window_is_refused():
    dev("10.0.1.1")
    o = orch()
    dep = plan([tgt("sw1", "10.0.1.1")])
    future = datetime.now(UTC) + timedelta(hours=2)
    dep.window_start, dep.window_end = future, future + timedelta(hours=1)
    o.prepare(dep)
    o.approve(dep, "bob")
    with pytest.raises(ApprovalRequiredError, match="Outside the approved maintenance window"):
        o.execute(dep)


def test_dry_run_changes_nothing():
    d = dev("10.0.1.1")
    dep = plan([tgt("sw1", "10.0.1.1")], dry_run=True, window=False)
    assert run(dep) is S.SUCCEEDED
    assert d.os_version == "10.0.0" and d.staged_firmware is None


@pytest.mark.parametrize("version,min_from,needle", [
    ("11.0.0", None, "downgrades are refused"),
    ("9.0.0", "9.5", "upgrade path"),
    ("unknown", None, "cannot compare"),
])
def test_preview_refuses_bad_version_paths(version, min_from, needle):
    dev("10.0.1.1", version=version)
    dep = plan([tgt("sw1", "10.0.1.1")], min_from=min_from)
    assert not orch().prepare(dep)
    assert dep.state is S.FAILED and needle in dep.targets[0].message


def test_already_on_target_is_skipped():
    d = dev("10.0.1.1", version="10.1.0")
    dep = plan([tgt("sw1", "10.0.1.1")])
    assert run(dep) is S.SUCCEEDED
    assert dep.targets[0].state is T.NO_CHANGE and d.previous_os_version is None


def test_install_failure_rolls_back_earlier_devices_and_stops():
    a = dev("10.0.1.1")
    b = dev("10.0.1.2", fail_on={Op.INSTALL_FIRMWARE})
    c = dev("10.0.1.3")
    dep = plan([tgt("sw1", "10.0.1.1"), tgt("sw2", "10.0.1.2"), tgt("sw3", "10.0.1.3")])
    assert run(dep) is S.ROLLED_BACK
    assert a.os_version == "10.0.0"  # upgraded, then rolled back
    assert b.os_version == "10.0.0" and "nothing to undo" in dep.targets[1].message
    assert c.os_version == "10.0.0" and dep.targets[2].state is T.SKIPPED


def test_device_that_does_not_come_back_needs_manual_recovery():
    dev("10.0.1.1", unreachable_after_reboot=True)
    dep = plan([tgt("sw1", "10.0.1.1")])
    assert run(dep) is S.RECOVERY_REQUIRED
    assert dep.targets[0].state is T.ROLLBACK_FAILED
    assert "console or physical recovery" in dep.targets[0].message


def test_driver_without_firmware_rollback_needs_manual_recovery():
    # FortiOS mock declares no firmware rollback; the reboot fails after the install.
    d = dev("10.0.1.9")
    dep = plan([tgt("fw1", "10.0.1.9", "mock.fortinet.fortios")])
    o = orch()
    o.prepare(dep)
    o.approve(dep, "bob")
    d.fail_on = {Op.REBOOT}
    assert o.execute(dep) is S.RECOVERY_REQUIRED
    assert dep.targets[0].state is T.MANUAL_RECOVERY_REQUIRED


def test_ssh_drivers_cannot_upgrade_firmware():
    dep = plan([tgt("r1", "192.0.2.10", "ssh.cisco.iosxe")])
    assert not orch().prepare(dep)
    assert "cannot perform firmware upgrades" in dep.targets[0].message


def test_aos_switch_style_versions_upgrade_and_roll_back():
    a = dev("10.0.2.1", version="WC.16.10.0010")
    # s1 upgrades fine; s2 fails during install, so s1 must be rolled back.
    b = dev("10.0.2.2", version="WC.16.10.0010", fail_on={Op.INSTALL_FIRMWARE})
    image = FirmwareImageRef("WC.16.11.0003", "WC_16_11_0003.swi", "b" * 64, 1, "/tmp/none")
    now = datetime.now(UTC)
    dep = Deployment("f2", [tgt("s1", "10.0.2.1", "mock.aruba.aos_switch"),
                            tgt("s2", "10.0.2.2", "mock.aruba.aos_switch")],
                     created_by="alice", firmware=image,
                     window_start=now - timedelta(minutes=1), window_end=now + timedelta(hours=1))
    assert run(dep) is S.ROLLED_BACK
    assert a.os_version == b.os_version == "WC.16.10.0010"



def test_reboot_that_keeps_failing_requires_manual_recovery():
    dev("10.0.2.3", version="WC.16.10.0010", fail_on={Op.REBOOT})
    image = FirmwareImageRef("WC.16.11.0003", "WC_16_11_0003.swi", "b" * 64, 1, "/tmp/none")
    now = datetime.now(UTC)
    dep = Deployment("f3", [tgt("s3", "10.0.2.3", "mock.aruba.aos_switch")], created_by="alice",
                     firmware=image, window_start=now - timedelta(minutes=1),
                     window_end=now + timedelta(hours=1))
    assert run(dep) is S.RECOVERY_REQUIRED
    assert dep.targets[0].state is T.ROLLBACK_FAILED


# -- secondary image slot (project standard: approved release in both slots) ---------------
APPROVED = FirmwareImageRef("WC.16.10.0025", "WC_16_10_0025.swi", "c" * 64, 1, "/tmp/none")


def secondary_plan(addr, *, allow_downgrade=False, driver="mock.aruba.aos_switch"):
    now = datetime.now(UTC)
    return Deployment("f-sec", [tgt("s", addr, driver)], created_by="alice", firmware=APPROVED,
                      allow_downgrade=allow_downgrade, also_secondary=True,
                      window_start=now - timedelta(minutes=1), window_end=now + timedelta(hours=1))


def test_secondary_is_written_after_the_primary_runs_the_target():
    d = dev("10.0.3.1", version="WC.16.09.0004", secondary_firmware="WC.16.09.0004")
    dep = secondary_plan("10.0.3.1")
    assert run(dep) is S.SUCCEEDED, [e.message for e in dep.events]
    assert d.os_version == d.secondary_firmware == "WC.16.10.0025"
    messages = [e.message for e in dep.events]
    reboot = next(i for i, m in enumerate(messages) if m.startswith("reboot:"))
    secondary = next(i for i, m in enumerate(messages) if m.startswith("secondary:"))
    assert reboot < secondary  # never both slots changed before the new image has booted
    assert any("secondary WC.16.09.0004 -> WC.16.10.0025" in m for m in messages)  # preview
    assert dep.targets[0].state is T.VERIFIED
    assert messages[-2].endswith("running WC.16.10.0025, secondary WC.16.10.0025")


def test_device_on_target_gets_only_its_secondary_written():
    d = dev("10.0.3.2", version="WC.16.10.0025", secondary_firmware="WC.16.11.0001")
    dep = secondary_plan("10.0.3.2", allow_downgrade=True)
    assert run(dep) is S.SUCCEEDED, [e.message for e in dep.events]
    assert d.secondary_firmware == "WC.16.10.0025"
    messages = [e.message for e in dep.events]
    assert any("only the secondary flash will be written" in m and "DOWNGRADE" in m
               for m in messages)
    assert not any(m.startswith(("stage:", "reboot:")) for m in messages)


def test_newer_secondary_is_kept_unless_the_plan_allows_the_older_version():
    dev("10.0.3.3", version="WC.16.10.0025", secondary_firmware="WC.16.11.0001")
    dep = secondary_plan("10.0.3.3")
    assert not orch().prepare(dep)
    assert "secondary image WC.16.11.0001 is newer" in dep.targets[0].message


def test_both_slots_on_target_is_no_change():
    dev("10.0.3.4", version="WC.16.10.0025", secondary_firmware="WC.16.10.0025")
    dep = secondary_plan("10.0.3.4")
    assert run(dep) is S.SUCCEEDED
    assert dep.targets[0].state is T.NO_CHANGE
    assert any("secondary already WC.16.10.0025" in e.message for e in dep.events)


def test_failed_secondary_keeps_the_verified_primary_and_asks_for_a_check():
    d = dev("10.0.3.5", version="WC.16.09.0004", secondary_firmware="WC.16.09.0004",
            fail_on={Op.STAGE_FIRMWARE_SECONDARY})
    dep = secondary_plan("10.0.3.5")
    assert run(dep) is S.RECOVERY_REQUIRED
    assert d.os_version == "WC.16.10.0025"  # the working new primary is not rolled back
    t = dep.targets[0]
    assert t.state is T.MANUAL_RECOVERY_REQUIRED
    assert "boots from its primary image" in t.message and "show flash" in t.message


def test_secondary_needs_a_driver_that_can_write_it():
    dev("10.0.3.6", version="10.0.0")
    dep = secondary_plan("10.0.3.6", driver="mock.aruba.aoscx")
    assert not orch().prepare(dep)
    assert "secondary image slot procedure" in dep.targets[0].message
