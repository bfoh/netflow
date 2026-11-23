import logging
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.routers.projects import get_project
from undm.api.schemas import (
    ApproveIn,
    DeploymentIn,
    DeploymentOut,
    DeploymentSummary,
    FirmwareDeploymentIn,
)
from undm.db.models import DeploymentRecord
from undm.services.deployments import DeploymentService
from undm.services.errors import ConflictError
from undm.services.jobs import DeploymentJobs
from undm.services.policy import Policy

router = APIRouter(tags=["deployments"])
log = logging.getLogger("undm")


def build_service(session: Session, state: Any) -> DeploymentService:
    settings = state.settings
    return DeploymentService(
        session, state.registry, Policy.from_settings(settings),
        firmware_reboot_wait=(settings.firmware_reboot_wait_attempts,
                              settings.firmware_reboot_wait_seconds),
        firmware_separate_approver=settings.firmware_require_separate_approver,
        transfer_hub=state.transfer_hub,
    )


def _svc(session: SessionDep, registry: RegistryDep, settings: SettingsDep,
         request: Request) -> DeploymentService:
    return build_service(session, request.app.state)


ServiceDep = Annotated[DeploymentService, Depends(_svc)]


@router.get("/api/deployments", response_model=list[DeploymentSummary])
def list_all_deployments(session: SessionDep, limit: int = Query(50, ge=1, le=500),
                         state: str | None = None) -> list[DeploymentRecord]:
    q = select(DeploymentRecord).order_by(DeploymentRecord.created_at.desc()).limit(limit)
    if state:
        q = q.where(DeploymentRecord.state == state)
    return list(session.scalars(q))


@router.get("/api/projects/{project_id}/deployments", response_model=list[DeploymentSummary])
def list_deployments(project_id: str, session: SessionDep) -> list[DeploymentRecord]:
    get_project(session, project_id)
    return list(session.scalars(
        select(DeploymentRecord).where(DeploymentRecord.project_id == project_id)
        .order_by(DeploymentRecord.created_at.desc())))


@router.post("/api/projects/{project_id}/deployments", response_model=DeploymentOut,
             status_code=status.HTTP_201_CREATED)
def create_deployment(project_id: str, body: DeploymentIn, session: SessionDep,
                      svc: ServiceDep, actor: ActorDep) -> DeploymentRecord:
    get_project(session, project_id)
    return svc.create(
        project_id, body.device_ids, actor, dry_run=body.dry_run, apply_mode=body.apply_mode,
        config_versions=body.config_versions, secrets=body.secrets,
        credentials_after=body.credentials_after)


@router.get("/api/deployments/{deployment_id}", response_model=DeploymentOut)
def read_deployment(deployment_id: str, svc: ServiceDep) -> DeploymentRecord:
    return svc.get(deployment_id)


@router.post("/api/deployments/{deployment_id}/approve", response_model=DeploymentOut)
def approve(deployment_id: str, svc: ServiceDep, actor: ActorDep,
            body: ApproveIn | None = None) -> DeploymentRecord:
    body = body or ApproveIn()
    return svc.approve(
        deployment_id, actor, body.window_start, body.window_end)


@router.post("/api/projects/{project_id}/firmware-upgrades", response_model=DeploymentOut,
             status_code=status.HTTP_201_CREATED, tags=["firmware"])
def create_firmware_deployment(project_id: str, body: FirmwareDeploymentIn,
                               session: SessionDep, svc: ServiceDep,
                               actor: ActorDep) -> DeploymentRecord:
    get_project(session, project_id)
    return svc.create_firmware(
        project_id, body.device_ids, body.image_id, actor, dry_run=body.dry_run,
        allow_downgrade=body.allow_downgrade, also_secondary=body.also_secondary)


def _run_in_background(state: Any, deployment_id: str, actor: str, signal: Any) -> None:
    jobs: DeploymentJobs = state.deployment_jobs
    try:
        with state.session_factory() as session:
            svc = build_service(session, state)
            try:
                svc.execute(deployment_id, actor, stop=signal)
            except Exception as e:  # noqa: BLE001 - recorded on the plan, not lost in a thread
                log.exception("background deployment run failed",
                              extra={"ctx": {"deployment": deployment_id}})
                session.rollback()
                svc.record_run_error(deployment_id, actor, str(e) or type(e).__name__)
    finally:
        jobs.release(deployment_id)


@router.post("/api/deployments/{deployment_id}/execute", response_model=DeploymentOut)
def execute(deployment_id: str, svc: ServiceDep, actor: ActorDep, request: Request,
            background: Annotated[bool, Query()] = False) -> DeploymentRecord:
    """Run an approved plan. ``background=true`` returns at once and the run continues on
    the server (the page follows its events); otherwise the call returns when it ends."""
    jobs: DeploymentJobs = request.app.state.deployment_jobs
    signal = jobs.claim(deployment_id)
    if signal is None:
        raise ConflictError("This deployment is already running")
    if not background:
        try:
            return svc.execute(deployment_id, actor, stop=signal)
        finally:
            jobs.release(deployment_id)
    try:
        rec = svc.check_can_execute(deployment_id)
    except Exception:
        jobs.release(deployment_id)
        raise
    threading.Thread(target=_run_in_background, name=f"deployment-{deployment_id[:8]}",
                     args=(request.app.state, deployment_id, actor, signal),
                     daemon=True).start()
    return rec


@router.post("/api/deployments/{deployment_id}/stop", response_model=DeploymentOut)
def stop(deployment_id: str, svc: ServiceDep, actor: ActorDep,
         request: Request) -> DeploymentRecord:
    """Stop a running deployment at its next safe point (see StopSignal)."""
    return svc.request_stop(deployment_id, actor, request.app.state.deployment_jobs)


@router.post("/api/deployments/{deployment_id}/cancel", response_model=DeploymentOut)
def cancel(deployment_id: str, svc: ServiceDep, actor: ActorDep) -> DeploymentRecord:
    return svc.cancel(deployment_id, actor)
