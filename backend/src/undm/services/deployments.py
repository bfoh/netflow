"""Deployment use cases.

Each request rebuilds the orchestrator view from the database. During
execution every lifecycle step is committed as it happens, so a process that
dies mid-deployment leaves a transient state behind that
:func:`recover_interrupted_deployments` resolves on the next start.
"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from undm.db.models import (
    ConfigVersion,
    CredentialRef,
    DeploymentEventRecord,
    DeploymentRecord,
    DeploymentTargetRecord,
    Device,
    FirmwareImage,
    Project,
)
from undm.domain.enums import DeviceDeploymentStatus, DeviceEnvironment, ProvisioningStatus
from undm.domain.lifecycle import (
    TRANSIENT_STATES,
    DeploymentState,
    interrupted_outcome,
)
from undm.domain.validation import Severity
from undm.drivers.base import ApplyMode, Capability, Credentials
from undm.drivers.fortinet.config_files import configured_hostname as fortinet_hostname
from undm.drivers.registry import DriverRegistry
from undm.orchestration.deployment import (
    ApprovalRequiredError,
    Deployment,
    DeploymentEvent,
    DeploymentOrchestrator,
    DeploymentTarget,
    StopSignal,
    TargetState,
)
from undm.orchestration.firmware import FirmwareOrchestrator
from undm.orchestration.first_login import FirstLoginOrchestrator
from undm.orchestration.free_address import FreeAddressOrchestrator
from undm.orchestration.license import LicenseOrchestrator
from undm.orchestration.restart import RestartOrchestrator
from undm.security import credentials as creds
from undm.services import app_settings, audit
from undm.services.devices import (
    build_driver,
    inspect_config,
    latest_config,
    login_after_loading_needed,
    port_off,
    set_login_after_loading_needed,
    set_port_off,
)
from undm.services.errors import ConflictError, ForbiddenError, NotFoundError
from undm.services.firmware import FirmwareRepository, device_compatibility
from undm.services.jobs import DeploymentJobs
from undm.services.policy import Policy
from undm.transfer.hub import TransferHub
from undm.transfer.tftp import TftpServerError

S = DeploymentState


# Where a person sets each project setting a file can require.
_SETTING_LABELS = {"certificate_subject": "Settings → For all systems → HTTPS certificate, "
                                         "or the system page"}

MAX_STAGING_STEPS = 8
_STEP_WORDS = {"first_login": "first login", "firmware": "firmware",
               "configuration": "load a file", "free_address": "move the other device aside",
               "license": "load the license"}


@dataclass(frozen=True)
class StagingStep:
    """One step of a device's staging plan (D-085)."""

    kind: str  # first_login | firmware | configuration | free_address
    # free_address: the device of the system to take off its address (D-107)
    other_device_id: str | None = None
    address: str | None = None  # ignored since D-107 (no spare address)
    image_id: str | None = None
    allow_downgrade: bool = False
    also_secondary: bool = False
    version_id: str | None = None
    apply_mode: ApplyMode | None = None  # None: as the file's kind requires (else merge)
    credential_after_ref_id: str | None = None
    secrets: dict[str, str] | None = None


def _utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)
# Target states reached without a successful connection during execution.
_NOT_CONNECTED = frozenset({TargetState.PENDING, TargetState.PREVIEWED,
                            TargetState.PREVIEW_FAILED, TargetState.PREFLIGHT_FAILED})


