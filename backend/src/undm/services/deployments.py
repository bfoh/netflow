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
from undm.services import audit
from undm.services.devices import build_driver, latest_config
from undm.services.errors import ConflictError, ForbiddenError, NotFoundError

S = DeploymentState
# Target states reached without a successful connection during execution.
_NOT_CONNECTED = frozenset({TargetState.PENDING, TargetState.PREVIEWED,
                            TargetState.PREVIEW_FAILED, TargetState.PREFLIGHT_FAILED})


class DeploymentService:
    def __init__(
        self, session: Session, registry: DriverRegistry, *,
        require_separate_approver: bool, allow_production_deployments: bool = False,
    ) -> None:
        self.s = session
        self.registry = registry
        self.require_separate_approver = require_separate_approver
        self.allow_production_deployments = allow_production_deployments

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

        return DeploymentOrchestrator(
            sink=sink, require_separate_approver=self.require_separate_approver
        )

    def _to_domain(self, rec: DeploymentRecord) -> Deployment:
        targets = []
        for t in rec.targets:
            device = self.s.get(Device, t.device_id)
            cfg = self.s.get(ConfigVersion, t.config_version_id)
            assert device is not None and cfg is not None
            serial = (device.observed_facts or {}).get("serial_number")
            dt = DeploymentTarget(device.id, device.name, build_driver(device, self.registry),
                                  cfg.text, expected_serial=serial)
            dt.state = TargetState(t.state)
            targets.append(dt)
        return Deployment(
            deployment_id=rec.id, targets=targets, created_by=rec.created_by,
            apply_mode=ApplyMode(rec.apply_mode), dry_run=rec.dry_run,
            state=S(rec.state), approved_by=rec.approved_by, approved_at=rec.approved_at,
        )

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
            if (device.environment == DeviceEnvironment.PRODUCTION.value
                    and not self.allow_production_deployments):
                raise ForbiddenError(
                    f"{device.name} is a production device; production deployments are "
                    "disabled by policy"
                )
            cfg = latest_config(self.s, did, "generated")
            if cfg is None:
                raise ConflictError(f"{device.name}: generate a configuration first")
            rec.targets.append(DeploymentTargetRecord(
                device_id=did, position=pos, config_version_id=cfg.id,
                state=TargetState.PENDING.value,
            ))
        self.s.flush()
        dep = self._to_domain(rec)
        self._orchestrator(rec).prepare(dep)
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.create", "deployment", rec.id, rec.state,
                     {"devices": device_ids, "dry_run": dry_run, "apply_mode": apply_mode.value})
        return rec

    def approve(self, deployment_id: str, actor: str) -> DeploymentRecord:
        rec = self.get(deployment_id)
        if rec.state != S.AWAITING_APPROVAL.value:
            raise ConflictError(f"Deployment is not awaiting approval (state {rec.state})")
        dep = self._to_domain(rec)
        try:
            self._orchestrator(rec).approve(dep, actor)
        except ApprovalRequiredError as e:
            raise ForbiddenError(str(e)) from e
        self._sync(rec, dep)
        audit.record(self.s, actor, "deployment.approve", "deployment", rec.id)
        return rec

    def execute(self, deployment_id: str, actor: str) -> DeploymentRecord:
        rec = self.get(deployment_id)
        if rec.state != S.READY.value:
            raise ConflictError(f"Deployment must be ready to execute (state {rec.state})")
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
