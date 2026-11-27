"""Ping and traceroute for troubleshooting after staging (D-128)."""

from typing import Any

from fastapi import APIRouter

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.routers.projects import get_project
from undm.api.schemas import CheckAllIn, TroubleshootIn
from undm.services import troubleshoot as svc
from undm.services.policy import Policy

router = APIRouter(prefix="/api/projects/{project_id}/troubleshoot", tags=["troubleshoot"])


@router.post("/ping")
def ping(project_id: str, body: TroubleshootIn, session: SessionDep, registry: RegistryDep,
         settings: SettingsDep, actor: ActorDep) -> dict[str, Any]:
    """Ping one address from this PC or a device of the system. Audited."""
    return svc.ping(session, get_project(session, project_id), registry, actor,
                    source=body.source, target=body.target, count=body.count,
                    policy=Policy.from_settings(settings))


@router.post("/traceroute")
def traceroute(project_id: str, body: TroubleshootIn, session: SessionDep,
               registry: RegistryDep, settings: SettingsDep, actor: ActorDep) -> dict[str, Any]:
    """The hops to one address from this PC or a device of the system. Audited."""
    return svc.traceroute(session, get_project(session, project_id), registry, actor,
                          source=body.source, target=body.target,
                          policy=Policy.from_settings(settings))


@router.post("/check-all")
def check_all(project_id: str, body: CheckAllIn, session: SessionDep, registry: RegistryDep,
              settings: SettingsDep, actor: ActorDep) -> list[dict[str, Any]]:
    """Every device of the system at the address UNDM uses: two echoes and its management
    port. Only the system's own addresses. Audited."""
    return svc.check_all(session, get_project(session, project_id), registry, actor,
                         source=body.source, policy=Policy.from_settings(settings))
