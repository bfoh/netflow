"""Audit trail recording. Details are redacted before storage."""

from typing import Any

from sqlalchemy.orm import Session

from undm.db.models import AuditEvent
from undm.security.redaction import redact


def record(
    session: Session, actor: str, action: str, target_type: str, target_id: str,
    outcome: str = "success", details: dict[str, Any] | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        actor=actor, action=action, target_type=target_type, target_id=target_id,
        outcome=outcome, details=redact(details or {}),
    )
    session.add(ev)
    return ev
