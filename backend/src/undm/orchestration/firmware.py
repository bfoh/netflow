"""Firmware upgrade orchestration (same lifecycle and safety rules as configuration).

Per device: preflight (reachability, identity, current version) -> configuration
backup -> stage image -> install -> reboot -> wait until reachable -> verify the
running version equals the target. Devices are upgraded one at a time and the
run stops at the first failure (failure containment). Recovery uses firmware
rollback only where the driver declares it; otherwise the device is reported as
needing manual (possibly console/physical) recovery.

Firmware deployments always need: an approved image with verified integrity
(checked by the service), a maintenance window, and an approver who is not the
creator.
"""

from __future__ import annotations

from datetime import UTC, datetime

from undm.domain.lifecycle import DeploymentState
from undm.domain.operations import DeviceOperation
from undm.domain.versions import compare
from undm.drivers.base import DeviceDriver, OperationResult, ResultStatus
from undm.orchestration.deployment import (
    ApprovalRequiredError,
    Deployment,
    DeploymentOrchestrator,
    DeploymentTarget,
    EventSink,
    TargetState,
)

S = DeploymentState
MAX_WINDOW_HOURS = 24


class FirmwareOrchestrator(DeploymentOrchestrator):
    def __init__(self, sink: EventSink | None = None, *, reboot_wait_attempts: int = 30,
                 reboot_wait_delay_s: float = 20.0,
                 require_separate_approver: bool = True) -> None:
        # A second approver is the default; a bench policy may relax it explicitly.
        super().__init__(sink, require_separate_approver=require_separate_approver,
                         restart_wait_attempts=reboot_wait_attempts,
                         restart_wait_delay_s=reboot_wait_delay_s)

    # -- validate + preview -----------------------------------------------------------
    def _validate(self, dep: Deployment) -> bool:
        problems: list[tuple[str, DeploymentTarget | None]] = []
        if dep.firmware is None:
            problems.append(("no firmware image selected", None))
        if not dep.targets:
            problems.append(("deployment has no targets", None))
        seen: set[str] = set()
        for t in dep.targets:
            if t.device_id in seen:
                problems.append((f"device {t.device_name} listed twice", t))
            seen.add(t.device_id)
            missing = (t.driver.missing_capabilities(DeviceOperation.INSTALL_FIRMWARE)
                       | t.driver.missing_capabilities(DeviceOperation.REBOOT)
                       | t.driver.missing_capabilities(DeviceOperation.BACKUP_CONFIGURATION))
            if missing:
                problems.append((
                    "driver cannot perform firmware upgrades "
                    f"(lacks {', '.join(sorted(m.value for m in missing))})", t))
        for message, target in problems:
            if target is not None:
                target.message = message
            self._emit(dep, "validate", "error", message, target)
        if not problems:
            self._emit(dep, "validate", "ok", f"{len(dep.targets)} target(s) valid")
        return not problems

    def _version_problem(self, dep: Deployment, current: str) -> str | None:
        assert dep.firmware is not None
        target = dep.firmware.version
        order = compare(current, target)
        if order is None:
            return f"cannot compare running version {current!r} with {target!r}"
        if order > 0:
            return f"running version {current} is newer than {target}; downgrades are refused"
        if dep.min_from_version:
            base = compare(current, dep.min_from_version)
            if base is None:
                return f"cannot compare {current!r} with minimum {dep.min_from_version!r}"
            if base < 0:
                return (f"upgrade path: {current} is older than the minimum "
                        f"{dep.min_from_version} required for {target}")
        return None

    def _read_version(self, t: DeploymentTarget) -> OperationResult:
        info = t.driver.get_firmware_information()
        if info.ok:
            t.current_version = str(info.data["running"])
        return info

    def _preview(self, dep: Deployment) -> bool:
        assert dep.firmware is not None
        ok = True
        for t in dep.targets:
            t.target_version = dep.firmware.version
            try:
                conn = t.driver.connect()
                if not conn.ok:
                    ok = self._fail_target(dep, t, "preview", TargetState.PREVIEW_FAILED,
                                           conn.message)
                    continue
                info = self._read_version(t)
                if not info.ok:
                    ok = self._fail_target(dep, t, "preview", TargetState.PREVIEW_FAILED,
                                           f"cannot read firmware version: {info.message}")
                    continue
                assert t.current_version is not None
                problem = self._version_problem(dep, t.current_version)
                if problem:
                    ok = self._fail_target(dep, t, "preview", TargetState.PREVIEW_FAILED, problem)
                    continue
                t.state = TargetState.PREVIEWED
                same = compare(t.current_version, dep.firmware.version) == 0
                self._emit(dep, "preview", "ok",
                           f"{t.current_version} -> {dep.firmware.version}"
                           + (" (already running target; will be skipped)" if same else ""), t)
            finally:
                t.driver.disconnect()
        return ok

    # -- approval ---------------------------------------------------------------------
    def approve(self, dep: Deployment, approver: str) -> None:
        if not dep.dry_run:
            if dep.window_start is None or dep.window_end is None:
                raise ApprovalRequiredError("Firmware approval needs a maintenance window")
            if dep.window_end <= dep.window_start:
                raise ApprovalRequiredError("Maintenance window must end after it starts")
            if (dep.window_end - dep.window_start).total_seconds() > MAX_WINDOW_HOURS * 3600:
                raise ApprovalRequiredError(
                    f"Maintenance window longer than {MAX_WINDOW_HOURS} hours")
        super().approve(dep, approver)
        self._emit(dep, "approve", "ok",
                   f"maintenance window {dep.window_start:%Y-%m-%d %H:%M} - "
                   f"{dep.window_end:%Y-%m-%d %H:%M} UTC")

    # -- execution --------------------------------------------------------------------
    def execute(self, dep: Deployment) -> DeploymentState:
        if not dep.dry_run:
            now = datetime.now(UTC)
            assert dep.window_start is not None and dep.window_end is not None
            if not dep.window_start <= now <= dep.window_end:
                raise ApprovalRequiredError(
                    f"Outside the approved maintenance window ({dep.window_start:%Y-%m-%d %H:%M}"
                    f" - {dep.window_end:%Y-%m-%d %H:%M} UTC)")
        return super().execute(dep)

    def _preflight(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            conn = t.driver.connect()
            if not conn.ok:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       conn.message)
                continue
            facts = t.driver.get_device_facts()
            if t.expected_serial and facts.ok and facts.data.serial_number != t.expected_serial:
                ok = self._fail_target(
                    dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                    f"identity mismatch: inventory serial {t.expected_serial}, device reports "
                    f"{facts.data.serial_number}")
                continue
            if facts.ok:
                t.observed_serial = facts.data.serial_number
            info = self._read_version(t)
            if not info.ok:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       f"cannot read firmware version: {info.message}")
                continue
            assert t.current_version is not None
            problem = self._version_problem(dep, t.current_version)
            if problem:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED, problem)
                continue
            t.from_version = t.current_version
            t.state = TargetState.PREFLIGHT_PASSED
            self._emit(dep, "preflight", "ok",
                       f"reachable, identity ok, running {t.current_version}", t)
        return ok

    def _needs_upgrade(self, dep: Deployment, t: DeploymentTarget) -> bool:
        assert dep.firmware is not None and t.current_version is not None
        return compare(t.current_version, dep.firmware.version) != 0

    @staticmethod
    def _step(dep: Deployment, t: DeploymentTarget, name: str) -> OperationResult:
        assert dep.firmware is not None
        if name == "stage":
            return t.driver.stage_firmware(dep.firmware)
        if name == "install":
            return t.driver.install_firmware()
        return t.driver.reboot()

    def _apply_all(self, dep: Deployment) -> bool:
        assert dep.firmware is not None
        for idx, t in enumerate(dep.targets):
            if not self._needs_upgrade(dep, t):
                t.state = TargetState.NO_CHANGE
                self._emit(dep, "deploy", "ok", f"already running {dep.firmware.version}", t)
                continue
            t.touched = True
            failed: tuple[str, OperationResult] | None = None
            for name in ("stage", "install", "reboot"):
                result = self._step(dep, t, name)
                if not result.ok:
                    failed = (name, result)
                    break
                self._emit(dep, "deploy", "ok", f"{name}: {result.message or 'done'}", t)
            if failed is None:
                back = self._wait_until_available(dep, t)
                if not back.ok:
                    failed = ("wait", back)
            if failed is not None:
                name, result = failed
                self._fail_target(dep, t, "deploy", TargetState.APPLY_FAILED,
                                  f"{name} failed: {result.message}")
                # What the device last printed (redacted by the driver) is the evidence a
                # technician needs, e.g. a question that was deliberately left unanswered.
                shown = str(result.diagnostics.get("device_output") or "").strip()
                if shown:
                    self._emit(dep, "deploy", "warning",
                               f"device output (last lines): {shown[-600:]}", t)
                for rest in dep.targets[idx + 1:]:
                    rest.state = TargetState.SKIPPED
                    self._emit(dep, "deploy", "skipped", "not attempted after failure", rest)
                return False
            t.state = TargetState.APPLIED
        return True

    def _verify_all(self, dep: Deployment) -> bool:
        assert dep.firmware is not None
        ok = True
        for t in dep.targets:
            if t.state is TargetState.NO_CHANGE:
                continue
            info = self._read_version(t)
            if not info.ok:
                ok = self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                       f"cannot read firmware version: {info.message}")
                continue
            if compare(str(t.current_version), dep.firmware.version) != 0:
                ok = self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                       f"device runs {t.current_version}, expected "
                                       f"{dep.firmware.version}")
                continue
            if t.backup is not None:
                running = t.driver.get_running_configuration()
                if running.ok:
                    missing = self._missing_from(t.driver, t.backup.text, str(running.data))
                    if missing:
                        self._emit(dep, "verify", "warning",
                                   f"{len(missing)} configuration line(s) differ from the "
                                   f"pre-upgrade backup; review: {'; '.join(missing[:3])}", t)
            t.state = TargetState.VERIFIED
            self._emit(dep, "verify", "ok", f"running {t.current_version}", t)
        return ok

    @staticmethod
    def _missing_from(driver: DeviceDriver, before: str, after: str) -> list[str]:
        present = driver.present_lines(after)
        return [ln for ln in driver.expected_lines(before) if ln not in present]

    def _recover(self, dep: Deployment) -> DeploymentState:
        self._move(dep, S.RECOVERING)
        all_ok = True
        for t in dep.targets:
            if not t.touched:
                continue
            t.driver.disconnect()
            conn = t.driver.connect()
            if conn.ok and self._read_version(t).ok and t.current_version == t.from_version:
                t.state = TargetState.ROLLED_BACK
                t.message = (f"still running the original version {t.from_version}; nothing to "
                             "undo. If the new image was already copied to the device it is "
                             "still stored there and may start at the next restart")
                self._emit(dep, "recover", "ok", t.message, t)
                continue
            if t.driver.missing_capabilities(DeviceOperation.ROLLBACK_FIRMWARE):
                all_ok = False
                t.state = TargetState.MANUAL_RECOVERY_REQUIRED
                t.message = ("automatic firmware rollback is not supported; restore the previous "
                             f"image ({t.from_version or 'unknown'}) manually, using console "
                             "access if the device is unreachable")
                self._emit(dep, "recover", "error", t.message, t)
                continue
            result = t.driver.rollback_firmware() if conn.ok else conn
            if result.ok:
                result = t.driver.reboot()
            if result.ok:
                result = self._wait_until_available(dep, t)
            if result.ok:
                t.state = TargetState.ROLLED_BACK
                self._read_version(t)
                self._emit(dep, "recover", "ok", f"rolled back to {t.current_version}", t)
            else:
                all_ok = False
                unreachable = "reach" in result.message.lower()
                t.state = TargetState.ROLLBACK_FAILED
                t.message = (f"rollback failed: {result.message}"
                             + ("; console or physical recovery may be required"
                                if unreachable else ""))
                self._emit(dep, "recover", "error", t.message, t)
        self._move(dep, S.ROLLED_BACK if all_ok else S.RECOVERY_REQUIRED)
        return dep.state


__all__ = ["FirmwareOrchestrator", "ResultStatus"]
