from dataclasses import asdict

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from undm.api.deps import ActorDep, SessionDep
from undm.api.schemas import (
    CertificateSetting,
    CredentialRefIn,
    CredentialRefOut,
    CredentialSecretIn,
    LoginDefaults,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    SharedLoginGroupOut,
    SharedLoginsResultOut,
    ShareLoginsIn,
)
from undm.db.models import CredentialRef, Device, Project
from undm.security import credentials as creds
from undm.services import app_settings, audit, shared_logins
from undm.services.errors import ConflictError, NotFoundError, ServiceError

router = APIRouter(prefix="/api/projects", tags=["projects"])
credentials_router = APIRouter(prefix="/api/credential-refs", tags=["credentials"])
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


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
    changes = body.model_dump(mode="json", exclude_unset=True)
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
    # The system's logins go with it, so their passwords leave the credential store too.
    removed, kept = 0, []
    for ref in p.credential_refs:
        if ref.provider != "keyring":
            continue
        try:
            creds.delete_secret(ref.provider, ref.locator)
            removed += 1
        except creds.CredentialStoreError:
            kept.append(ref.name)
    session.delete(p)
    audit.record(session, actor, "project.delete", "project", project_id,
                 details={"name": p.name, "stored_logins_removed": removed,
                          "stored_logins_not_removed": kept})


def _ref_out(ref: CredentialRef) -> CredentialRefOut:
    out = CredentialRefOut.model_validate(ref)
    out.shared = ref.project_id is None
    out.has_secret = creds.has_secret(ref.provider, ref.locator)
    out.empty_password = (creds.has_empty_password(ref.provider, ref.locator)
                          if out.has_secret else None)
    return out


@router.get("/{project_id}/credential-refs", response_model=list[CredentialRefOut])
def list_credential_refs(project_id: str, session: SessionDep) -> list[CredentialRefOut]:
    """The system's own logins, then the logins for all systems (D-105)."""
    own = list(get_project(session, project_id).credential_refs)
    return [_ref_out(r) for r in own + app_settings.shared_logins(session)]


@router.post("/{project_id}/credential-refs", response_model=CredentialRefOut,
             status_code=status.HTTP_201_CREATED)
def create_credential_ref(
    project_id: str, body: CredentialRefIn, session: SessionDep, actor: ActorDep
) -> CredentialRefOut:
    get_project(session, project_id)
    return _create_ref(session, actor, body, project_id)


def _create_ref(session: SessionDep, actor: str, body: CredentialRefIn,
                project_id: str | None) -> CredentialRefOut:
    if body.provider == "env" and not body.locator:
        raise ServiceError("The 'env' provider needs a locator (environment variable stem)")
    if project_id is None and any(r.name == body.name
                                  for r in app_settings.shared_logins(session)):
        raise ConflictError(f"A login for all systems is already called '{body.name}'")
    ref = CredentialRef(project_id=project_id, name=body.name, provider=body.provider,
                        locator=body.locator or "pending")
    session.add(ref)
    try:
        session.flush()
    except IntegrityError as e:
        raise ConflictError("Credential reference name already in use") from e
    if body.provider == "keyring":
        ref.locator = f"credential/{ref.id}"
    audit.record(session, actor, "credential_ref.create", "credential_ref", ref.id,
                 details={"name": ref.name, "provider": ref.provider,
                          "shared": project_id is None})
    return _ref_out(ref)


@credentials_router.get("", response_model=list[CredentialRefOut])
def list_shared_logins(session: SessionDep) -> list[CredentialRefOut]:
    """Logins for all systems (D-105)."""
    return [_ref_out(r) for r in app_settings.shared_logins(session)]


@credentials_router.post("", response_model=CredentialRefOut,
                         status_code=status.HTTP_201_CREATED)
def create_shared_login(body: CredentialRefIn, session: SessionDep,
                        actor: ActorDep) -> CredentialRefOut:
    return _create_ref(session, actor, body, None)


@credentials_router.get("/from-systems", response_model=list[SharedLoginGroupOut])
def preview_share_all(session: SessionDep) -> list[SharedLoginGroupOut]:
    """What bringing the systems' own logins in would do, with suggested names (D-115).
    Changes nothing."""
    return [SharedLoginGroupOut.model_validate(asdict(g)) for g in shared_logins.plan(session)]


@credentials_router.post("/from-systems", response_model=SharedLoginsResultOut)
def share_all(body: ShareLoginsIn, session: SessionDep, actor: ActorDep) -> SharedLoginsResultOut:
    """Make every system's own login a login for all systems (D-115)."""
    groups, replaced = shared_logins.share_all(session, actor, body.names)
    return SharedLoginsResultOut(logins=[SharedLoginGroupOut.model_validate(asdict(g))
                                         for g in groups], replaced=replaced)


def _get_ref(session: SessionDep, ref_id: str) -> CredentialRef:
    ref = session.get(CredentialRef, ref_id)
    if ref is None:
        raise NotFoundError("Credential reference not found")
    return ref


@credentials_router.put("/{ref_id}/secret", response_model=CredentialRefOut)
def set_credential_secret(
    ref_id: str, body: CredentialSecretIn, session: SessionDep, actor: ActorDep
) -> CredentialRefOut:
    """Store username/password in the OS credential store. The secret is never returned."""
    ref = _get_ref(session, ref_id)
    try:
        creds.store_secret(ref.provider, ref.locator, body.username, body.password)
    except creds.CredentialStoreError as e:
        raise ServiceError(str(e)) from e
    audit.record(session, actor, "credential.secret.set", "credential_ref", ref.id,
                 details={"name": ref.name, "username": body.username})
    return _ref_out(ref)


@credentials_router.delete("/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential_ref(ref_id: str, session: SessionDep, actor: ActorDep) -> None:
    ref = _get_ref(session, ref_id)
    try:
        creds.delete_secret(ref.provider, ref.locator)
    except creds.CredentialStoreError as e:
        raise ServiceError(str(e)) from e
    for device in session.scalars(select(Device).where(Device.credential_ref_id == ref.id)):
        device.credential_ref_id = None
    session.delete(ref)
    audit.record(session, actor, "credential_ref.delete", "credential_ref", ref_id,
                 details={"name": ref.name})


@settings_router.get("/defaults", response_model=LoginDefaults)
def get_defaults(session: SessionDep) -> LoginDefaults:
    return LoginDefaults.model_validate(app_settings.defaults(session))


@settings_router.put("/defaults", response_model=LoginDefaults)
def put_defaults(body: LoginDefaults, session: SessionDep, actor: ActorDep) -> LoginDefaults:
    return LoginDefaults.model_validate(
        app_settings.set_defaults(session, actor, body.model_dump()))


@settings_router.get("/certificate", response_model=CertificateSetting)
def get_certificate(session: SessionDep) -> CertificateSetting:
    return CertificateSetting.model_validate({"subject": app_settings.certificate(session)})


@settings_router.put("/certificate", response_model=CertificateSetting)
def put_certificate(body: CertificateSetting, session: SessionDep,
                    actor: ActorDep) -> CertificateSetting:
    subject = body.subject.model_dump() if body.subject is not None else None
    app_settings.set_certificate(session, actor, subject)
    return CertificateSetting.model_validate({"subject": subject})
