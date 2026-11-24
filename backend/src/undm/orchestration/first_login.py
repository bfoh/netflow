"""First login on a new unit: set the device's own login where the unit demands a new
password (D-073).

A new FortiGate lets ``admin`` in with an empty password and then demands a new password
before its prompt. This plan does that change through the deployment lifecycle:

* preview (read-only): log in with the empty password and record what the unit shows,
  answering nothing (the login then times out and the session is closed);
* after approval: log in again with the empty password and answer only the questions the
  driver knows (D-066), with the device's stored login as the new password;
* verification: log in with the device's login and read its facts.

The unit must demand the change: if the empty password is refused, or reaches the prompt
without a demand, nothing is changed and the plan fails with the reason.
"""

from __future__ import annotations

from dataclasses import replace

from undm.domain.lifecycle import DeploymentState
from undm.drivers.base import Capability, Credentials
from undm.orchestration.deployment import (
    ApprovalRequiredError,
    Deployment,
    DeploymentOrchestrator,
    DeploymentTarget,
    StopRequested,
    TargetState,
)

S = DeploymentState


def _empty(login: Credentials) -> Credentials:
    return replace(login, password="")


class FirstLoginOrchestrator(DeploymentOrchestrator):
    def _validate(self, dep: Deployment) -> bool:
        problems: list[tuple[str, DeploymentTarget | None]] = []
        if not dep.targets:
            problems.append(("plan has no device", None))
        for t in dep.targets:
            if Capability.FIRST_LOGIN_SETUP not in t.driver.capabilities():
                problems.append(("this driver cannot answer a new unit's password change; "
                                 "do the first login by hand", t))
            if t.credentials_before is None or not t.credentials_before.password:
                problems.append(("the device needs its own login (user and the approved "
                                 "password) before the first login can set it", t))
        for message, target in problems:
            if target is not None:
                target.message = message
            self._emit(dep, "validate", "error", message, target)
        if not problems:
            self._emit(dep, "validate", "ok", f"{len(dep.targets)} target(s) valid")
        return not problems

    def _probe(self, dep: Deployment, t: DeploymentTarget, stage: str) -> bool:
        """Read-only: does the empty password lead to a demanded change? Nothing is sent."""
        assert t.credentials_before is not None
        failed = (TargetState.PREVIEW_FAILED if stage == "preview"
                  else TargetState.PREFLIGHT_FAILED)
        t.driver.use_credentials(_empty(t.credentials_before))
        try:
            r = t.driver.connect()
        finally:
            t.driver.disconnect()
        if r.ok:
            return self._fail_target(
                dep, t, stage, failed,
                "the empty password reaches the prompt without a demand for a new password: "
                "this is not the first login UNDM expects; nothing was changed")
        if r.diagnostics.get("login_refused"):
            return self._fail_target(
                dep, t, stage, failed,
                "the empty password is refused: the unit is not new, or its password was set "
                "already (Test connection shows whether the device's login works); nothing "
                "was changed")
        if not r.diagnostics.get("login_accepted"):
            return self._fail_target(dep, t, stage, failed, r.message)
        shown = str(r.diagnostics.get("device_output") or "").strip()
        self._emit(dep, stage, "ok", "the empty password is accepted and the unit asks for "
                   "something before its prompt" + (f": “{shown[-300:]}”" if shown else "")
                   + "; nothing was answered", t)
        return True

    def _preview(self, dep: Deployment) -> bool:
        ok = True
        for t in dep.targets:
            if self._probe(dep, t, "preview"):
                t.state = TargetState.PREVIEWED
            else:
                ok = False
        return ok

    def execute(self, dep: Deployment) -> DeploymentState:
        if dep.state is not S.READY:
            raise ApprovalRequiredError(f"Deployment must be ready to execute (is {dep.state})")
        if not dep.approved_by:
            raise ApprovalRequiredError("The first login must be approved before it runs")
        for t in dep.targets:
            t.driver.should_stop = dep.stop.is_set
        try:
            self._move(dep, S.PREFLIGHT)
            self._check_stop(dep)
            if not all([self._probe(dep, t, "preflight") for t in dep.targets]):
                self._move(dep, S.FAILED, "preflight failed; no device was changed")
                return dep.state
            for t in dep.targets:
                t.state = TargetState.PREFLIGHT_PASSED
            self._check_stop(dep)
            self._move(dep, S.BACKING_UP)
            for t in dep.targets:  # the lifecycle's backup step, recorded as not possible
                t.state = TargetState.BACKED_UP
                self._emit(dep, "backup", "ok", "nothing to back up: a new unit shows no "
                           "configuration before its first login (factory default)", t)
            self._check_stop(dep)
            self._move(dep, S.DEPLOYING)
            if not all([self._set_login(dep, t) for t in dep.targets]):
                self._move(dep, S.RECOVERY_REQUIRED,
                           "the password change did not complete; check the unit")
                return dep.state
            self._move(dep, S.VERIFYING)
            if not all([self._verify_login(dep, t) for t in dep.targets]):
                self._move(dep, S.RECOVERY_REQUIRED,
                           "the device's login does not work after the change; check the unit")
                return dep.state
            self._move(dep, S.SUCCEEDED)
            return dep.state
        except StopRequested:
            return self._stopped(dep)
        finally:
            for t in dep.targets:
                t.driver.offer_password_change(None)
                t.driver.disconnect()
                t.driver.should_stop = None

    def _set_login(self, dep: Deployment, t: DeploymentTarget) -> bool:
        assert t.credentials_before is not None
        t.touched = True
        t.driver.use_credentials(_empty(t.credentials_before))
        t.driver.offer_password_change(t.credentials_before)
        try:
            r = t.driver.connect()
        finally:
            t.driver.offer_password_change(None)
        changed = isinstance(r.data, dict) and r.data.get("password_changed") \
            or r.diagnostics.get("password_changed")
        if not changed:
            return self._fail_target(dep, t, "deploy", TargetState.APPLY_FAILED,
                                     f"the unit's password was not set: {r.message}")
        t.password_set = True
        t.state = TargetState.APPLIED
        self._emit(dep, "deploy", "ok", "the unit demanded a new password; UNDM answered its "
                   "questions with the device's login", t)
        return True

    def _verify_login(self, dep: Deployment, t: DeploymentTarget) -> bool:
        assert t.credentials_before is not None
        t.driver.disconnect()  # independent evidence: a fresh login with the device's login
        t.driver.use_credentials(t.credentials_before)
        r = t.driver.connect()
        if not r.ok:
            return self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                     f"logging in with the device's login failed: {r.message}")
        facts = t.driver.get_device_facts()
        seen = ""
        if facts.ok:
            f = facts.data
            t.observed_serial = f.serial_number
            seen = f": {f.hostname or '?'}, {f.model or '?'} {f.os_version or ''}".rstrip()
        t.state = TargetState.VERIFIED
        self._emit(dep, "verify", "ok", f"logged in with the device's login{seen}", t)
        return True
