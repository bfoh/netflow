"""Restart a device on request, through the deployment lifecycle (D-099).

* preview (read-only): the device answers, the command that will be sent, and that
  unsaved changes are not saved;
* after approval: back up its running configuration, send the restart, wait until it
  answers at its own address with the same serial number, read its facts.

A device moved to a temporary address (D-096) answers at its own address again after a
restart: UNDM waits for it there.
"""

from __future__ import annotations

from dataclasses import replace

from undm.domain.lifecycle import DeploymentState
from undm.drivers.base import Capability
from undm.orchestration.deployment import (
    ApprovalRequiredError,
    Deployment,
    DeploymentOrchestrator,
    DeploymentTarget,
    StopRequested,
    TargetState,
)

S = DeploymentState


class RestartOrchestrator(DeploymentOrchestrator):
    def _validate(self, dep: Deployment) -> bool:
        problems: list[tuple[str, DeploymentTarget | None]] = []
        if not dep.targets:
            problems.append(("plan has no device", None))
        for t in dep.targets:
            if Capability.RESTART not in t.driver.capabilities():
                problems.append(("UNDM cannot restart this device on request (no verified "
                                 "restart procedure for its model yet)", t))
        for message, target in problems:
            if target is not None:
                target.message = message
            self._emit(dep, "validate", "error", message, target)
        if not problems:
            self._emit(dep, "validate", "ok", f"{len(dep.targets)} target(s) valid")
        return not problems

    def _look(self, dep: Deployment, t: DeploymentTarget, stage: str) -> bool:
        failed = (TargetState.PREVIEW_FAILED if stage == "preview"
                  else TargetState.PREFLIGHT_FAILED)
        r = t.driver.connect()
        if not r.ok:
            return self._fail_target(dep, t, stage, failed, r.message)
        facts = t.driver.get_device_facts()
        if facts.ok:
            t.observed_serial = facts.data.serial_number
        if t.expected_serial and facts.ok and facts.data.serial_number != t.expected_serial:
            return self._fail_target(
                dep, t, stage, failed, f"identity mismatch: inventory serial "
                f"{t.expected_serial}, device reports {facts.data.serial_number}")
        self._emit(dep, stage, "ok", f"the device answers; the restart sends "
                   f"'{t.driver.restart_command}'. Changes that were not saved on it are lost; "
                   "it starts with its saved configuration", t)
        return True

    def _preview(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            try:
                if self._look(dep, t, "preview"):
                    t.state = TargetState.PREVIEWED
                else:
                    ok = False
            finally:
                t.driver.disconnect()
        return ok

    def execute(self, dep: Deployment) -> DeploymentState:
        if dep.state is not S.READY:
            raise ApprovalRequiredError(f"Deployment must be ready to execute (is {dep.state})")
        if not dep.approved_by:
            raise ApprovalRequiredError("A restart must be approved before it runs")
        for t in dep.targets:
            t.driver.should_stop = dep.stop.is_set
        try:
            self._move(dep, S.PREFLIGHT)
            self._check_stop(dep)
            for t in dep.targets:
                if not self._look(dep, t, "preflight"):
                    self._move(dep, S.FAILED, "preflight failed; no device was changed")
                    return dep.state
                t.state = TargetState.PREFLIGHT_PASSED
            self._check_stop(dep)
            self._move(dep, S.BACKING_UP)
            for t in dep.targets:
                backup = t.driver.backup_configuration()
                if backup.ok:
                    t.backup = backup.data
                    self._emit(dep, "backup", "ok", f"backup {backup.data.reference}", t)
                else:
                    self._emit(dep, "backup", "warning", f"no backup ({backup.message}); a "
                               "restart changes no saved setting", t)
                t.state = TargetState.BACKED_UP
            self._check_stop(dep)
            self._move(dep, S.DEPLOYING)
            for t in dep.targets:
                t.touched = True
                r = t.driver.restart()
                if not r.ok:
                    if r.diagnostics.get("unchanged"):
                        self._fail_target(dep, t, "deploy", TargetState.APPLY_FAILED,
                                          r.message)
                        self._move(dep, S.FAILED, "the device did not restart; nothing "
                                   "was changed")
                    else:
                        self._fail_target(dep, t, "deploy",
                                          TargetState.MANUAL_RECOVERY_REQUIRED, r.message)
                        self._move(dep, S.RECOVERY_REQUIRED, "the restart did not complete "
                                   "as expected; check the device")
                    return dep.state
                self._emit(dep, "deploy", "ok", r.message or "restarting", t)
                own = t.target_version or t.driver.target.management_address
                if own != t.driver.target.management_address:
                    # It ran at a temporary address (D-096): after a restart it uses its own.
                    t.driver.target = replace(t.driver.target, management_address=own)
                back = self._wait_until_available(dep, t)
                if not back.ok:
                    self._fail_target(dep, t, "deploy",
                                      TargetState.MANUAL_RECOVERY_REQUIRED, back.message)
                    self._move(dep, S.RECOVERY_REQUIRED, "the device did not come back "
                               "as expected; check it")
                    return dep.state
                t.state = TargetState.APPLIED
            self._move(dep, S.VERIFYING)
            for t in dep.targets:
                facts = t.driver.get_device_facts()
                seen = (f": {facts.data.hostname or '?'}, {facts.data.os_version or '?'}"
                        if facts.ok else "")
                self._note_hostname(t)
                t.state = TargetState.VERIFIED
                self._emit(dep, "verify", "ok", f"back after the restart{seen}", t)
            self._move(dep, S.SUCCEEDED)
            return dep.state
        except StopRequested:
            return self._stopped(dep)
        finally:
            for t in dep.targets:
                t.driver.disconnect()
                t.driver.should_stop = None
