"""Free an address: take a device off its management address until its next restart
(D-107; D-096's spare address could not work, D-106).

Two devices of a system can end at the same management address (both 2930F of the staging
use case). Before the second one loads its file, the first switches off its management port
in its running configuration only; nothing is saved, so it answers again at its next
power-on. Through the deployment lifecycle:

* preview (read-only): the exact commands, or "no device answers there: nothing to move";
* after approval: back up, send the commands, and check that its address has gone quiet.

EXPERIMENTAL: a driver's procedure is unverified until run on a named lab model.
"""

from __future__ import annotations

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


class FreeAddressOrchestrator(DeploymentOrchestrator):
    def _validate(self, dep: Deployment) -> bool:
        problems: list[tuple[str, DeploymentTarget | None]] = []
        if not dep.targets:
            problems.append(("plan has no device", None))
        for t in dep.targets:
            if Capability.MANAGEMENT_PORT_OFF not in t.driver.capabilities():
                problems.append(("this driver cannot take a device off its address; "
                                 "disconnect the device from the bench network instead", t))
        for message, target in problems:
            if target is not None:
                target.message = message
            self._emit(dep, "validate", "error", message, target)
        if not problems:
            self._emit(dep, "validate", "ok", f"{len(dep.targets)} target(s) valid")
        return not problems

    def _look(self, dep: Deployment, t: DeploymentTarget, stage: str) -> bool | None:
        """Read-only. True: the device answers and can be moved; None: nothing answers at
        its address (nothing to move); False: failed (recorded)."""
        failed = (TargetState.PREVIEW_FAILED if stage == "preview"
                  else TargetState.PREFLIGHT_FAILED)
        r = t.driver.connect()
        if not r.ok:
            if r.diagnostics.get("no_answer"):
                self._emit(dep, stage, "ok", "no device answers at its address: it is off or "
                           "disconnected, so its address is free already; nothing to move", t)
                return None
            self._fail_target(dep, t, stage, failed, r.message)
            return False
        plan = t.driver.free_address_commands()
        if not plan.ok:
            self._fail_target(dep, t, stage, failed, plan.message)
            return False
        commands = "; ".join(plan.data.get("commands", []))
        self._emit(dep, stage, "ok", f"{plan.message}. Commands: {commands}", t)
        return True

    def _preview(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            try:
                found = self._look(dep, t, "preview")
            finally:
                t.driver.disconnect()
            if found is False:
                ok = False
            else:
                t.state = TargetState.PREVIEWED
        return ok

    def execute(self, dep: Deployment) -> DeploymentState:
        if dep.state is not S.READY:
            raise ApprovalRequiredError(f"Deployment must be ready to execute (is {dep.state})")
        if not dep.approved_by:
            raise ApprovalRequiredError("Moving a device aside must be approved before it runs")
        for t in dep.targets:
            t.driver.should_stop = dep.stop.is_set
        try:
            self._move(dep, S.PREFLIGHT)
            self._check_stop(dep)
            present: list[DeploymentTarget] = []
            for t in dep.targets:
                found = self._look(dep, t, "preflight")
                if found is False:
                    self._move(dep, S.FAILED, "preflight failed; no device was changed")
                    return dep.state
                if found:
                    t.state = TargetState.PREFLIGHT_PASSED
                    present.append(t)
                else:
                    t.state = TargetState.NO_CHANGE
            self._check_stop(dep)
            self._move(dep, S.BACKING_UP)
            for t in present:
                backup = t.driver.backup_configuration()
                if not backup.ok:
                    self._fail_target(dep, t, "backup", TargetState.BACKUP_FAILED,
                                      f"backup failed: {backup.message}")
                    self._move(dep, S.FAILED, "backup failed; no device was changed")
                    return dep.state
                t.backup = backup.data
                t.state = TargetState.BACKED_UP
                self._emit(dep, "backup", "ok", f"backup {backup.data.reference}", t)
            self._check_stop(dep)
            self._move(dep, S.DEPLOYING)
            for t in present:
                t.touched = True
                r = t.driver.free_address()
                if not r.ok and r.diagnostics.get("unchanged"):
                    # Refused before anything changed: the device is as it was.
                    self._fail_target(dep, t, "deploy", TargetState.APPLY_FAILED, r.message)
                    self._move(dep, S.FAILED, "the device was left as it was; nothing "
                               "was changed on it")
                    return dep.state
                if not r.ok:
                    self._fail_target(dep, t, "deploy", TargetState.MANUAL_RECOVERY_REQUIRED,
                                      r.message)
                    self._move(dep, S.RECOVERY_REQUIRED,
                               "the step did not complete; nothing was saved on the device: "
                               "switching it off and on returns it to its saved configuration")
                    return dep.state
                self._emit_notes(dep, t, "deploy", r)
                if r.data and r.data.get("port"):
                    t.target_version = f"port {r.data['port']} off"
                t.state = TargetState.APPLIED
                self._emit(dep, "deploy", "ok", r.message, t)
            self._move(dep, S.VERIFYING)
            for t in present:
                # The driver's own evidence: the address stopped answering after the
                # command (independent of the device's own words, D-031).
                t.state = TargetState.VERIFIED
                self._emit(dep, "verify", "ok", "its address no longer answers; it is free "
                           "until this device's next power-on", t)
            self._move(dep, S.SUCCEEDED)
            return dep.state
        except StopRequested:
            return self._stopped(dep)
        finally:
            for t in dep.targets:
                t.driver.disconnect()
                t.driver.should_stop = None
