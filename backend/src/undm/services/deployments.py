"""Deployment use cases.

Each request rebuilds the orchestrator view from the database. During
execution every lifecycle step is committed as it happens, so a process that
dies mid-deployment leaves a transient state behind that
:func:`recover_interrupted_deployments` resolves on the next start.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from undm.db.models import (
    ConfigVersion,
    DeploymentEventRecord,
    DeploymentRecord,
    DeploymentTargetRecord,
    Device,
    FirmwareImage,
)
from undm.domain.enums import DeviceDeploymentStatus, DeviceEnvironment
from undm.domain.lifecycle import (
    TRANSIENT_STATES,
    DeploymentState,
    interrupted_outcome,
)
from undm.drivers.base import ApplyMode
from undm.drivers.registry import DriverRegistry
from undm.orchestration.deployment import (
    ApprovalRequiredError,
    Deployment,
    DeploymentEvent,
    DeploymentOrchestrator,
    DeploymentTarget,
    TargetState,
)
from undm.orchestration.firmware import FirmwareOrchestrator
from undm.services import audit
from undm.services.devices import build_driver, latest_config
from undm.services.errors import ConflictError, ForbiddenError, NotFoundError
from undm.services.firmware import FirmwareRepository, device_compatibility
from undm.services.policy import Policy

S = DeploymentState


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
                 *, firmware_reboot_wait: tuple[int, float] = (30, 20.0)) -> None:
        self.s = session
        self.registry = registry
        self.policy = policy
        self.require_separate_approver = policy.require_separate_approver
        self.firmware_reboot_wait = firmware_reboot_wait

    def _policy_problem(self, device: Device, dry_run: bool) -> str | None:
        simulated = self.registry.get(device.driver_id).info.simulated
        if dry_run:
            return self.policy.read_problem(device.name, device.environment, simulated)
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
            return FirmwareOrchestrator(sink=sink, reboot_wait_attempts=attempts,
                                        reboot_wait_delay_s=delay)
        return DeploymentOrchestrator(
            sink=sink, require_separate_approver=self.require_separate_approver
        )

    def _to_domain(self, rec: DeploymentRecord) -> Deployment:
        targets = []
        for t in rec.targets:
            device = self.s.get(Device, t.device_id)
            assert device is not None
            text = ""
            if t.config_version_id:
                cfg = self.s.get(ConfigVersion, t.config_version_id)
                assert cfg is not None
                text = cfg.text
            serial = (device.observed_facts or {}).get("serial_number")
            dt = DeploymentTarget(device.id, device.name, build_driver(device, self.registry),
                                  text, expected_serial=serial)
            dt.state = TargetState(t.state)
            dt.from_version, dt.target_version = t.from_version, t.to_version
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
    ) -> DeploymentRecord:
        if not device_ids:
            raise ConflictError("Select at least one device")
        if len(set(device_ids)) != len(device_ids):
            raise ConflictError("A device is selected more than once")
        rec = DeploymentRecord(
            project_id=project_id, state=S.DRAFT.value, dry_run=dry_run,
            apply_mode=apply_mode.value, created_by=actor,
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
            rec.targets.append(DeploymentTargetRecord(
                device_id=did, position=pos, config_version_id=cfg.id,
                state=TargetState.PENDING.value,
            ))
        unknown = set(config_versions or {}) - set(device_ids)
        if unknown:
            raise ConflictError("Configuration chosen for a device that is not in the plan")
        self.s.flush()
        dep = self._to_domain(rec)
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": device_ids, "dry_run": dry_run, "apply_mode": apply_mode.value,
                      "config_versions": {t.device_id: t.config_version_id for t in rec.targets}})
        return rec

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
        *, dry_run: bool,
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
            created_by=actor,
        )
        self.s.add(rec)
        problems: dict[str, list[str]] = {}
        for pos, did in enumerate(device_ids):
            device = self.s.get(Device, did)
            if device is None or device.project_id != project_id:
                raise NotFoundError(f"Device {did} not found in project")
            problem = self._policy_problem(device, dry_run)
            if problem:
                raise ForbiddenError(problem)
            issues = device_compatibility(img, device, self.registry)
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
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "firmware_deployment.create", "deployment", rec.id,
                     rec.state, {"devices": device_ids, "image": img.id, "version": img.version,
                                 "dry_run": dry_run})
        return rec

    def execute(self, deployment_id: str, actor: str) -> DeploymentRecord:
        rec = self.get(deployment_id)
        if rec.state != S.READY.value:
            raise ConflictError(f"Deployment must be ready to execute (state {rec.state})")
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
            problem = self._policy_problem(device, rec.dry_run)
            if problem:
                raise ForbiddenError(problem)
        dep = self._to_domain(rec)
        audit.record(self.s, actor, "deployment.execute.start", "deployment", rec.id,
                     details={"dry_run": rec.dry_run})
        self._lock_devices(rec)  # commits
        try:
            self._orchestrator(rec, commit_each_step=True).execute(dep)
        finally:
            self._sync(rec, dep)
            self._record_backups_and_status(rec, dep, actor)
            self._unlock_devices(rec)
            audit.record(self.s, actor, "deployment.execute", "deployment", rec.id, rec.state,
                         {"dry_run": rec.dry_run})
            self.s.commit()
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
            device = self.s.get(Device, t.device_id)
            assert device is not None
            if t.state not in _NOT_CONNECTED:
                device.last_connection_at = now
            if rec.dry_run:
                continue
            if t.backup is not None:
                device.last_backup_at = now
            if rec.kind == "firmware":
                if t.current_version:  # observed, not declared
                    device.observed_facts = {**(device.observed_facts or {}),
                                             "os_version": t.current_version}
                    device.facts_retrieved_at = now
                continue
            if t.state in (TargetState.VERIFIED, TargetState.NO_CHANGE):
                device.deployment_status = DeviceDeploymentStatus.IN_SYNC.value
                device.last_deployment_at = now
            elif t.state is TargetState.ROLLED_BACK:
                device.deployment_status = DeviceDeploymentStatus.DEPLOYMENT_FAILED.value
            elif t.touched:
                device.deployment_status = DeviceDeploymentStatus.UNKNOWN.value


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
        outcome = interrupted_outcome(previous)
        assert outcome is not None
        rec.state = outcome.value
        rec.events.append(DeploymentEventRecord(
            seq=len(rec.events), timestamp=datetime.now(UTC), stage="lifecycle",
            status=outcome.value,
            message=f"application stopped while deployment was {previous.value}; "
                    "device state must be verified before further changes",
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
        audit.record(session, "system", "deployment.interrupted", "deployment", rec.id,
                     outcome.value, {"previous_state": previous.value})
        resolved.append(rec.id)
    session.commit()
    return resolved
