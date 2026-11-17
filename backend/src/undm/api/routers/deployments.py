from fastapi import APIRouter, Query, status
from sqlalchemy import select

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.routers.projects import get_project
from undm.api.schemas import DeploymentIn, DeploymentOut, DeploymentSummary
from undm.db.models import DeploymentRecord
from undm.services.deployments import DeploymentService

router = APIRouter(tags=["deployments"])


def _svc(session: SessionDep, registry: RegistryDep, settings: SettingsDep) -> DeploymentService:
    return DeploymentService(
        session, registry,
        require_separate_approver=settings.require_separate_approver,
        allow_production_deployments=settings.allow_production_deployments,
    )


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
                      registry: RegistryDep, settings: SettingsDep,
                      actor: ActorDep) -> DeploymentRecord:
    get_project(session, project_id)
    return _svc(session, registry, settings).create(
        project_id, body.device_ids, actor, dry_run=body.dry_run, apply_mode=body.apply_mode)


@router.get("/api/deployments/{deployment_id}", response_model=DeploymentOut)
def read_deployment(deployment_id: str, session: SessionDep, registry: RegistryDep,
                    settings: SettingsDep) -> DeploymentRecord:
    return _svc(session, registry, settings).get(deployment_id)


@router.post("/api/deployments/{deployment_id}/approve", response_model=DeploymentOut)
def approve(deployment_id: str, session: SessionDep, registry: RegistryDep,
            settings: SettingsDep, actor: ActorDep) -> DeploymentRecord:
    return _svc(session, registry, settings).approve(deployment_id, actor)


@router.post("/api/deployments/{deployment_id}/execute", response_model=DeploymentOut)
def execute(deployment_id: str, session: SessionDep, registry: RegistryDep,
            settings: SettingsDep, actor: ActorDep) -> DeploymentRecord:
    return _svc(session, registry, settings).execute(deployment_id, actor)


@router.post("/api/deployments/{deployment_id}/cancel", response_model=DeploymentOut)
def cancel(deployment_id: str, session: SessionDep, registry: RegistryDep,
           settings: SettingsDep, actor: ActorDep) -> DeploymentRecord:
    return _svc(session, registry, settings).cancel(deployment_id, actor)