class DeploymentService:
    def __init__(self, session: Session, registry: DriverRegistry, policy: Policy,
                 *, firmware_reboot_wait: tuple[int, float] = (30, 20.0),
                 firmware_separate_approver: bool = True,
                 transfer_hub: TransferHub | None = None) -> None:
        self.s = session
        self.registry = registry
        self.policy = policy
        self.require_separate_approver = policy.require_separate_approver
        self.firmware_reboot_wait = firmware_reboot_wait
        self.firmware_separate_approver = firmware_separate_approver
        self.transfer_hub = transfer_hub

    def _policy_problem(self, device: Device, dry_run: bool,
                        firmware: bool = False) -> str | None:
        simulated = self.registry.get(device.driver_id).info.simulated
        if dry_run:
            return self.policy.read_problem(device.name, device.environment, simulated)
        if firmware and not simulated:
            return self.policy.firmware_problem(device.name, device.environment, simulated)
        if simulated and device.environment == DeviceEnvironment.PRODUCTION.value \
                and not self.policy.allow_production_deployments:
            return (f"{device.name} is a production device; production deployments are "
                    "disabled by policy")
        return self.policy.write_problem(device.name, device.environment, simulated)

    # -- helpers --------------------------------------------------------------------
    def _orchestrator(self, rec: DeploymentRecord, *, commit_each_step: bool = False
                      ) -> DeploymentOrchestrator:
        def sink(dep: Deployment, ev: DeploymentEvent) -> None:
            rec.events.append(DeploymentEventRecord(
                seq=len(rec.events), timestamp=ev.timestamp, device_id=ev.device_id,
                stage=ev.stage, status=ev.status, message=ev.message,
            ))
            self._sync(rec, dep)
            if commit_each_step:
                self.s.commit()

        if rec.kind == "firmware":
            attempts, delay = self.firmware_reboot_wait
            return FirmwareOrchestrator(
                sink=sink, reboot_wait_attempts=attempts, reboot_wait_delay_s=delay,
                require_separate_approver=self.firmware_separate_approver)
        attempts, delay = self.firmware_reboot_wait
        cls = {"first_login": FirstLoginOrchestrator,
               "free_address": FreeAddressOrchestrator,
               "restart": RestartOrchestrator,
               "license": LicenseOrchestrator}.get(rec.kind, DeploymentOrchestrator)
        return cls(
            sink=sink, require_separate_approver=self.require_separate_approver,
            restart_wait_attempts=attempts, restart_wait_delay_s=delay,
        )

    def _to_domain(self, rec: DeploymentRecord) -> Deployment:
        targets = []
        for t in rec.targets:
            device = self.s.get(Device, t.device_id)
            assert device is not None
            text = ""
            label: str | None = None
            if t.config_version_id:
                cfg = self.s.get(ConfigVersion, t.config_version_id)
                assert cfg is not None
                text = cfg.text
                if cfg.kind == "imported" and cfg.reference:
                    # Named after the file, as the team names FortiGate revisions.
                    label = PurePath(cfg.reference).stem[:60] or None
                elif cfg.kind == "license":
                    label = PurePath(cfg.reference or "license.lic").name[:80]
            serial = (device.observed_facts or {}).get("serial_number")
            dt = DeploymentTarget(device.id, device.name, build_driver(device, self.registry),
                                  text, expected_serial=serial)
            dt.state = TargetState(t.state)
            dt.checkpoint_label = label
            subject = app_settings.effective_certificate(self.s, device.project)
            if subject:
                dt.settings["certificate_subject"] = subject
            dt.from_version, dt.target_version = t.from_version, t.to_version
            if rec.kind == "first_login" and device.credential_ref_id:
                # The login the first login sets on the unit (D-073).
                dt.credentials_before = self._credentials_for(device, device.credential_ref_id)
            targets.append(dt)
        dep = Deployment(
            deployment_id=rec.id, targets=targets, created_by=rec.created_by,
            apply_mode=ApplyMode(rec.apply_mode), dry_run=rec.dry_run,
            state=S(rec.state), approved_by=rec.approved_by, approved_at=rec.approved_at,
            window_start=_utc(rec.window_start), window_end=_utc(rec.window_end),
        )
        if rec.kind == "firmware":
            assert rec.firmware_image_id is not None
            img = self.s.get(FirmwareImage, rec.firmware_image_id)
            assert img is not None
            dep.firmware = FirmwareRepository.ref(img)
            dep.min_from_version = img.min_from_version
            dep.allow_downgrade = bool(rec.allow_downgrade)
            dep.also_secondary = bool(rec.also_secondary)
        return dep

    @staticmethod
    def _sync(rec: DeploymentRecord, dep: Deployment) -> None:
        rec.state = dep.state.value
        rec.approved_by = dep.approved_by
        rec.approved_at = dep.approved_at
        by_device = {t.device_id: t for t in dep.targets}
        for tr in rec.targets:
            t = by_device[tr.device_id]
            tr.state = t.state.value
            tr.message = t.message
            if t.diff is not None:
                tr.diff = t.diff.unified
            if dep.firmware is not None:
                tr.from_version = t.from_version or t.current_version or tr.from_version
                tr.to_version = t.target_version or dep.firmware.version
            elif rec.kind == "free_address" and t.target_version:
                tr.to_version = t.target_version  # e.g. "port 2 off" once done

    def get(self, deployment_id: str) -> DeploymentRecord:
        rec = self.s.get(DeploymentRecord, deployment_id)
        if rec is None:
            raise NotFoundError("Deployment not found")
        return rec

    # -- locking --------------------------------------------------------------------
    def _lock_devices(self, rec: DeploymentRecord) -> None:
        """Atomically claim every target device, or none of them."""
        ids = [t.device_id for t in rec.targets]
        result: CursorResult[Any] = self.s.execute(  # type: ignore[assignment]
            update(Device)
            .where(Device.id.in_(ids), Device.locked_by_deployment_id.is_(None))
            .values(locked_by_deployment_id=rec.id)
        )
        if result.rowcount != len(ids):
            self.s.rollback()
            busy = self.s.scalars(
                select(Device.name).where(Device.id.in_(ids),
                                          Device.locked_by_deployment_id.is_not(None))
            ).all()
            raise ConflictError(
                f"Device(s) busy with another deployment: {', '.join(sorted(busy))}"
            )
        self.s.commit()

    def _unlock_devices(self, rec: DeploymentRecord) -> None:
        self.s.execute(
            update(Device).where(Device.locked_by_deployment_id == rec.id)
            .values(locked_by_deployment_id=None)
        )

    # -- use cases --------------------------------------------------------------------
    def create(
        self, project_id: str, device_ids: list[str], actor: str,
        *, dry_run: bool, apply_mode: ApplyMode,
        config_versions: dict[str, str] | None = None,
        secrets: dict[str, dict[str, str]] | None = None,
        credentials_after: dict[str, str] | None = None,
        staging: tuple[str, int] | None = None, defer_preview: str | None = None,
    ) -> DeploymentRecord:
        if not device_ids:
            raise ConflictError("Select at least one device")
        if len(set(device_ids)) != len(device_ids):
            raise ConflictError("A device is selected more than once")
        rec = DeploymentRecord(
            project_id=project_id, state=S.DRAFT.value, dry_run=dry_run,
            apply_mode=apply_mode.value, created_by=actor,
            staging_id=staging[0] if staging else None,
            staging_step=staging[1] if staging else None,
        )
        self.s.add(rec)
        for pos, did in enumerate(device_ids):
            device = self.s.get(Device, did)
            if device is None or device.project_id != project_id:
                raise NotFoundError(f"Device {did} not found in project")
            problem = self._policy_problem(device, dry_run)
            if problem:
                raise ForbiddenError(problem)
            cfg = self._choose_config(device, (config_versions or {}).get(did))
            if not dry_run:
                self._check_file_can_be_applied(device, cfg, apply_mode)
            refs = (secrets or {}).get(did) or None
            if refs:
                self._check_secrets(device, cfg, refs)
            after = (credentials_after or {}).get(did) or None
            if after:
                self._credentials_for(device, after)  # exists, belongs here, has a secret
            elif (not dry_run and apply_mode is ApplyMode.REPLACE
                  and login_after_loading_needed(device)):
                raise ConflictError(
                    f"{device.name} still has the login it had before its console setup (its "
                    "password survived): choose the approved login as 'Login after loading' "
                    "for its file, which sets the approved password.")
            rec.targets.append(DeploymentTargetRecord(
                device_id=did, position=pos, config_version_id=cfg.id,
                state=TargetState.PENDING.value, secret_refs=refs,
                credential_after_ref_id=after,
            ))
        unknown = set(config_versions or {}) - set(device_ids)
        if unknown:
            raise ConflictError("Configuration chosen for a device that is not in the plan")
        if set(secrets or {}) - set(device_ids):
            raise ConflictError("Secret values chosen for a device that is not in the plan")
        if set(credentials_after or {}) - set(device_ids):
            raise ConflictError("Login after loading chosen for a device that is not in the plan")
        self.s.flush()
        if not dry_run:
            for tr in rec.targets:
                named = self.s.get(Device, tr.device_id)
                file = self.s.get(ConfigVersion, tr.config_version_id)
                if named is not None and file is not None:
                    self._name_from_file(named, file, actor, rec)
        dep = self._to_domain(rec)
        dep.defer_preview = defer_preview
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": device_ids, "dry_run": dry_run, "apply_mode": apply_mode.value,
                      "config_versions": {t.device_id: t.config_version_id for t in rec.targets},
                      **({"staging_id": staging[0], "staging_step": staging[1]}
                         if staging else {})})
        return rec

    # -- first login on a new unit (D-073) ---------------------------------------------
    def create_first_login(self, project_id: str, device_id: str, actor: str, *,
                           staging: tuple[str, int] | None = None) -> DeploymentRecord:
        """A plan that sets the device's login on a new unit at its first login."""
        device = self.s.get(Device, device_id)
        if device is None or device.project_id != project_id:
            raise NotFoundError(f"Device {device_id} not found in project")
        problem = self._policy_problem(device, False)
        if problem:
            raise ForbiddenError(problem)
        if not device.credential_ref_id:
            raise ConflictError("Attach the device's login (user and the approved password) "
                                "first: the first login sets that password on the unit")
        rec = DeploymentRecord(
            project_id=project_id, kind="first_login", state=S.DRAFT.value, dry_run=False,
            apply_mode=ApplyMode.MERGE.value, created_by=actor,
            staging_id=staging[0] if staging else None,
            staging_step=staging[1] if staging else None)
        rec.targets.append(DeploymentTargetRecord(
            device_id=device_id, position=0, state=TargetState.PENDING.value))
        self.s.add(rec)
        self.s.flush()
        dep = self._to_domain(rec)
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": [device_id], "kind": "first_login",
                      **({"staging_id": staging[0], "staging_step": staging[1]}
                         if staging else {})})
        return rec

    # -- take a device off its address until its next restart (D-107) -------------------
    def create_free_address(self, project_id: str, device_id: str, actor: str,
                            *, staging: tuple[str, int] | None = None) -> DeploymentRecord:
        device = self.s.get(Device, device_id)
        if device is None or device.project_id != project_id:
            raise NotFoundError(f"Device {device_id} not found in project")
        self._check_free_address(device)
        problem = self._policy_problem(device, False)
        if problem:
            raise ForbiddenError(problem)
        rec = DeploymentRecord(
            project_id=project_id, kind="free_address", state=S.DRAFT.value, dry_run=False,
            apply_mode=ApplyMode.MERGE.value, created_by=actor,
            staging_id=staging[0] if staging else None,
            staging_step=staging[1] if staging else None)
        # Its address and what it becomes are kept in the target's from/to fields.
        rec.targets.append(DeploymentTargetRecord(
            device_id=device_id, position=0, state=TargetState.PENDING.value,
            from_version=device.management_address, to_version="management port off"))
        self.s.add(rec)
        self.s.flush()
        dep = self._to_domain(rec)
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": [device_id], "kind": "free_address",
                      **({"staging_id": staging[0], "staging_step": staging[1]}
                         if staging else {})})
        return rec

    def _check_free_address(self, device: Device) -> None:
        if device.driver_id not in self.registry or Capability.MANAGEMENT_PORT_OFF not in \
                self.registry.get(device.driver_id).info.capabilities:
            raise ConflictError(f"UNDM cannot take {device.name} off its address: unplug it "
                                "from the bench network instead")

    # -- restart a device on request (D-099) --------------------------------------------
    def create_restart(self, project_id: str, device_id: str, actor: str) -> DeploymentRecord:
        device = self.s.get(Device, device_id)
        if device is None or device.project_id != project_id:
            raise NotFoundError(f"Device {device_id} not found in project")
        if device.driver_id not in self.registry or Capability.RESTART not in \
                self.registry.get(device.driver_id).info.capabilities:
            raise ConflictError(f"UNDM cannot restart {device.name} on request: no verified "
                                "restart procedure for its model yet")
        problem = self._policy_problem(device, False)
        if problem:
            raise ForbiddenError(problem)
        rec = DeploymentRecord(
            project_id=project_id, kind="restart", state=S.DRAFT.value, dry_run=False,
            apply_mode=ApplyMode.MERGE.value, created_by=actor)
        # Where it is reached now, and its own address it answers at after the restart.
        rec.targets.append(DeploymentTargetRecord(
            device_id=device_id, position=0, state=TargetState.PENDING.value,
            from_version=device.management_address,
            to_version=device.management_address))
        self.s.add(rec)
        self.s.flush()
        dep = self._to_domain(rec)
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": [device_id], "kind": "restart"})
        return rec

    # -- a license file on a device (D-100) ---------------------------------------------
    def store_license(self, device: Device, filename: str, data: bytes,
                      actor: str) -> ConfigVersion:
        """Keep the team's license file for a device. Its content is not checked (the team
        verified it), never shown, and kept out of exports and backups; only its name and
        hash are audited."""
        if not data:
            raise ConflictError("The license file is empty")
        if len(data) > 1_000_000:
            raise ConflictError("A license file is small; this one is over 1 MB")
        if device.driver_id not in self.registry or Capability.LICENSE_FILE not in \
                self.registry.get(device.driver_id).info.capabilities:
            raise ConflictError(f"UNDM cannot load a license file on {device.name}")
        digest = hashlib.sha256(data).hexdigest()
        v = ConfigVersion(device_id=device.id, kind="license",
                          text=base64.b64encode(data).decode(), sha256=digest,
                          reference=PurePath(filename).name[:200] or "license.lic",
                          created_by=actor)
        self.s.add(v)
        self.s.flush()
        audit.record(self.s, actor, "device.license_stored", "device", device.id,
                     details={"file": v.reference, "sha256": digest, "bytes": len(data)})
        return v

    def create_license(self, project_id: str, device_id: str, version_id: str,
                       actor: str, *, staging: tuple[str, int] | None = None,
                       defer_preview: str | None = None) -> DeploymentRecord:
        device = self.s.get(Device, device_id)
        if device is None or device.project_id != project_id:
            raise NotFoundError(f"Device {device_id} not found in project")
        cfg = self.s.get(ConfigVersion, version_id)
        if cfg is None or cfg.device_id != device_id or cfg.kind != "license":
            raise ConflictError("Choose a license file stored for this device")
        problem = self._policy_problem(device, False)
        if problem:
            raise ForbiddenError(problem)
        rec = DeploymentRecord(
            project_id=project_id, kind="license", state=S.DRAFT.value, dry_run=False,
            apply_mode=ApplyMode.MERGE.value, created_by=actor,
            staging_id=staging[0] if staging else None,
            staging_step=staging[1] if staging else None)
        rec.targets.append(DeploymentTargetRecord(
            device_id=device_id, position=0, state=TargetState.PENDING.value,
            config_version_id=cfg.id))
        self.s.add(rec)
        self.s.flush()
        dep = self._to_domain(rec)
        dep.defer_preview = defer_preview
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": [device_id], "kind": "license", "file": cfg.reference,
                      **({"staging_id": staging[0], "staging_step": staging[1]}
                         if staging else {})})
        return rec

    # -- staging plans (D-071) ----------------------------------------------------------
    def create_staging(self, project_id: str, device_id: str, actor: str, *,
                       base_version_id: str, site_version_id: str,
                       credential_after_ref_id: str | None = None,
                       secrets: dict[str, str] | None = None,
                       first_login: bool = False) -> list[DeploymentRecord]:
        """Base file (replace), then site file (merge), for one device, as one plan.

        Step 2 is previewed at its run, once the base file is on the device: a site file
        loaded over an earlier site configuration can be refused part-way (D-070)."""
        device = self.s.get(Device, device_id)
        if device is None or device.project_id != project_id:
            raise NotFoundError(f"Device {device_id} not found in project")
        if base_version_id == site_version_id:
            raise ConflictError("Choose two different files: the base file and the site file")
        site = self._choose_config(device, site_version_id)
        self._check_file_can_be_applied(device, site, ApplyMode.MERGE)  # before any preview
        staging_id = str(uuid.uuid4())
        self._reopen_system(project_id, actor)
        steps: list[DeploymentRecord] = []
        if first_login:
            steps.append(self.create_first_login(project_id, device_id, actor,
                                                 staging=(staging_id, 1)))
        n = len(steps)
        base_rec = self.create(
            project_id, [device_id], actor, dry_run=False, apply_mode=ApplyMode.REPLACE,
            config_versions={device_id: base_version_id},
            credentials_after=({device_id: credential_after_ref_id}
                               if credential_after_ref_id else None),
            staging=(staging_id, n + 1),
            defer_preview=("it is made at the run, after the first login has set the "
                           "device's login" if first_login else None))
        site_rec = self.create(
            project_id, [device_id], actor, dry_run=False, apply_mode=ApplyMode.MERGE,
            config_versions={device_id: site_version_id},
            secrets={device_id: secrets} if secrets else None,
            staging=(staging_id, n + 2),
            defer_preview=f"it is made at the run, after step {n + 1} has restored the base "
                          "file")
        steps += [base_rec, site_rec]
        failed = next((r for r in steps if r.state == S.FAILED.value), None)
        if failed is not None:
            self.cancel_rest_of_staging(staging_id, failed.staging_step or 0, actor,
                                        f"step {failed.staging_step} failed its validation "
                                        "or preview")
        audit.record(self.s, actor, "staging.create", "staging_plan", staging_id,
                     details={"device": device_id, "steps": [r.id for r in steps],
                              "first_login": first_login,
                              "base_version": base_version_id, "site_version": site_version_id})
        return steps

    def create_device_staging(self, project_id: str, device_id: str, actor: str,
                              steps: list[StagingStep]) -> list[DeploymentRecord]:
        """Any sequence of first login, firmware and file steps for one device, as one plan
        (D-085). Every step is checked offline before any is made; steps after the first
        are previewed at their run, because the earlier steps change the device."""
        device = self.s.get(Device, device_id)
        if device is None or device.project_id != project_id:
            raise NotFoundError(f"Device {device_id} not found in project")
        if not 1 <= len(steps) <= MAX_STAGING_STEPS:
            raise ConflictError(f"A staging plan has 1 to {MAX_STAGING_STEPS} steps")
        if any(s.kind == "first_login" for s in steps[1:]):
            raise ConflictError("The first login can only be the first step")
        for n, step in enumerate(steps, 1):
            self._check_staging_step(device, n, step)
        staging_id = str(uuid.uuid4())
        self._reopen_system(project_id, actor)
        made: list[DeploymentRecord] = []
        for n, step in enumerate(steps, 1):
            later = (f"it is made at the run, after step {n - 1} ({_STEP_WORDS[steps[n - 2].kind]})"
                     if n > 1 else None)
            if step.kind == "first_login":
                rec = self.create_first_login(project_id, device_id, actor,
                                              staging=(staging_id, n))
            elif step.kind == "free_address":
                rec = self.create_free_address(project_id, str(step.other_device_id), actor,
                                               staging=(staging_id, n))
            elif step.kind == "license":
                rec = self.create_license(project_id, device_id, str(step.version_id), actor,
                                          staging=(staging_id, n), defer_preview=later)
            elif step.kind == "firmware":
                assert step.image_id is not None
                rec = self.create_firmware(
                    project_id, [device_id], step.image_id, actor, dry_run=False,
                    allow_downgrade=step.allow_downgrade, also_secondary=step.also_secondary,
                    staging=(staging_id, n), defer_preview=later)
            else:
                rec = self.create(
                    project_id, [device_id], actor, dry_run=False,
                    apply_mode=self._staging_mode(device, step),
                    config_versions={device_id: str(step.version_id)},
                    secrets={device_id: step.secrets} if step.secrets else None,
                    credentials_after=({device_id: step.credential_after_ref_id}
                                       if step.credential_after_ref_id else None),
                    staging=(staging_id, n), defer_preview=later)
            made.append(rec)
            if rec.state == S.FAILED.value:
                break
        failed = next((r for r in made if r.state == S.FAILED.value), None)
        audit.record(self.s, actor, "staging.create", "staging_plan", staging_id,
                     details={"device": device_id, "steps": [r.id for r in made],
                              "kinds": [s.kind for s in steps]})
        if failed is not None:
            # A step that fails its check ends the plan: the steps not yet made are not made.
            self.cancel_rest_of_staging(staging_id, failed.staging_step or 0, actor,
                                        f"step {failed.staging_step} failed its validation "
                                        "or preview")
        return made

    def _staging_mode(self, device: Device, step: StagingStep) -> ApplyMode:
        """The mode chosen, else the one the file's kind requires, else merge."""
        if step.apply_mode is not None:
            return step.apply_mode
        cfg = self._choose_config(device, step.version_id)
        report = inspect_config(self.s, cfg, self.registry)
        return report.apply_mode if report and report.apply_mode else ApplyMode.MERGE

    def _check_staging_step(self, device: Device, n: int, step: StagingStep) -> None:
        """What can be known before anything is made: right inputs, files fit, image fits."""
        where = f"Step {n} ({_STEP_WORDS.get(step.kind, step.kind)})"
        if step.kind == "first_login":
            if not device.credential_ref_id:
                raise ConflictError(f"{where}: choose the device's login first (user and the "
                                    "approved password); the first login sets that password")
            problem = self._policy_problem(device, False)
        elif step.kind == "firmware":
            img = self.s.get(FirmwareImage, step.image_id) if step.image_id else None
            if img is None:
                raise ConflictError(f"{where}: choose an approved firmware image")
            if img.status != "approved":
                raise ConflictError(f"{where}: image {img.version} is {img.status}, not approved")
            errors = [i.message for i in device_compatibility(img, device, self.registry)
                      if i.severity is Severity.ERROR]
            if errors:
                raise ConflictError(f"{where}: image {img.version} does not fit "
                                    f"{device.name}", details=errors)
            problem = self._policy_problem(device, False, firmware=True)
        elif step.kind == "configuration":
            if not step.version_id:
                raise ConflictError(f"{where}: choose the file to load")
            cfg = self._choose_config(device, step.version_id)
            self._check_file_can_be_applied(device, cfg, self._staging_mode(device, step))
            if step.secrets:
                self._check_secrets(device, cfg, step.secrets)
            if step.credential_after_ref_id:
                self._credentials_for(device, step.credential_after_ref_id)
            problem = self._policy_problem(device, False)
        elif step.kind == "license":
            # Optional in a staging plan; also loadable later from the device's menu (D-109).
            lic = self.s.get(ConfigVersion, step.version_id) if step.version_id else None
            if lic is None or lic.device_id != device.id or lic.kind != "license":
                raise ConflictError(f"{where}: choose a license file stored for this device")
            if device.driver_id not in self.registry or Capability.LICENSE_FILE not in \
                    self.registry.get(device.driver_id).info.capabilities:
                raise ConflictError(f"{where}: UNDM cannot load a license on {device.name}")
            problem = self._policy_problem(device, False)
        elif step.kind == "free_address":
            other = self.s.get(Device, step.other_device_id) if step.other_device_id else None
            if other is None or other.project_id != device.project_id or other.id == device.id:
                raise ConflictError(f"{where}: choose another device of this system")
            self._check_free_address(other)
            problem = self._policy_problem(other, False)
        else:
            raise ConflictError(f"Step {n}: unknown kind '{step.kind}'")
        if problem:
            raise ForbiddenError(problem)

    def staging_steps(self, staging_id: str) -> list[DeploymentRecord]:
        steps = list(self.s.scalars(
            select(DeploymentRecord).where(DeploymentRecord.staging_id == staging_id)
            .order_by(DeploymentRecord.staging_step)))
        if not steps:
            raise NotFoundError("Staging plan not found")
        return steps

    def approve_staging(self, staging_id: str, actor: str, window_start: datetime | None = None,
                        window_end: datetime | None = None) -> list[DeploymentRecord]:
        """One approval for every step still awaiting it; firmware steps take the
        maintenance window given."""
        steps = self.staging_steps(staging_id)
        waiting = [r for r in steps if r.state == S.AWAITING_APPROVAL.value]
        if not waiting:
            raise ConflictError("No step of this staging plan is awaiting approval")
        if any(r.kind == "firmware" for r in waiting) and (window_start is None
                                                          or window_end is None):
            raise ConflictError("This staging plan has a firmware step: give the maintenance "
                                "window it may run in")
        for rec in waiting:
            self.approve(rec.id, actor, window_start, window_end)
        audit.record(self.s, actor, "staging.approve", "staging_plan", staging_id,
                     details={"steps": [r.id for r in waiting]})
        return steps

    # -- the end of staging a system (D-108) ---------------------------------------------
    def _reopen_system(self, project_id: str, actor: str, *, reason: str = "new staging plan"
                       ) -> None:
        project = self.s.get(Project, project_id)
        if project is not None and project.staged_at is not None:
            project.staged_at, project.staged_by = None, ""
            audit.record(self.s, actor, "system.reopened", "project", project_id,
                         details={"reason": reason})

    def _console_only(self, device: Device) -> bool:
        """Staged by its console setup alone: a console-only device whose driver loads no
        file. (The modem loads its file by a plan since D-116.)"""
        if device.driver_id not in self.registry:
            return False
        caps = self.registry.get(device.driver_id).info.capabilities
        return (Capability.SERIAL_CONSOLE in caps and Capability.SSH not in caps
                and Capability.CONFIGURATION_APPLY not in caps)

    def finish_system(self, project_id: str, device_ids: list[str], actor: str) -> Project:
        """Record that staging of a system is finished: every named device's latest staging
        plan succeeded, and none is still off the network (D-107)."""
        project = self.s.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project not found")
        latest: dict[str, list[DeploymentRecord]] = {}
        for _sid, device_id, steps in self.project_stagings(project_id):
            latest.setdefault(device_id, steps)  # newest first
        problems: list[str] = []
        names: list[str] = []
        for did in dict.fromkeys(device_ids):
            device = self.s.get(Device, did)
            if device is None or device.project_id != project_id:
                raise NotFoundError(f"Device {did} not found in project")
            names.append(device.name)
            mine = latest.get(did)
            if not mine and self._console_only(device):
                # Staged over its console only, with no plan: its console setup is its
                # staging.
                if device.provisioning_status not in (ProvisioningStatus.BOOTSTRAPPED.value,
                                                      ProvisioningStatus.MANAGED.value):
                    problems.append(f"{device.name} has not had its console setup")
            elif not mine:
                problems.append(f"{device.name} has no staging plan")
            elif any(r.state != S.SUCCEEDED.value for r in mine):
                problems.append(f"{device.name}'s latest staging plan has not succeeded")
            if port_off(device):
                problems.append(f"{device.name} still has its management port off: switch it "
                                "off and on, then Test it")
        if problems:
            raise ConflictError("Staging is not finished: " + "; ".join(problems))
        project.staged_at, project.staged_by = datetime.now(UTC), actor
        audit.record(self.s, actor, "system.staged", "project", project_id,
                     details={"devices": names})
        return project

    def reopen_system(self, project_id: str, actor: str) -> Project:
        project = self.s.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project not found")
        self._reopen_system(project_id, actor, reason="reopened by a person")
        return project

    def project_stagings(self, project_id: str) -> list[tuple[str, str, list[DeploymentRecord]]]:
        """(staging id, device id, steps) for every staging plan of a project, newest first."""
        recs = list(self.s.scalars(
            select(DeploymentRecord).where(DeploymentRecord.project_id == project_id,
                                           DeploymentRecord.staging_id.is_not(None))
            .order_by(DeploymentRecord.created_at.desc(), DeploymentRecord.staging_step)))
        plans: dict[str, list[DeploymentRecord]] = {}
        for r in recs:
            plans.setdefault(str(r.staging_id), []).append(r)
        out = []
        for sid, steps in plans.items():
            steps.sort(key=lambda r: r.staging_step or 0)
            # The plan's device: a 'free_address' step targets another device (D-096).
            own = next((r for r in steps if r.kind != "free_address"), steps[0])
            device = own.targets[0].device_id if own.targets else ""
            out.append((sid, device, steps))
        return out

    def check_staging_can_start(self, staging_id: str) -> list[DeploymentRecord]:
        steps = self.staging_steps(staging_id)
        pending = [r for r in steps if r.state != S.SUCCEEDED.value]
        if not pending:
            raise ConflictError("Every step of this staging plan has succeeded already")
        not_ready = [r for r in pending if r.state != S.READY.value]
        if not_ready:
            r = not_ready[0]
            raise ConflictError(f"Step {r.staging_step} is {r.state.replace('_', ' ')}: every "
                                "step must be approved (ready) before the plan runs")
        self.check_can_execute(pending[0].id)
        return steps

    def cancel_rest_of_staging(self, staging_id: str, after_step: int, actor: str,
                               why: str) -> None:
        """Later steps that will not run because an earlier step did not succeed."""
        for rec in self.staging_steps(staging_id):
            if (rec.staging_step or 0) > after_step and rec.state in {
                    S.DRAFT.value, S.AWAITING_APPROVAL.value, S.READY.value}:
                self.cancel(rec.id, actor)
                rec.events.append(DeploymentEventRecord(
                    seq=len(rec.events), timestamp=datetime.now(UTC), stage="lifecycle",
                    status="skipped", message=f"not run: {why}"))
        self.s.commit()

    def _check_file_can_be_applied(self, device: Device, cfg: ConfigVersion,
                                   apply_mode: ApplyMode) -> None:
        """Refuse to apply a supplied file in a way that does not fit what the file is.

        Example: a full backup must be restored as a whole; sending it line by line as
        if it were a list of changes would leave the device in an undefined state.
        """
        report = inspect_config(self.s, cfg, self.registry)
        if report is None:
            return
        what = f"{device.name}: '{cfg.reference}' is a {report.summary}"
        if report.problems:
            raise ConflictError(f"{what} with problems; it cannot be applied as it is",
                                details=list(report.problems))
        if report.blocked_reason:
            raise ConflictError(f"{what}. {report.blocked_reason}")
        if report.apply_mode is not None and report.apply_mode is not apply_mode:
            raise ConflictError(
                f"{what}; it can only be applied in {report.apply_mode.value} mode, not "
                f"{apply_mode.value} mode")
        project = self.s.get(Project, device.project_id)
        for name, why in report.required_settings.items():
            value = (app_settings.effective_certificate(self.s, project)
                     if name == "certificate_subject" else getattr(project, name, None))
            if not value:
                label = _SETTING_LABELS.get(name, name)
                raise ConflictError(f"{what}. {why}: set it first ({label}).")

    def _credentials_for(self, device: Device, ref_id: str) -> Credentials:
        ref = self.s.get(CredentialRef, ref_id)
        if not app_settings.usable_by(ref, device.project_id):
            raise ConflictError(f"{device.name}: login after loading: credential not found")
        try:
            return creds.resolve(ref.provider, ref.locator)
        except creds.CredentialResolutionError as e:
            raise ConflictError(f"{device.name}: credential '{ref.name}': {e}") from e

    def _secret_values(self, device: Device, refs: dict[str, str]) -> dict[str, str]:
        """Read the values for a target's secret slots from the credential store."""
        values: dict[str, str] = {}
        for slot_id, ref_id in refs.items():
            ref = self.s.get(CredentialRef, ref_id)
            if not app_settings.usable_by(ref, device.project_id):
                raise ConflictError(f"{device.name}: credential for '{slot_id}' not found")
            try:
                values[slot_id] = creds.resolve(ref.provider, ref.locator).password
            except creds.CredentialResolutionError as e:
                raise ConflictError(f"{device.name}: credential '{ref.name}': {e}") from e
            if not values[slot_id]:
                raise ConflictError(f"{device.name}: credential '{ref.name}' has an empty "
                                    "secret; store the value to send first")
        return values

    def _check_secrets(self, device: Device, cfg: ConfigVersion, refs: dict[str, str]) -> None:
        """The slots exist in the chosen file and the values can be sent (checked, not kept)."""
        report = inspect_config(self.s, cfg, self.registry)
        known = {slot.slot_id for slot in (report.secret_slots if report else ())}
        unknown = sorted(set(refs) - known)
        if unknown:
            raise ConflictError(f"{device.name}: the chosen file has no secret setting "
                                f"{', '.join(unknown)}")
        driver = build_driver(device, self.registry)
        try:
            driver.prepare_for_device(cfg.text, self._secret_values(device, refs))
        except ValueError as e:
            raise ConflictError(f"{device.name}: {e}") from e

    def _choose_config(self, device: Device, version_id: str | None) -> ConfigVersion:
        """Explicit version if given; else latest generated; else latest imported."""
        if version_id:
            cfg = self.s.get(ConfigVersion, version_id)
            if cfg is None or cfg.device_id != device.id:
                raise NotFoundError(f"{device.name}: configuration version not found")
            return cfg
        cfg = latest_config(self.s, device.id, "generated") or latest_config(
            self.s, device.id, "imported")
        if cfg is None:
            raise ConflictError(f"{device.name}: generate or import a configuration first")
        return cfg

    def approve(self, deployment_id: str, actor: str, window_start: datetime | None = None,
                window_end: datetime | None = None) -> DeploymentRecord:
        rec = self.get(deployment_id)
        if rec.state != S.AWAITING_APPROVAL.value:
            raise ConflictError(f"Deployment is not awaiting approval (state {rec.state})")
        dep = self._to_domain(rec)
        if rec.kind == "firmware":
            dep.window_start, dep.window_end = _utc(window_start), _utc(window_end)
        try:
            self._orchestrator(rec).approve(dep, actor)
        except ApprovalRequiredError as e:
            raise ForbiddenError(str(e)) from e
        if rec.kind == "firmware":
            rec.window_start, rec.window_end = dep.window_start, dep.window_end
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.approve", "deployment", rec.id, details={
            "window_start": str(rec.window_start), "window_end": str(rec.window_end)}
            if rec.kind == "firmware" else None)
        return rec

    def create_firmware(
        self, project_id: str, device_ids: list[str], image_id: str, actor: str,
        *, dry_run: bool, allow_downgrade: bool = False, also_secondary: bool = False,
        staging: tuple[str, int] | None = None, defer_preview: str | None = None,
    ) -> DeploymentRecord:
        if not device_ids:
            raise ConflictError("Select at least one device")
        if len(set(device_ids)) != len(device_ids):
            raise ConflictError("A device is selected more than once")
        img = self.s.get(FirmwareImage, image_id)
        if img is None:
            raise NotFoundError("Firmware image not found")
        rec = DeploymentRecord(
            project_id=project_id, kind="firmware", firmware_image_id=img.id,
            state=S.DRAFT.value, dry_run=dry_run, apply_mode=ApplyMode.MERGE.value,
            created_by=actor, allow_downgrade=allow_downgrade, also_secondary=also_secondary,
            staging_id=staging[0] if staging else None,
            staging_step=staging[1] if staging else None,
        )
        self.s.add(rec)
        problems: dict[str, list[str]] = {}
        for pos, did in enumerate(device_ids):
            device = self.s.get(Device, did)
            if device is None or device.project_id != project_id:
                raise NotFoundError(f"Device {did} not found in project")
            problem = self._policy_problem(device, dry_run, firmware=True)
            if problem:
                raise ForbiddenError(problem)
            issues = [i for i in device_compatibility(img, device, self.registry)
                      if i.severity is Severity.ERROR]
            if issues:
                problems[device.name] = [i.message for i in issues]
            rec.targets.append(DeploymentTargetRecord(
                device_id=did, position=pos, state=TargetState.PENDING.value,
                to_version=img.version,
            ))
        if problems:
            raise ConflictError("Firmware image is not compatible with every selected device",
                                details=problems)
        self.s.flush()
        dep = self._to_domain(rec)
        dep.defer_preview = defer_preview
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        if not img.integrity_verified:
            rec.events.append(DeploymentEventRecord(
                seq=len(rec.events), timestamp=datetime.now(UTC), stage="validate",
                status="warning",
                message=f"The image {img.version} was approved by {img.approved_by} WITHOUT the "
                        f"vendor's checksum; reason given: {img.unverified_reason}"))
        audit.record(self.s, actor, "firmware_deployment.create", "deployment", rec.id,
                     rec.state, {"devices": device_ids, "image": img.id, "version": img.version,
                                 "image_verified": img.integrity_verified,
                                 "dry_run": dry_run, "allow_downgrade": allow_downgrade,
                                 "also_secondary": also_secondary,
                                 **({"staging_id": staging[0], "staging_step": staging[1]}
                                    if staging else {})})
        return rec

    def check_can_execute(self, deployment_id: str) -> DeploymentRecord:
        """Everything that must hold before a run starts; raises the reason if not."""
        rec = self.get(deployment_id)
        if rec.state != S.READY.value:
            raise ConflictError(f"Deployment must be ready to execute (state {rec.state})")
        if rec.staging_id and (rec.staging_step or 1) > 1:
            before = [r for r in self.staging_steps(rec.staging_id)
                      if (r.staging_step or 0) < (rec.staging_step or 0)]
            if any(r.state != S.SUCCEEDED.value for r in before):
                raise ConflictError(
                    f"Step {rec.staging_step} of a staging plan runs only after the steps "
                    "before it have succeeded (the base file must be on the device first)")
        if rec.kind == "firmware" and not rec.dry_run:
            now = datetime.now(UTC)
            start, end = _utc(rec.window_start), _utc(rec.window_end)
            if start is None or end is None or not start <= now <= end:
                raise ConflictError(
                    f"Outside the approved maintenance window ({start} - {end} UTC)")
            img = self.s.get(FirmwareImage, rec.firmware_image_id)
            if img is None or img.status != "approved":
                raise ConflictError("Firmware image is no longer approved")
        for t in rec.targets:  # settings may have changed since the plan was created
            device = self.s.get(Device, t.device_id)
            assert device is not None
            problem = self._policy_problem(device, rec.dry_run, firmware=rec.kind == "firmware")
            if problem:
                raise ForbiddenError(problem)
            if t.config_version_id and not rec.dry_run:
                cfg = self.s.get(ConfigVersion, t.config_version_id)
                if cfg is not None:
                    self._check_file_can_be_applied(device, cfg, ApplyMode(rec.apply_mode))
        return rec

    def execute(self, deployment_id: str, actor: str,
                stop: StopSignal | None = None) -> DeploymentRecord:
        rec = self.check_can_execute(deployment_id)
        dep = self._to_domain(rec)
        if stop is not None:
            dep.stop = stop
        if not rec.dry_run:
            by_id = {t.device_id: t for t in dep.targets}
            for tr in rec.targets:
                device = self.s.get(Device, tr.device_id)
                assert device is not None
                if tr.secret_refs:
                    by_id[tr.device_id].secret_values = self._secret_values(
                        device, dict(tr.secret_refs))
                if tr.credential_after_ref_id:
                    by_id[tr.device_id].credentials_after = self._credentials_for(
                        device, tr.credential_after_ref_id)
                    if device.credential_ref_id:
                        by_id[tr.device_id].credentials_before = self._credentials_for(
                            device, device.credential_ref_id)
        mode = ApplyMode(rec.apply_mode)
        needs_files = not rec.dry_run and any(
            not t.driver.info.simulated and t.driver.needs_file_server(rec.kind, mode)
            for t in dep.targets)
        with ExitStack() as stack:
            if needs_files:
                if self.transfer_hub is None:
                    raise ConflictError("No file transfer service is configured")
                try:
                    files = stack.enter_context(self.transfer_hub.session())
                except TftpServerError as e:
                    raise ConflictError(str(e)) from e
                for target in dep.targets:
                    target.driver.file_server = files
            audit.record(self.s, actor, "deployment.execute.start", "deployment", rec.id,
                         details={"dry_run": rec.dry_run, "tftp": needs_files})
            self._lock_devices(rec)  # commits
            self._run_locked(rec, dep, actor)
        return rec

    def record_run_error(self, deployment_id: str, actor: str, reason: str) -> None:
        """A run started in the background raised instead of ending normally."""
        rec = self.get(deployment_id)
        started = rec.state != S.READY.value
        message = (f"the run ended with an internal error: {reason}" if started
                   else f"could not start: {reason}")
        rec.events.append(DeploymentEventRecord(
            seq=len(rec.events), timestamp=datetime.now(UTC), stage="execute",
            status="error", message=message,
        ))
        audit.record(self.s, actor, "deployment.execute.error", "deployment", rec.id,
                     "failed", {"reason": reason, "started": started})
        self.s.commit()

    def request_stop(self, deployment_id: str, actor: str, jobs: DeploymentJobs
                     ) -> DeploymentRecord:
        """Stop button: a running run stops at its next safe point; a run that no longer
        exists (e.g. the application was restarted) is resolved at once."""
        rec = self.get(deployment_id)
        if jobs.request_stop(deployment_id, actor):
            audit.record(self.s, actor, "deployment.stop_requested", "deployment", rec.id,
                         details={"state": rec.state})
            return rec
        return self.stop_without_run(deployment_id, actor)

    def stop_without_run(self, deployment_id: str, actor: str) -> DeploymentRecord:
        """Resolve a deployment shown as running although no run exists in this process."""
        rec = self.get(deployment_id)
        previous = S(rec.state)
        outcome = interrupted_outcome(previous)
        if outcome is None:
            raise ConflictError(f"This deployment is not running (state {rec.state})")
        resolve_interrupted(self.s, rec, f"stopped by {actor}: no run was active for it in "
                            f"this application while it was {previous.value}")
        audit.record(self.s, actor, "deployment.stop", "deployment", rec.id, rec.state,
                     {"previous_state": previous.value, "run_active": False})
        return rec

    def _run_locked(self, rec: DeploymentRecord, dep: Deployment, actor: str) -> None:
        try:
            self._orchestrator(rec, commit_each_step=True).execute(dep)
        finally:
            self._sync(rec, dep)
            self._record_backups_and_status(rec, dep, actor)
            self._unlock_devices(rec)
            audit.record(self.s, actor, "deployment.execute", "deployment", rec.id, rec.state,
                         {"dry_run": rec.dry_run})
            self.s.commit()

    # -- plans that need attention (D-088) ---------------------------------------------
    def attention(self, records: list[DeploymentRecord]) -> dict[str, str | None]:
        """For each plan that needs attention: None while it waits for a person, else why
        it no longer does: 'checked' (a person recorded a check) or 'superseded:<id>' (a
        later, real, successful plan covered all of its devices, so they were checked
        again). The plan's own state is never changed."""
        pending = [r for r in records if r.state == S.RECOVERY_REQUIRED.value]
        if not pending:
            return {}
        later = list(self.s.scalars(
            select(DeploymentRecord).where(
                DeploymentRecord.project_id.in_({r.project_id for r in pending}),
                DeploymentRecord.state == S.SUCCEEDED.value,
                DeploymentRecord.dry_run.is_(False))
            .order_by(DeploymentRecord.created_at)))
        out: dict[str, str | None] = {}
        for r in pending:
            if any(e.status == "checked" for e in r.events):
                out[r.id] = "checked"
                continue
            devices = {t.device_id for t in r.targets}
            since = _utc(r.created_at)
            assert since is not None
            hit = next((x for x in later if (_utc(x.created_at) or since) > since
                        and devices <= {t.device_id for t in x.targets}), None)
            out[r.id] = f"superseded:{hit.id}" if hit else None
        return out

    def delete(self, deployment_id: str, actor: str, jobs: DeploymentJobs) -> list[str]:
        """Remove a plan that is not running, with its targets and events (D-088). A step
        of a staging plan takes the whole staging plan with it, so the order of the steps
        cannot be bypassed. The audit trail keeps what the plan was."""
        rec = self.get(deployment_id)
        recs = self.staging_steps(rec.staging_id) if rec.staging_id else [rec]
        for r in recs:
            locked = self.s.scalars(select(Device.name).where(
                Device.locked_by_deployment_id == r.id)).first()
            if (DeploymentState(r.state) in TRANSIENT_STATES or jobs.is_running(r.id)
                    or locked):
                raise ConflictError("This plan is running: stop it, wait for it to end, "
                                    "then delete it")
        ids = [r.id for r in recs]
        for r in recs:
            audit.record(self.s, actor, "deployment.delete", "deployment", r.id, details={
                "kind": r.kind, "state": r.state, "dry_run": r.dry_run,
                "devices": [x.device_id for x in r.targets], "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                **({"staging_id": r.staging_id, "staging_step": r.staging_step}
                   if r.staging_id else {})})
            self.s.delete(r)
        return ids

    def mark_checked(self, deployment_id: str, actor: str, note: str) -> DeploymentRecord:
        """A person checked the device(s) of a plan that needs attention (D-088)."""
        rec = self.get(deployment_id)
        if rec.state != S.RECOVERY_REQUIRED.value:
            raise ConflictError("Only a plan that needs attention can be marked as checked")
        note = " ".join(note.split())
        if len(note) < 5:
            raise ConflictError("Say in a few words what you checked on the device")
        rec.events.append(DeploymentEventRecord(
            seq=len(rec.events), timestamp=datetime.now(UTC), stage="recover",
            status="checked", message=f"device checked by {actor}: {note}"))
        audit.record(self.s, actor, "deployment.checked", "deployment", rec.id,
                     details={"note": note})
        return rec

    def cancel(self, deployment_id: str, actor: str) -> DeploymentRecord:
        rec = self.get(deployment_id)
        if rec.state not in {S.DRAFT.value, S.AWAITING_APPROVAL.value, S.READY.value}:
            raise ConflictError(f"Cannot cancel a deployment in state {rec.state}")
        rec.state = S.CANCELLED.value
        rec.events.append(DeploymentEventRecord(
            seq=len(rec.events), timestamp=datetime.now(UTC), stage="lifecycle",
            status=S.CANCELLED.value, message=f"cancelled by {actor}",
        ))
        audit.record(self.s, actor, "deployment.cancel", "deployment", rec.id)
        return rec

    def _record_backups_and_status(
        self, rec: DeploymentRecord, dep: Deployment, actor: str
    ) -> None:
        now = datetime.now(UTC)
        by_device = {t.device_id: t for t in dep.targets}
        for tr in rec.targets:
            t = by_device[tr.device_id]
            if t.backup is not None and tr.backup_version_id is None:
                v = ConfigVersion(
                    device_id=t.device_id, kind="backup", text=t.backup.text,
                    sha256=hashlib.sha256(t.backup.text.encode()).hexdigest(),
                    reference=t.backup.reference, created_by=actor,
                )
                self.s.add(v)
                self.s.flush()
                tr.backup_version_id = v.id
            if t.after_config is not None and tr.after_version_id is None \
                    and not rec.dry_run:
                # Read back from the device after the change: review it, or compare it with
                # the configuration that was sent.
                v = ConfigVersion(
                    device_id=t.device_id, kind="backup", text=t.after_config,
                    sha256=hashlib.sha256(t.after_config.encode()).hexdigest(),
                    reference=f"after deployment {rec.id[:8]}", created_by=actor,
                )
                self.s.add(v)
                self.s.flush()
                tr.after_version_id = v.id
            device = self.s.get(Device, t.device_id)
            assert device is not None
            if t.state not in _NOT_CONNECTED:
                device.last_connection_at = now
            if rec.dry_run:
                continue
            reached = t.driver.target.management_address
            if rec.kind == "free_address":
                if t.state is TargetState.VERIFIED:
                    # Off the network until its next power-on; nothing was saved on it.
                    m = re.fullmatch(r"port (\S+) off", str(t.target_version or ""))
                    port = m.group(1) if m else ""
                    set_port_off(device, port or "?")
                    audit.record(self.s, actor, "device.management_port_off", "device",
                                 device.id, details={"port": port, "deployment": rec.id,
                                                     "address": device.management_address})
                if t.backup is not None:
                    device.last_backup_at = now
                continue
            if port_off(device) and t.state is TargetState.VERIFIED:
                # It answers again (it was switched off and on).
                set_port_off(device, None)
                audit.record(self.s, actor, "device.management_port_on", "device",
                             device.id, details={"deployment": rec.id})
            if (reached != device.management_address
                    and t.state in (TargetState.VERIFIED, TargetState.VERIFY_FAILED)):
                # The loaded file moved the device to another address, and it was reached
                # there after its restart (identity checked): keep UNDM pointing at it.
                audit.record(self.s, actor, "device.address_changed", "device", device.id,
                             details={"from": device.management_address, "to": reached,
                                      "deployment": rec.id})
                device.management_address = reached
            if t.password_set:
                # UNDM answered a demanded password change with the device's own login.
                audit.record(self.s, actor, "device.password_set", "device", device.id,
                             details={"credential": device.credential_ref_id,
                                      "reason": "the device demanded a new password after "
                                                "loading", "deployment": rec.id})
            after = tr.credential_after_ref_id
            if (after and after != device.credential_ref_id and not t.kept_previous_login
                    and t.state in (TargetState.VERIFIED, TargetState.VERIFY_FAILED)):
                # The device was reached with the login chosen for after loading: keep it.
                audit.record(self.s, actor, "device.credential_changed", "device", device.id,
                             details={"from": device.credential_ref_id,
                                      "to": after, "deployment": rec.id})
                device.credential_ref_id = after
                set_login_after_loading_needed(device, False)
            if t.backup is not None:
                device.last_backup_at = now
            if rec.kind in ("first_login", "restart", "license"):
                continue  # no configuration was deployed
            if rec.kind == "firmware":
                if t.current_version:  # observed, not declared
                    device.observed_facts = {**(device.observed_facts or {}),
                                             "os_version": t.current_version}
                    device.facts_retrieved_at = now
                continue
            if t.state in (TargetState.VERIFIED, TargetState.NO_CHANGE):
                device.deployment_status = DeviceDeploymentStatus.IN_SYNC.value
                device.last_deployment_at = now
                self._name_after_hostname(rec, tr, t, device, actor)
            elif t.state is TargetState.ROLLED_BACK:
                device.deployment_status = DeviceDeploymentStatus.DEPLOYMENT_FAILED.value
            elif t.touched:
                device.deployment_status = DeviceDeploymentStatus.UNKNOWN.value


    def _name_after_hostname(self, rec: DeploymentRecord, tr: DeploymentTargetRecord,
                             t: DeploymentTarget, device: Device, actor: str) -> None:
        """A device whose supplied file was loaded and verified takes the hostname it now
        reports (D-094), in case it differs from the one its file named."""
        if t.state is not TargetState.VERIFIED:
            return
        cfg = self.s.get(ConfigVersion, tr.config_version_id) if tr.config_version_id else None
        if cfg is None or cfg.kind != "imported":
            return  # generated from the device's own settings: its name is already chosen
        self._rename(device, t.observed_hostname, actor, rec.id, "read from the device")

    def _name_from_file(self, device: Device, cfg: ConfigVersion, actor: str,
                        rec: DeploymentRecord) -> None:
        """A device named after the hostname in the file a plan will load on it (D-094,
        product owner 2026-11-25): the placeholder name gives way as soon as the file is
        chosen, before any connection."""
        if cfg.kind != "imported":
            return
        report = inspect_config(self.s, cfg, self.registry)
        name = (report.facts.get("hostname") if report else None) \
            or fortinet_hostname(cfg.text)
        self._rename(device, name, actor, rec.id, "the file to load")

    def _rename(self, device: Device, hostname: str | None, actor: str, plan_id: str,
                source: str) -> None:
        new = (hostname or "").strip().strip('"')[:120]
        if not new or new == device.name:
            return
        generic = {v.lower() for v in (device.model, device.product_family) if v}
        if any(new.lower().startswith(g) for g in generic):
            return  # a factory hostname is the model, not a name
        taken = self.s.scalar(select(Device.id).where(
            Device.project_id == device.project_id, Device.name == new, Device.id != device.id))
        if taken:
            audit.record(self.s, actor, "device.rename_skipped", "device", device.id,
                         details={"hostname": new, "deployment": plan_id,
                                  "reason": "another device of this system has that name"})
            return
        audit.record(self.s, actor, "device.renamed", "device", device.id,
                     details={"from": device.name, "to": new, "deployment": plan_id,
                              "source": source})
        device.name = new


