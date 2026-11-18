"""Deployment orchestrator.

Pure application logic: it works on drivers and plain data, and reports every
step through an event sink. Persistence, audit, locking and background
execution live in other layers.

Safety rules enforced here:
* Live execution requires an explicit approval; dry runs perform only
  read-only operations (connect, identity check, read running config, diff).
* Preflight (connect, identity, capabilities) and backup must succeed for
  *every* target before *any* device is changed.
* A device is never assumed changed or unchanged because a command was sent:
  success is decided by reading the configuration back (verification).
* After the first change, any failure triggers recovery of every touched
  device. Devices whose driver cannot roll back are reported as requiring
  manual recovery; the deployment then ends RECOVERY_REQUIRED.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from undm.configgen.diff import ConfigDiff, diff_configs, normalize
from undm.domain.lifecycle import DeploymentState, transition
from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigurationBackup,
    DeviceDriver,
    FirmwareImageRef,
    ResultStatus,
)

S = DeploymentState


class TargetState(StrEnum):
    PENDING = "pending"
    PREVIEWED = "previewed"
    PREVIEW_FAILED = "preview_failed"
    PREFLIGHT_PASSED = "preflight_passed"
    PREFLIGHT_FAILED = "preflight_failed"
    BACKED_UP = "backed_up"
    BACKUP_FAILED = "backup_failed"
    APPLIED = "applied"
    APPLY_FAILED = "apply_failed"
    VERIFIED = "verified"
    VERIFY_FAILED = "verify_failed"
    NO_CHANGE = "no_change"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"
    ROLLBACK_FAILED = "rollback_failed"
    MANUAL_RECOVERY_REQUIRED = "manual_recovery_required"


@dataclass
class DeploymentTarget:
    device_id: str
    device_name: str
    driver: DeviceDriver
    intended_config: str
    # Serial number recorded in inventory; preflight refuses a device that reports another.
    expected_serial: str | None = None
    state: TargetState = TargetState.PENDING
    diff: ConfigDiff | None = None
    backup: ConfigurationBackup | None = None
    touched: bool = False  # an impacting operation was attempted on the device
    message: str = ""
    # firmware deployments only
    current_version: str | None = None
    target_version: str | None = None
    from_version: str | None = None  # version found at preflight


@dataclass(frozen=True)
class DeploymentEvent:
    timestamp: datetime
    stage: str
    status: str
    message: str
    device_id: str | None = None


@dataclass
class Deployment:
    deployment_id: str
    targets: list[DeploymentTarget]
    created_by: str
    apply_mode: ApplyMode = ApplyMode.MERGE
    dry_run: bool = False
    state: DeploymentState = S.DRAFT
    approved_by: str | None = None
    approved_at: datetime | None = None
    events: list[DeploymentEvent] = field(default_factory=list)
    # firmware deployments only
    firmware: FirmwareImageRef | None = None
    min_from_version: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


class ApprovalRequiredError(PermissionError):
    pass


EventSink = Callable[[Deployment, DeploymentEvent], None]


class DeploymentOrchestrator:
    def __init__(
        self, sink: EventSink | None = None, *, require_separate_approver: bool = False
    ) -> None:
        self._sink = sink
        self.require_separate_approver = require_separate_approver

    # -- bookkeeping ----------------------------------------------------------------
    def _emit(
        self, dep: Deployment, stage: str, status: str, message: str,
        target: DeploymentTarget | None = None,
    ) -> None:
        ev = DeploymentEvent(
            datetime.now(UTC), stage, status, message, target.device_id if target else None
        )
        dep.events.append(ev)
        if self._sink:
            self._sink(dep, ev)

    def _move(self, dep: Deployment, new_state: DeploymentState, message: str = "") -> None:
        previous = dep.state
        dep.state = transition(dep.state, new_state)
        self._emit(dep, "lifecycle", new_state.value,
                   message or f"{previous.value} -> {new_state.value}")

    # -- validate + preview ---------------------------------------------------------
    def prepare(self, dep: Deployment) -> bool:
        """Validate the plan and preview the change on every device (read-only)."""
        self._move(dep, S.VALIDATING)
        if not self._validate(dep) or not self._preview(dep):
            self._move(dep, S.FAILED, "validation or preview failed; no device was changed")
            return False
        self._move(dep, S.READY if dep.dry_run else S.AWAITING_APPROVAL)
        return True

    def _validate(self, dep: Deployment) -> bool:
        problems: list[tuple[str, DeploymentTarget | None]] = []
        if not dep.targets:
            problems.append(("deployment has no targets", None))
        seen: set[str] = set()
        for t in dep.targets:
            if t.device_id in seen:
                problems.append((f"device {t.device_name} listed twice", t))
            seen.add(t.device_id)
            if not normalize(t.intended_config):
                problems.append(("intended configuration is empty", t))
            missing = t.driver.missing_capabilities(DeviceOperation.APPLY_CONFIGURATION)
            missing |= t.driver.missing_capabilities(DeviceOperation.BACKUP_CONFIGURATION)
            if missing:
                problems.append(
                    (f"driver lacks {', '.join(sorted(m.value for m in missing))}", t)
                )
            if (dep.apply_mode is ApplyMode.REPLACE
                    and Capability.CONFIGURATION_REPLACE not in t.driver.capabilities()):
                problems.append(("driver does not support replace mode", t))
        for message, target in problems:
            if target is not None:
                target.message = message
            self._emit(dep, "validate", "error", message, target)
        if not problems:
            self._emit(dep, "validate", "ok", f"{len(dep.targets)} target(s) valid")
        return not problems

    def _preview(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            try:
                conn = t.driver.connect()
                if not conn.ok:
                    ok = self._fail_target(dep, t, "preview", TargetState.PREVIEW_FAILED,
                                           conn.message)
                    continue
                running = t.driver.get_running_configuration()
                if not running.ok:
                    ok = self._fail_target(dep, t, "preview", TargetState.PREVIEW_FAILED,
                                           running.message)
                    continue
                t.diff = self._preview_diff(dep, t, running.data)
                t.state = TargetState.PREVIEWED
                self._emit(dep, "preview", "ok", f"+{t.diff.added} -{t.diff.removed} lines", t)
            finally:
                t.driver.disconnect()
        return ok

    # -- approval -------------------------------------------------------------------
    def approve(self, dep: Deployment, approver: str) -> None:
        if dep.dry_run:
            raise ValueError("Dry runs do not need approval")
        if self.require_separate_approver and approver == dep.created_by:
            raise ApprovalRequiredError("Approver must differ from the deployment creator")
        dep.approved_by = approver
        dep.approved_at = datetime.now(UTC)
        self._move(dep, S.READY, f"approved by {approver}")

    # -- execution ------------------------------------------------------------------
    def execute(self, dep: Deployment) -> DeploymentState:
        if dep.state is not S.READY:
            raise ApprovalRequiredError(f"Deployment must be ready to execute (is {dep.state})")
        if not dep.dry_run and not dep.approved_by:
            raise ApprovalRequiredError("Live deployments must be approved before execution")
        try:
            self._move(dep, S.PREFLIGHT)
            if not self._preflight(dep):
                self._move(dep, S.FAILED, "preflight failed; no device was changed")
                return dep.state
            if dep.dry_run:
                self._move(dep, S.SUCCEEDED, "dry run complete; no device was changed")
                return dep.state
            self._move(dep, S.BACKING_UP)
            if not self._backup_all(dep):
                self._move(dep, S.FAILED, "backup failed; no device was changed")
                return dep.state
            self._move(dep, S.DEPLOYING)
            if not self._apply_all(dep):
                return self._recover(dep)
            self._move(dep, S.VERIFYING)
            if not self._verify_all(dep):
                return self._recover(dep)
            self._move(dep, S.SUCCEEDED)
            return dep.state
        finally:
            for t in dep.targets:
                t.driver.disconnect()

    # -- internals ------------------------------------------------------------------
    def _fail_target(
        self, dep: Deployment, t: DeploymentTarget, stage: str, state: TargetState, message: str
    ) -> bool:
        t.state, t.message = state, message
        self._emit(dep, stage, "error", message, t)
        return False

    def _preflight(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            conn = t.driver.connect()
            if not conn.ok:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       conn.message)
                continue
            facts = t.driver.get_device_facts()
            if facts.status is ResultStatus.FAILED:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       f"could not read device identity: {facts.message}")
                continue
            if t.expected_serial and facts.ok and facts.data.serial_number != t.expected_serial:
                ok = self._fail_target(
                    dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                    f"identity mismatch: inventory serial {t.expected_serial}, device reports "
                    f"{facts.data.serial_number}",
                )
                continue
            running = t.driver.get_running_configuration()
            if not running.ok:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       running.message)
                continue
            t.diff = self._preview_diff(dep, t, running.data)
            t.state = TargetState.PREFLIGHT_PASSED
            self._emit(dep, "preflight", "ok",
                       f"reachable, identity ok; +{t.diff.added} -{t.diff.removed} lines", t)
        return ok

    def _backup_all(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            backup = t.driver.backup_configuration()
            if not backup.ok:
                ok = self._fail_target(dep, t, "backup", TargetState.BACKUP_FAILED,
                                       f"backup failed: {backup.message}")
                continue
            t.backup = backup.data
            t.state = TargetState.BACKED_UP
            self._emit(dep, "backup", "ok", f"backup {t.backup.reference}", t)
        return ok

    @staticmethod
    def _preview_diff(dep: Deployment, t: DeploymentTarget, running: str) -> ConfigDiff:
        """What the deployment will change.

        Replace mode: a full diff (lines not in the intended config are removed).
        Merge mode: nothing is removed, so show the intended lines only, marking each as
        "+" (will be added) or unchanged (already on the device). Showing the whole running
        configuration as removed would misrepresent a merge.
        """
        if dep.apply_mode is ApplyMode.REPLACE:
            return diff_configs(running, t.intended_config, t.device_name)
        present = t.driver.present_lines(running)
        lines = [f"--- {t.device_name} (current)",
                 f"+++ {t.device_name} (merge: '+' lines are added; nothing is removed)"]
        added = 0
        for raw in t.intended_config.splitlines():
            if not raw.strip():
                continue
            keys = t.driver.expected_lines(raw)
            if keys and keys[0] not in present:
                lines.append("+" + raw)
                added += 1
            else:
                lines.append(" " + raw)
        return ConfigDiff("\n".join(lines) if added else "", added, 0)

    @staticmethod
    def _missing(t: DeploymentTarget, running: str) -> list[str]:
        present = t.driver.present_lines(running)
        return [ln for ln in t.driver.expected_lines(t.intended_config) if ln not in present]

    def _needs_change(self, dep: Deployment, t: DeploymentTarget) -> bool:
        assert t.backup is not None
        if dep.apply_mode is ApplyMode.REPLACE:
            return diff_configs(t.backup.text, t.intended_config).changed
        return bool(self._missing(t, t.backup.text))

    def _apply_all(self, dep: Deployment) -> bool:
        for idx, t in enumerate(dep.targets):
            if not self._needs_change(dep, t):
                t.state = TargetState.NO_CHANGE
                self._emit(dep, "deploy", "ok", "already in desired state; not changed", t)
                continue
            t.touched = True
            result = t.driver.apply_configuration(t.intended_config, dep.apply_mode)
            if result.ok:
                result = t.driver.save_configuration()
            if not result.ok:
                self._fail_target(dep, t, "deploy", TargetState.APPLY_FAILED, result.message)
                for rest in dep.targets[idx + 1:]:
                    rest.state = TargetState.SKIPPED
                    self._emit(dep, "deploy", "skipped", "not attempted after failure", rest)
                return False
            t.state = TargetState.APPLIED
            self._emit(dep, "deploy", "ok", result.message or "applied", t)
        return True

    def _verify_all(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            if t.state is TargetState.NO_CHANGE:
                continue
            running = t.driver.get_running_configuration()
            if not running.ok:
                ok = self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                       f"could not read configuration back: {running.message}")
                continue
            if dep.apply_mode is ApplyMode.REPLACE:
                remaining = diff_configs(running.data, t.intended_config, t.device_name)
                absent = [ln[1:] for ln in remaining.unified.splitlines()
                          if ln.startswith("+") and not ln.startswith("+++")]
                problem = remaining.changed
            else:
                absent = self._missing(t, running.data)
                problem = bool(absent)
            if problem:
                detail = "; ".join(absent[:5]) or "running config differs from intent"
                ok = self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                       f"{len(absent)} intended line(s) missing after apply: "
                                       f"{detail}")
            else:
                t.state = TargetState.VERIFIED
                self._emit(dep, "verify", "ok", "running configuration matches intent", t)
        return ok

    def _recover(self, dep: Deployment) -> DeploymentState:
        self._move(dep, S.RECOVERING)
        all_ok = True
        for t in dep.targets:
            if not t.touched:
                continue
            assert t.backup is not None  # guaranteed by the backup stage
            result = t.driver.rollback_configuration(t.backup)
            if result.ok:
                t.driver.save_configuration()
                t.state = TargetState.ROLLED_BACK
                self._emit(dep, "recover", "ok", result.message or "rolled back", t)
            elif result.status is ResultStatus.UNSUPPORTED:
                all_ok = False
                t.state = TargetState.MANUAL_RECOVERY_REQUIRED
                t.message = (f"automatic rollback unsupported; restore backup "
                             f"{t.backup.reference} manually")
                self._emit(dep, "recover", "error", t.message, t)
            else:
                all_ok = False
                self._fail_target(dep, t, "recover", TargetState.ROLLBACK_FAILED,
                                  f"rollback failed: {result.message}")
        self._move(dep, S.ROLLED_BACK if all_ok else S.RECOVERY_REQUIRED)
        return dep.state
