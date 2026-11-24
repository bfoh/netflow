import logging
from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from undm import __version__
from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.schemas import AuditOut, DeviceModelOut, DriverOut, PolicyChange, PolicyOut
from undm.config import Settings
from undm.db.models import AuditEvent
from undm.inventory.catalog import CATALOG
from undm.services import audit
from undm.services import safety_settings as safety
from undm.services.errors import ConflictError
from undm.services.policy import Policy

router = APIRouter(tags=["system"])
log = logging.getLogger("undm")


@router.get("/api/health")
def health(request: Request) -> dict[str, str | None]:
    problem = getattr(request.app.state, "database_problem", None)
    return {"status": "database_upgrade_needed" if problem else "ok", "version": __version__,
            "problem": problem}


@router.get("/api/drivers", response_model=list[DriverOut])
def list_drivers(registry: RegistryDep) -> list[DriverOut]:
    return [
        DriverOut(driver_id=i.driver_id, vendor=i.vendor, platform=i.platform,
                  os_family=i.os_family, description=i.description, simulated=i.simulated,
                  capabilities=sorted(c.value for c in i.capabilities),
                  maturity=i.maturity.value, transport=i.transport, notes=list(i.notes))
        for i in registry.list()
    ]


def _policy_out(settings: Settings) -> PolicyOut:
    return PolicyOut(**asdict(Policy.from_settings(settings)),
                     firmware_require_separate_approver=settings.firmware_require_separate_approver,
                     locked=sorted(safety.locked(settings)))


@router.get("/api/policy", response_model=PolicyOut)
def policy(settings: SettingsDep) -> PolicyOut:
    """The safety switches in force now (start-up settings, then Settings → Safety)."""
    return _policy_out(settings)


@router.put("/api/policy", response_model=PolicyOut)
def change_policy(body: PolicyChange, request: Request, session: SessionDep,
                  actor: ActorDep) -> PolicyOut:
    """Change safety switches from Settings → Safety. Every change is audited (D-082)."""
    base: Settings = request.app.state.settings
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        done = safety.change(base, changes)
    except safety.SafetySettingsError as e:
        raise ConflictError(str(e)) from e
    for name, (before, after) in done.items():
        audit.record(session, actor, "policy.change", "policy", name,
                     details={"switch": name, "meaning": safety.SWITCHES[name],
                              "before": before, "after": after})
    if done:
        log.warning("safety switch changed", extra={"ctx": {
            "actor": actor, "changes": {k: v[1] for k, v in done.items()}}})
    return _policy_out(safety.effective(base))


@router.get("/api/device-models", response_model=list[DeviceModelOut])
def list_device_models() -> list[DeviceModelOut]:
    return [
        DeviceModelOut(model_id=m.model_id, manufacturer=m.manufacturer,
                       product_family=m.product_family, model=m.model, category=m.category.value,
                       os_family=m.os_family, drivers=list(m.drivers), support=m.support.value,
                       notes=m.notes)
        for m in CATALOG
    ]


@router.get("/api/audit", response_model=list[AuditOut])
def list_audit(session: SessionDep, limit: int = Query(100, ge=1, le=1000),
               target_id: str | None = None) -> list[AuditEvent]:
    q = select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit)
    if target_id:
        q = q.where(AuditEvent.target_id == target_id)
    return list(session.scalars(q))