def resolve_interrupted(session: Session, rec: DeploymentRecord, why: str) -> None:
    """End a deployment whose run is gone: devices may have been changed."""
    previous = S(rec.state)
    outcome = interrupted_outcome(previous)
    assert outcome is not None
    rec.state = outcome.value
    rec.events.append(DeploymentEventRecord(
        seq=len(rec.events), timestamp=datetime.now(UTC), stage="lifecycle",
        status=outcome.value,
        message=f"{why}; device state must be verified before further changes",
    ))
    if outcome is S.RECOVERY_REQUIRED:
        for tr in rec.targets:
            device = session.get(Device, tr.device_id)
            if device is not None:
                device.deployment_status = DeviceDeploymentStatus.UNKNOWN.value
    session.execute(
        update(Device).where(Device.locked_by_deployment_id == rec.id)
        .values(locked_by_deployment_id=None)
    )


def recover_interrupted_deployments(session: Session) -> list[str]:
    """Resolve deployments left in a transient state by a stopped process.

    Devices may have been changed, so the deployment becomes RECOVERY_REQUIRED
    (or FAILED if no device could have been changed), the device lock is
    released and affected devices are marked UNKNOWN until verified.
    """
    resolved = []
    stuck = session.scalars(
        select(DeploymentRecord).where(
            DeploymentRecord.state.in_([s.value for s in TRANSIENT_STATES])
        )
    ).all()
    for rec in stuck:
        previous = S(rec.state)
        resolve_interrupted(session, rec, f"application stopped while deployment was "
                            f"{previous.value}")
        audit.record(session, "system", "deployment.interrupted", "deployment", rec.id,
                     rec.state, {"previous_state": previous.value})
        resolved.append(rec.id)
    session.commit()
    return resolved
