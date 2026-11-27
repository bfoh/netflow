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

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from undm.configgen.diff import ConfigDiff, diff_configs, normalize
from undm.domain.lifecycle import DeploymentState, transition
from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigurationBackup,
    Credentials,
    DeviceDriver,
    FirmwareImageRef,
    OperationResult,
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
class StopSignal:
    """A request to stop a running deployment, set from another thread (the Stop button).

    The run stops at the next safe point: between steps, while waiting for a device to
    come back, or while waiting for a device's answer. A command a device is already
    executing is not interrupted on the device itself.
    """

    event: threading.Event = field(default_factory=threading.Event)
    by: str = ""

    def request(self, by: str) -> None:
        self.by = by
        self.event.set()

    def is_set(self) -> bool:
        return self.event.is_set()

    def wait(self, seconds: float) -> bool:
        return self.event.wait(seconds)


class StopRequested(Exception):  # noqa: N818 - a signal, not an error
    pass


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
    current_secondary: str | None = None  # secondary image slot, where the device has one
    # Running configuration read back once the target was verified (kept for review).
    after_config: str | None = None
    secondary_failed: bool = False  # writing the secondary image failed or did not verify
    # Values for secret slots of a supplied file (slot id -> value). Inserted only into the
    # copy sent to the device; never stored, logged or shown.
    secret_values: dict[str, str] = field(default_factory=dict, repr=False)
    # Name of a restore point to keep on the device after verification (if supported).
    checkpoint_label: str | None = None
    # Serial number the device reported at preflight; re-checked after any restart so a
    # different unit answering at the same address is never taken for this one.
    observed_serial: str | None = None
    # Login valid once the configuration is applied (the file changes the password).
    credentials_after: Credentials | None = field(default=None, repr=False)
    # The device's login before the load is one it kept from before staging, not the approved
    # one (a switch that kept its password, D-131): keeping it after the load is a warning.
    previous_login_interim: bool = False
    # The device's own login before loading. Used after a restart when the unit, on the
    # login chosen for after loading, demands a new password and a person sets this one
    # on it by hand (D-065); the device then keeps this login.
    credentials_before: Credentials | None = field(default=None, repr=False)
    # Hostname the device reported once its configuration was verified (observed, not
    # declared); the service may name the device after it (D-094).
    observed_hostname: str | None = None
    kept_previous_login: bool = False
    password_set: bool = False  # UNDM answered a demanded password change (D-066)
    # Project settings a driver may need before applying (e.g. certificate_subject).
    settings: dict[str, Any] = field(default_factory=dict)


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
    # Install the approved image even where the device runs a newer version (project rule).
    allow_downgrade: bool = False
    # Also write the approved image into the secondary image slot, after the primary is
    # verified (project standard: the approved release in both slots).
    also_secondary: bool = False
    window_start: datetime | None = None
    window_end: datetime | None = None
    stop: StopSignal = field(default_factory=StopSignal, repr=False)
    # A later step of a staging plan: the device does not yet have the configuration this
    # step builds on, so the preview is made at the run's preflight instead (D-071).
    defer_preview: str | None = None


class ApprovalRequiredError(PermissionError):
    pass


EventSink = Callable[[Deployment, DeploymentEvent], None]


