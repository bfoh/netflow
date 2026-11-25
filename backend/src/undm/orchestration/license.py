"""Load a license file the team supplies on a device, through the lifecycle (D-100).

* preview (read-only): the device answers, and the command that will be sent; the unit
  restarts with the license;
* after approval: back up, offer the file to the device only (UNDM's TFTP server), send
  the command and answer only its expected question, wait until it answers again with the
  same serial number, read its facts.

The file's content is the team's (verified by them); UNDM checks only that it is not
empty, and keeps it out of events and logs. EXPERIMENTAL until run on hardware (Q-46).
"""

from __future__ import annotations

import base64
import contextlib
import os
import tempfile
from pathlib import Path

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


class LicenseOrchestrator(DeploymentOrchestrator):
    def _validate(self, dep: Deployment) -> bool:
        problems: list[tuple[str, DeploymentTarget | None]] = []
        if not dep.targets:
            problems.append(("plan has no device", None))
        for t in dep.targets:
            if Capability.LICENSE_FILE not in t.driver.capabilities():
                problems.append(("UNDM cannot load a license file on this device", t))
            if not t.intended_config:
                problems.append(("the license file is empty", t))
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
        self._emit(dep, stage, "ok", f"the device answers; the load sends "
                   f"'{t.driver.license_command}' and the unit restarts with the license "
                   f"('{t.checkpoint_label or 'license'}')", t)
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
            raise ApprovalRequiredError("A license load must be approved before it runs")
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
            self._move(dep, S.BACKING_UP)
            for t in dep.targets:
                backup = t.driver.backup_configuration()
                if backup.ok:
                    t.backup = backup.data
                    self._emit(dep, "backup", "ok", f"backup {backup.data.reference}", t)
                t.state = TargetState.BACKED_UP
            self._check_stop(dep)
            self._move(dep, S.DEPLOYING)
            for t in dep.targets:
                t.touched = True
                fd, tmp = tempfile.mkstemp(prefix="undm-license-")
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(base64.b64decode(t.intended_config))
                    r = t.driver.load_license(Path(tmp), t.checkpoint_label or "license.lic")
                finally:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
                if not r.ok:
                    self._fail_target(dep, t, "deploy", TargetState.MANUAL_RECOVERY_REQUIRED,
                                      r.message)
                    shown = str(r.diagnostics.get("device_output") or "").strip()
                    if shown:
                        self._emit(dep, "deploy", "warning",
                                   f"device output (last lines): {shown[-600:]}", t)
                    self._move(dep, S.RECOVERY_REQUIRED, "the license load did not complete "
                               "as expected; check the unit")
                    return dep.state
                self._emit(dep, "deploy", "ok", r.message or "license loaded", t)
                back = self._wait_until_available(dep, t)
                if not back.ok:
                    self._fail_target(dep, t, "deploy",
                                      TargetState.MANUAL_RECOVERY_REQUIRED, back.message)
                    self._move(dep, S.RECOVERY_REQUIRED, "the unit did not come back as "
                               "expected after the license; check it")
                    return dep.state
                t.state = TargetState.APPLIED
            self._move(dep, S.VERIFYING)
            for t in dep.targets:
                facts = t.driver.get_device_facts()
                seen = (f": {facts.data.hostname or '?'}, {facts.data.os_version or '?'}"
                        if facts.ok else "")
                t.state = TargetState.VERIFIED
                self._emit(dep, "verify", "ok", f"back after the license load{seen}. Check "
                           "its license status on the unit's web page (System → FortiGuard)", t)
            self._move(dep, S.SUCCEEDED)
            return dep.state
        except StopRequested:
            return self._stopped(dep)
        finally:
            for t in dep.targets:
                t.driver.disconnect()
                t.driver.should_stop = None
