"""Settings for all systems (D-105): default logins per device role and the HTTPS
certificate answers. Kept in the database (``app_settings``), so they travel with it.

Logins shared by all systems are ``CredentialRef`` rows without a system
(``project_id`` is None). A system may use its own logins and the shared ones.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import TypeIs  # pydantic's dependency

from undm.db.models import AppSetting, CredentialRef, Project
from undm.services import audit
from undm.services.errors import ServiceError

DEFAULTS = "defaults"
CERTIFICATE = "certificate"

# Which default logins exist, per device kind (the wizard's roles; both 2930F share one).
DEFAULT_FIELDS: dict[str, tuple[str, ...]] = {
    "firewall": ("login", "login_after", "tunnel_key"),
    "blackbox": ("login", "login_after"),
    "aruba": ("login", "current"),
    # Added in v94 (D-124); values stored before read back with it empty.
    "modem": ("login",),
}


def get(session: Session, key: str) -> dict[str, Any] | None:
    row = session.get(AppSetting, key)
    return dict(row.value) if row is not None and row.value is not None else None


def put(session: Session, key: str, value: dict[str, Any] | None) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    session.flush()


def shared_logins(session: Session) -> list[CredentialRef]:
    return list(session.scalars(select(CredentialRef).where(CredentialRef.project_id.is_(None))
                                .order_by(CredentialRef.name)))


def usable_by(ref: CredentialRef | None, project_id: str) -> TypeIs[CredentialRef]:
    """A login a system's device may use: its own system's, or a shared one."""
    return ref is not None and ref.project_id in (None, project_id)


def defaults(session: Session) -> dict[str, dict[str, str | None]]:
    stored = get(session, DEFAULTS) or {}
    shared = {r.id for r in shared_logins(session)}
    out: dict[str, dict[str, str | None]] = {}
    for kind, fields in DEFAULT_FIELDS.items():
        given = stored.get(kind) or {}
        # A deleted login is no longer a default.
        out[kind] = {f: (given.get(f) if given.get(f) in shared else None) for f in fields}
    return out


def set_defaults(session: Session, actor: str,
                 value: dict[str, dict[str, str | None]]) -> dict[str, dict[str, str | None]]:
    shared = {r.id: r.name for r in shared_logins(session)}
    clean: dict[str, dict[str, str | None]] = {}
    for kind, fields in DEFAULT_FIELDS.items():
        given = value.get(kind) or {}
        unknown = set(given) - set(fields)
        if unknown:
            raise ServiceError(f"Unknown default for {kind}: {', '.join(sorted(unknown))}")
        clean[kind] = {}
        for f in fields:
            ref_id = given.get(f)
            if ref_id is not None and ref_id not in shared:
                raise ServiceError("A default must be one of the logins for all systems")
            clean[kind][f] = ref_id
    unknown_kinds = set(value) - set(DEFAULT_FIELDS)
    if unknown_kinds:
        raise ServiceError(f"Unknown device kind: {', '.join(sorted(unknown_kinds))}")
    put(session, DEFAULTS, clean)
    audit.record(session, actor, "settings.defaults", "settings", DEFAULTS, details={
        kind: {f: shared.get(v) if v else None for f, v in fields.items()}
        for kind, fields in clean.items()})
    return clean


def certificate(session: Session) -> dict[str, Any] | None:
    return get(session, CERTIFICATE)


def set_certificate(session: Session, actor: str, subject: dict[str, Any] | None) -> None:
    put(session, CERTIFICATE, subject)
    audit.record(session, actor, "settings.certificate", "settings", CERTIFICATE,
                 details={"set": subject is not None})


def effective_certificate(session: Session, project: Project | None) -> dict[str, Any] | None:
    """The system's own answers, else the answers for all systems."""
    if project is not None and project.certificate_subject:
        return dict(project.certificate_subject)
    return certificate(session)
