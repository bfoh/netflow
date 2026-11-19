from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select

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
from undm.services.policy import Policy

router = APIRouter(tags=["deployments"])


def _svc(session: SessionDep, registry: RegistryDep, settings: SettingsDep,
         request: Request) -> DeploymentService:
    return DeploymentService(
        session, registry, Policy.from_settings(settings),
        firmware_reboot_wait=(settings.firmware_reboot_wait_attempts,
                              settings.firmware_reboot_wait_seconds),
        firmware_separate_approver=settings.firmware_require_separate_approver,
        transfer_hub=request.app.state.transfer_hub,
    )


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
        project_id, body.device_ids, body.image_id, actor, dry_run=body.dry_run)


@router.post("/api/deployments/{deployment_id}/execute", response_model=DeploymentOut)
def execute(deployment_id: str, svc: ServiceDep, actor: ActorDep) -> DeploymentRecord:
    return svc.execute(deployment_id, actor)


@router.post("/api/deployments/{deployment_id}/cancel", response_model=DeploymentOut)
def cancel(deployment_id: str, svc: ServiceDep, actor: ActorDep) -> DeploymentRecord:
    return svc.cancel(deployment_id, actor)