class DeploymentOrchestrator:
    def __init__(
        self, sink: EventSink | None = None, *, require_separate_approver: bool = False,
        restart_wait_attempts: int = 30, restart_wait_delay_s: float = 20.0,
    ) -> None:
        self._sink = sink
        self.require_separate_approver = require_separate_approver
        # A device that restarts by itself (e.g. after a full restore) is polled this often.
        self.restart_wait_attempts = restart_wait_attempts
        self.restart_wait_delay_s = restart_wait_delay_s

    def _check_stop(self, dep: Deployment) -> None:
        if dep.stop.is_set():
            raise StopRequested

    def _wait_until_available(self, dep: Deployment, t: DeploymentTarget) -> OperationResult:
        if not t.driver.info.simulated:
            self._emit(dep, "deploy", "ok",
                       f"waiting for the device to answer at {t.driver.target.management_address}"
                       f" (up to {self.restart_wait_attempts} attempts, "
                       f"{self.restart_wait_delay_s:.0f} s apart; Stop ends the wait)", t)
        fallback = t.credentials_before if t.credentials_after is not None else None
        # A unit that demands a new password on the login chosen for after loading gets the
        # device's previous (approved) one, where the driver knows the questions (D-066).
        t.driver.offer_password_change(fallback)
        try:
            return self._wait_for_login(dep, t, fallback)
        finally:
            t.driver.offer_password_change(None)

    def _wait_for_login(self, dep: Deployment, t: DeploymentTarget,
                        fallback: Credentials | None) -> OperationResult:
        last = OperationResult.failed(DeviceOperation.CHECK_REACHABILITY, "not attempted")
        hinted, attempt, limit = False, 0, self.restart_wait_attempts
        while attempt < limit:
            attempt += 1
            if not t.driver.info.simulated and dep.stop.wait(self.restart_wait_delay_s):
                raise StopRequested
            self._check_stop(dep)
            t.driver.disconnect()
            last = t.driver.connect()
            if (not last.ok and last.diagnostics.get("login_refused") and fallback is not None
                    and not t.kept_previous_login):
                # The login chosen for after loading no longer works: typically a person
                # has just set the device's previous (approved) password on the unit.
                t.driver.use_credentials(fallback)
                t.kept_previous_login = True
                self._emit(dep, "deploy", "ok", "the login chosen for after loading is "
                           "refused now; trying the device's previous login", t)
                t.driver.disconnect()
                last = t.driver.connect()
            if not last.ok and last.diagnostics.get("password_changed"):
                t.kept_previous_login = t.password_set = True  # the device has it now
            login_problem = not last.ok and (last.diagnostics.get("login_accepted")
                                             or last.diagnostics.get("login_refused"))
            if login_problem and not hinted:
                hinted = True
                limit = attempt + self.restart_wait_attempts  # a person needs time
                self._emit(dep, "deploy", "warning", self._login_hint(t, last, fallback), t)
            elif login_problem:  # show that the wait goes on (bench: it looked stuck)
                why = ("the login is refused" if last.diagnostics.get("login_refused")
                       else "the device shows no command prompt after the login")
                self._emit(dep, "deploy", "ok", f"still waiting for a working login "
                           f"(attempt {attempt} of {limit}): {why}", t)
            if last.ok and isinstance(last.data, dict) and last.data.get("password_changed"):
                t.kept_previous_login = t.password_set = True
                t.driver.offer_password_change(None)
                self._emit(dep, "deploy", "ok", "the device demanded a new password at login "
                           "with the login chosen for after loading; UNDM answered its "
                           "questions and set the password of the device's previous "
                           "(approved) login", t)
                t.driver.disconnect()  # independent evidence: log in again with it
                last = t.driver.connect()
                if not last.ok:
                    return OperationResult.failed(
                        DeviceOperation.CHECK_REACHABILITY,
                        f"the new password was set, but logging in again with it failed: "
                        f"{last.message}")
                self._emit(dep, "deploy", "ok", "logged in again with the device's login", t)
            elif last.ok and t.kept_previous_login and t.previous_login_interim:
                # Bench 2026-11-27: a 2930F's team file did not set the approved password,
                # so the switch stayed on the login it kept from before staging (D-131).
                self._emit(dep, "deploy", "warning", "the login chosen for after loading is "
                           "refused: the file did not give the device that password. It still "
                           "answers to the login it had before staging, not the approved one: "
                           "give it the approved password on its console before it leaves the "
                           "bench", t)
            elif last.ok and t.kept_previous_login:
                self._emit(dep, "deploy", "ok", "logged in with the device's previous "
                           "login (set on the unit by hand); the device keeps it", t)
            if last.ok:
                facts = t.driver.get_device_facts() if t.observed_serial else None
                seen = facts.data.serial_number if facts is not None and facts.ok else None
                if seen and seen != t.observed_serial:
                    return OperationResult.failed(
                        DeviceOperation.CHECK_REACHABILITY,
                        f"a different device answers at {t.driver.target.management_address} "
                        f"after the restart (serial {seen}, expected {t.observed_serial}). "
                        "Make sure only this unit uses that address, then check it on the "
                        "console.")
                self._emit(dep, "deploy", "ok", f"device reachable again (attempt {attempt}"
                           + (", same serial number" if seen else "") + ")", t)
                return last
        if last.diagnostics.get("login_accepted") or last.diagnostics.get("login_refused"):
            return OperationResult.failed(
                DeviceOperation.CHECK_REACHABILITY,
                f"the device answers after its restart, but no login reached its prompt "
                f"({attempt} attempts): {last.message}")
        return OperationResult.failed(
            DeviceOperation.CHECK_REACHABILITY,
            f"device not reachable after its restart ({attempt} attempts): {last.message}")

    def _login_hint(self, t: DeploymentTarget, last: OperationResult,
                    fallback: Credentials | None) -> str:
        minutes = self.restart_wait_attempts * self.restart_wait_delay_s / 60
        keep = f"UNDM keeps trying for up to {minutes:.0f} more minutes"
        if last.diagnostics.get("login_accepted"):
            then = (" with the login chosen for after loading, and switches to the device's "
                    "previous login as soon as that one is refused (that is, once the "
                    "password was changed)" if fallback is not None else "")
            return (f"{last.message} If it asks for a new password, set the device's approved "
                    f"password on the unit by hand now. {keep}{then}.")
        return (f"The device answers after its restart but refuses the login ({last.message}). "
                "If the loaded file sets another password, either set the device's login on "
                f"the unit by hand now ({keep}), or choose that password as 'login after "
                "loading' in the plan next time.")

    def _emit_notes(self, dep: Deployment, t: DeploymentTarget, stage: str,
                    result: OperationResult) -> None:
        """Evidence a driver wants on record (e.g. what the device printed), as events."""
        notes = result.data.get("notes") if isinstance(result.data, dict) else None
        for note in list(notes or [])[:5]:
            self._emit(dep, stage, "ok", str(note), t)

    def _emit_warnings(self, dep: Deployment, t: DeploymentTarget, stage: str,
                       result: OperationResult) -> None:
        warnings = result.data.get("warnings") if isinstance(result.data, dict) else None
        for w in list(warnings or [])[:25]:
            self._emit(dep, stage, "warning", str(w), t)
        if warnings and len(warnings) > 25:
            self._emit(dep, stage, "warning", f"... and {len(warnings) - 25} more", t)

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
        if dep.defer_preview:
            for t in dep.targets:
                t.state = TargetState.PREVIEWED
                self._emit(dep, "preview", "ok", f"preview deferred: {dep.defer_preview}", t)
            return True
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
                if dep.apply_mode is ApplyMode.MERGE:
                    present = t.driver.present_lines(running.data)
                    keys = [k[0] for raw in t.intended_config.splitlines() if raw.strip()
                            if (k := t.driver.expected_lines(raw))]
                    note = t.driver.merge_rerun_note(sum(1 for k in keys if k in present),
                                                     len(keys))
                    if note:
                        self._emit(dep, "preview", "warning", note, t)
            finally:
                t.driver.disconnect()
        return ok

    # -- approval -------------------------------------------------------------------
    def approve(self, dep: Deployment, approver: str) -> None:
        if dep.dry_run:
            raise ValueError("Dry runs do not need approval")
        if self.require_separate_approver and approver == dep.created_by:
            raise ApprovalRequiredError(
                f"A second person must approve this plan: it was made by {dep.created_by}. "
                "Ask a colleague to approve it under their own name (Settings → Your name). "
                "For firmware plans on a bench where you work alone, turn off 'A second "
                "person approves firmware plans' in Settings → Safety.")
        dep.approved_by = approver
        dep.approved_at = datetime.now(UTC)
        self._move(dep, S.READY, f"approved by {approver}")

    # -- execution ------------------------------------------------------------------
    def execute(self, dep: Deployment) -> DeploymentState:
        if dep.state is not S.READY:
            raise ApprovalRequiredError(f"Deployment must be ready to execute (is {dep.state})")
        if not dep.dry_run and not dep.approved_by:
            raise ApprovalRequiredError("Live deployments must be approved before execution")
        for t in dep.targets:  # long waits inside a driver end early on a stop request
            t.driver.should_stop = dep.stop.is_set
        try:
            self._move(dep, S.PREFLIGHT)
            self._check_stop(dep)  # stopped before the run had begun
            if not self._preflight(dep):
                self._check_stop(dep)
                self._move(dep, S.FAILED, "preflight failed; no device was changed")
                return dep.state
            self._check_stop(dep)
            if dep.dry_run:
                self._move(dep, S.SUCCEEDED, "dry run complete; no device was changed")
                return dep.state
            self._move(dep, S.BACKING_UP)
            if not self._backup_all(dep):
                self._check_stop(dep)
                self._move(dep, S.FAILED, "backup failed; no device was changed")
                return dep.state
            self._check_stop(dep)
            self._move(dep, S.DEPLOYING)
            if not self._apply_all(dep):
                self._check_stop(dep)
                return self._recover(dep)
            self._check_stop(dep)
            self._move(dep, S.VERIFYING)
            if not self._verify_all(dep):
                self._check_stop(dep)
                return self._recover(dep)
            self._move(dep, S.SUCCEEDED)
            return dep.state
        except StopRequested:
            return self._stopped(dep)
        finally:
            for t in dep.targets:
                t.driver.disconnect()
                t.driver.should_stop = None

    _FINISHED = frozenset({TargetState.VERIFIED, TargetState.NO_CHANGE,
                           TargetState.ROLLED_BACK, TargetState.MANUAL_RECOVERY_REQUIRED})

    def _stopped(self, dep: Deployment) -> DeploymentState:
        """End a run stopped on request. No further device action is taken."""
        by = dep.stop.by or "a user"
        changed = [t for t in dep.targets if t.touched and t.state not in self._FINISHED]
        for t in dep.targets:
            if t in changed:
                t.state = TargetState.MANUAL_RECOVERY_REQUIRED
                t.message = (f"stopped by {by} while {dep.state.value}; the device may be "
                             "part-way through a change (or still restarting): check it "
                             "before making further changes")
                self._emit(dep, "stop", "error", t.message, t)
            elif t.state not in self._FINISHED and not t.state.value.endswith("failed"):
                t.state = TargetState.SKIPPED
                self._emit(dep, "stop", "skipped", "not attempted: the run was stopped", t)
        if changed or (dep.state in (S.VERIFYING, S.RECOVERING)):
            self._move(dep, S.RECOVERY_REQUIRED,
                       f"stopped by {by}; {len(changed)} device(s) may be mid-change and must "
                       "be checked")
        else:
            self._move(dep, S.FAILED, f"stopped by {by}; no device was changed")
        return dep.state

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
            if facts.ok:
                t.observed_serial = facts.data.serial_number
            running = t.driver.get_running_configuration()
            if not running.ok:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       running.message)
                continue
            t.diff = self._preview_diff(dep, t, running.data)
            check = t.driver.check_before_apply(t.intended_config, dep.apply_mode)
            if check is not None and not check.ok:
                ok = self._fail_target(dep, t, "preflight", TargetState.PREFLIGHT_FAILED,
                                       check.message)
                continue
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
            self._check_stop(dep)
            if not self._needs_change(dep, t):
                t.state = TargetState.NO_CHANGE
                self._emit(dep, "deploy", "ok", "already in desired state; not changed", t)
                continue
            try:
                to_send = t.driver.prepare_for_device(t.intended_config, t.secret_values)
            except ValueError as e:
                result = OperationResult.failed(DeviceOperation.APPLY_CONFIGURATION, str(e))
            else:
                t.touched = True
                prep = t.driver.prepare_before_apply(to_send, dep.apply_mode, t.settings)
                if prep is not None and prep.ok:
                    self._emit(dep, "deploy", "ok", prep.message or "prepared", t)
                    self._emit_warnings(dep, t, "deploy", prep)
                notice = (t.driver.restart_notice(dep.apply_mode)
                          if prep is None or prep.ok else None)
                if notice:
                    self._emit(dep, "deploy", "ok", notice, t)
                result = (prep if prep is not None and not prep.ok
                          else t.driver.apply_configuration(to_send, dep.apply_mode))
                if result.ok:
                    self._emit_notes(dep, t, "deploy", result)
                    self._emit_warnings(dep, t, "deploy", result)
                    restarting = isinstance(result.data, dict) and result.data.get("restarting")
                    if t.credentials_after is not None:
                        t.driver.use_credentials(t.credentials_after)
                        self._emit(dep, "deploy", "ok", "from now on logging in with the "
                                   "credential chosen for after loading", t)
                    if restarting:
                        self._emit(dep, "deploy", "ok", result.message or "device restarting", t)
                        back = self._wait_until_available(dep, t)
                        result = back if not back.ok else result
                    elif t.credentials_after is not None:
                        t.driver.disconnect()  # prove the new login works
                        back = t.driver.connect()
                        if not back.ok:
                            result = OperationResult.failed(
                                DeviceOperation.APPLY_CONFIGURATION,
                                f"the configuration was applied, but the login chosen for "
                                f"after loading does not work: {back.message}")
                if result.ok:
                    applied_message = ("back after the restart; configuration saved"
                                       if restarting else result.message)
                    result = t.driver.save_configuration()
                    if result.ok:
                        self._emit_notes(dep, t, "deploy", result)
                    if result.ok and applied_message:
                        result = OperationResult.success(result.operation, result.data,
                                                         applied_message)
            if not result.ok:
                self._check_stop(dep)  # a step ended early by a stop is not a device failure
                self._fail_target(dep, t, "deploy", TargetState.APPLY_FAILED, result.message)
                shown = str(result.diagnostics.get("device_output") or "").strip()
                if shown:  # what the device printed is the evidence a technician needs
                    self._emit(dep, "deploy", "warning",
                               f"device output (last lines): {shown[-600:]}", t)
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
            self._check_stop(dep)
            if t.state is TargetState.NO_CHANGE:
                continue
            custom = t.driver.verify_configuration(t.intended_config, dep.apply_mode)
            if custom is not None:
                # What the device runs now, kept for review whether or not it verified.
                after = t.driver.get_running_configuration()
                if after.ok:
                    t.after_config = str(after.data)
                if custom.ok:
                    t.state = TargetState.VERIFIED
                    self._note_hostname(t)
                    self._emit(dep, "verify", "ok", custom.message or "verified", t)
                    self._emit_warnings(dep, t, "verify", custom)
                    self._checkpoint(dep, t)
                else:
                    ok = self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                           custom.message)
                continue
            running = t.driver.get_running_configuration()
            if not running.ok:
                ok = self._fail_target(dep, t, "verify", TargetState.VERIFY_FAILED,
                                       f"could not read configuration back: {running.message}")
                continue
            t.after_config = str(running.data)
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
                self._note_hostname(t)
                self._emit(dep, "verify", "ok", "running configuration matches intent", t)
                self._checkpoint(dep, t)
        return ok

    @staticmethod
    def _note_hostname(t: DeploymentTarget) -> None:
        facts = t.driver.get_device_facts()
        if facts.ok and facts.data.hostname:
            t.observed_hostname = str(facts.data.hostname).strip() or None

    def _checkpoint(self, dep: Deployment, t: DeploymentTarget) -> None:
        """Keep a named restore point after a verified change, where the device supports it.

        A failure here does not undo a verified change; it is reported as a warning."""
        if not t.checkpoint_label or t.driver.missing_capabilities(
                DeviceOperation.CREATE_CHECKPOINT):
            return
        result = t.driver.create_checkpoint(t.checkpoint_label)
        if result.ok:
            self._emit(dep, "verify", "ok", result.message or f"saved '{t.checkpoint_label}'", t)
        else:
            self._emit(dep, "verify", "warning",
                       f"configuration verified, but the named restore point "
                       f"'{t.checkpoint_label}' was not confirmed: {result.message}", t)

    def _recover(self, dep: Deployment) -> DeploymentState:
        self._move(dep, S.RECOVERING)
        all_ok = True
        for t in dep.targets:
            self._check_stop(dep)
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
                cause = f"{t.message}. " if t.message else ""  # keep why it failed
                t.state = TargetState.MANUAL_RECOVERY_REQUIRED
                t.message = cause + (t.driver.manual_recovery() or (
                    f"Automatic rollback unsupported; restore backup {t.backup.reference} "
                    "manually"))
                self._emit(dep, "recover", "error", t.message, t)
            else:
                all_ok = False
                self._fail_target(dep, t, "recover", TargetState.ROLLBACK_FAILED,
                                  f"rollback failed: {result.message}")
        self._move(dep, S.ROLLED_BACK if all_ok else S.RECOVERY_REQUIRED)
        return dep.state
