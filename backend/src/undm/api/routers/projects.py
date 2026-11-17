from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from undm.api.deps import ActorDep, SessionDep
from undm.api.schemas import (
    CredentialRefIn,
    CredentialRefOut,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from undm.db.models import CredentialRef, Project
from undm.services import audit
from undm.services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_project(session: SessionDep, project_id: str) -> Project:
    p = session.get(Project, project_id)
    if p is None:
        raise NotFoundError("Project not found")
    return p


@router.get("", response_model=list[ProjectOut])
def list_projects(session: SessionDep) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.name)))


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, session: SessionDep, actor: ActorDep) -> Project:
    p = Project(**body.model_dump())
    session.add(p)
    try:
        session.flush()
    except IntegrityError as e:
        raise ConflictError(f"A project named {body.name!r} already exists") from e
    audit.record(session, actor, "project.create", "project", p.id, details={"name": p.name})
    return p


@router.get("/{project_id}", response_model=ProjectOut)
def read_project(project_id: str, session: SessionDep) -> Project:
    return get_project(session, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str, body: ProjectPatch, session: SessionDep, actor: ActorDep
) -> Project:
    p = get_project(session, project_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    try:
        session.flush()
    except IntegrityError as e:
        raise ConflictError("Project name already in use") from e
    audit.record(session, actor, "project.update", "project", p.id, details=changes)
    return p


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, session: SessionDep, actor: ActorDep) -> None:
    p = get_project(session, project_id)
    session.delete(p)
    audit.record(session, actor, "project.delete", "project", project_id,
                 details={"name": p.name})


@router.get("/{project_id}/credential-refs", response_model=list[CredentialRefOut])
def list_credential_refs(project_id: str, session: SessionDep) -> list[CredentialRef]:
    return get_project(session, project_id).credential_refs


@router.post("/{project_id}/credential-refs", response_model=CredentialRefOut,
             status_code=status.HTTP_201_CREATED)
def create_credential_ref(
    project_id: str, body: CredentialRefIn, session: SessionDep, actor: ActorDep
) -> CredentialRef:
    get_project(session, project_id)
    ref = CredentialRef(project_id=project_id, **body.model_dump())
    session.add(ref)
    try:
        session.flush()
    except IntegrityError as e:
        raise ConflictError("Credential reference name already in use") from e
    audit.record(session, actor, "credential_ref.create", "credential_ref", ref.id,
                 details={"name": ref.name, "provider": ref.provider})
    return ref
