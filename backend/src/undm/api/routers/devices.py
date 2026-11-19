from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.routers.projects import get_project
from undm.api.schemas import (
    ConfigDiffOut,
    ConfigFileReportOut,
    ConfigImportIn,
    ConfigVersionFull,
    ConfigVersionOut,
    DeviceIn,
    DeviceOut,
    DevicePatch,
    DiagnosticsOut,
    GenerateOut,
    IntentIn,
    IssueOut,
    OperationOut,
)
from undm.configgen.diff import diff_configs
from undm.db.models import ConfigVersion, CredentialRef, Device
from undm.domain.enums import DeviceEnvironment
from undm.domain.operations import DeviceOperation
from undm.drivers.registry import DriverRegistry
from undm.inventory.rules import environment_problem
from undm.services import audit
from undm.services import devices as svc
from undm.services.errors import ConflictError, NotFoundError, ServiceError
from undm.services.policy import Policy

router = APIRouter(tags=["devices"])


def to_out(device: Device, registry: RegistryDep) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    if device.driver_id in registry:
        out.capabilities = sorted(c.value for c in registry.get(device.driver_id).capabilities())
    return out


def get_device(session: SessionDep, device_id: str) -> Device:
    d = session.get(Device, device_id)
    if d is None:
        raise NotFoundError("Device not found")
    return d


def _check_refs(session: SessionDep, registry: RegistryDep, project_id: str,
                values: dict[str, Any], current: Device | None = None) -> None:
    if "driver_id" in values and values["driver_id"] not in registry:
        raise ServiceError(f"Unknown driver {values['driver_id']!r}")
    driver_id = values.get("driver_id") or (current.driver_id if current else None)
    environment = values.get("environment") or (
        current.environment if current else DeviceEnvironment.SIMULATED.value)
    if driver_id:
        problem = environment_problem(driver_id, str(environment), registry)
        if problem:
            raise ServiceError(problem)
    ref_id = values.get("credential_ref_id")
    if ref_id:
        ref = session.get(CredentialRef, ref_id)
        if ref is None or ref.project_id != project_id:
            raise ServiceError("Credential reference not found in this project")


@router.get("/api/projects/{project_id}/devices", response_model=list[DeviceOut])
def list_devices(project_id: str, session: SessionDep, registry: RegistryDep) -> list[DeviceOut]:
    get_project(session, project_id)
    return [to_out(d, registry) for d in session.scalars(
        select(Device).where(Device.project_id == project_id).order_by(Device.name))]


@router.get("/api/devices", response_model=list[DeviceOut])
def list_all_devices(session: SessionDep, registry: RegistryDep) -> list[DeviceOut]:
    return [to_out(d, registry) for d in session.scalars(select(Device).order_by(Device.name))]


@router.post("/api/projects/{project_id}/devices", response_model=DeviceOut,
             status_code=status.HTTP_201_CREATED)
def create_device(project_id: str, body: DeviceIn, session: SessionDep,
                  registry: RegistryDep, actor: ActorDep) -> DeviceOut:
    get_project(session, project_id)
    values = {k: v for k, v in body.model_dump(mode="json").items() if v is not None}
    _check_refs(session, registry, project_id, values)
    d = Device(project_id=project_id, **values)
    session.add(d)
    try:
        session.flush()
    except IntegrityError as e:
        raise ConflictError(f"A device named {body.name!r} already exists in this project") from e
    audit.record(session, actor, "device.create", "device", d.id,
                 details={"name": d.name, "driver_id": d.driver_id})
    return to_out(d, registry)


@router.get("/api/devices/{device_id}", response_model=DeviceOut)
def read_device(device_id: str, session: SessionDep, registry: RegistryDep) -> DeviceOut:
    return to_out(get_device(session, device_id), registry)


@router.patch("/api/devices/{device_id}", response_model=DeviceOut)
def update_device(device_id: str, body: DevicePatch, session: SessionDep,
                  registry: RegistryDep, actor: ActorDep) -> DeviceOut:
    d = get_device(session, device_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    if d.locked_by_deployment_id:
        raise ConflictError("Device is locked by a running deployment")
    _check_refs(session, registry, d.project_id, changes, d)
    for k, v in changes.items():
        setattr(d, k, v)
    try:
        session.flush()
    except IntegrityError as e:
        raise ConflictError("Device name already in use in this project") from e
    audit.record(session, actor, "device.update", "device", d.id, details=changes)
    return to_out(d, registry)


@router.delete("/api/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: str, session: SessionDep, actor: ActorDep) -> None:
    d = get_device(session, device_id)
    if d.locked_by_deployment_id:
        raise ConflictError("Device is locked by a running deployment")
    session.delete(d)
    audit.record(session, actor, "device.delete", "device", device_id, details={"name": d.name})


@router.put("/api/devices/{device_id}/intent", response_model=DeviceOut)
def set_intent(device_id: str, body: IntentIn, session: SessionDep, registry: RegistryDep,
               actor: ActorDep) -> DeviceOut:
    d = get_device(session, device_id)
    d.intent = body.model_dump(mode="json")
    audit.record(session, actor, "device.intent.set", "device", d.id)
    return to_out(d, registry)


@router.post("/api/devices/{device_id}/configs/generate", response_model=GenerateOut)
def generate_config(device_id: str, session: SessionDep, registry: RegistryDep,
                    actor: ActorDep) -> GenerateOut:
    d = get_device(session, device_id)
    result, version = svc.generate_config(session, d, registry, actor)
    return GenerateOut(
        ok=result.ok,
        issues=[IssueOut(severity=i.severity.value, code=i.code, message=i.message, path=i.path)
                for i in result.issues],
        version=ConfigVersionFull.model_validate(version) if version else None,
    )


@router.post("/api/devices/{device_id}/configs/import", response_model=ConfigVersionFull,
             status_code=status.HTTP_201_CREATED)
def import_config(device_id: str, body: ConfigImportIn, session: SessionDep,
                  registry: RegistryDep, actor: ActorDep) -> ConfigVersionFull:
    d = get_device(session, device_id)
    version = svc.import_config(session, d, registry, actor, body.filename, body.text)
    return _full(session, version, registry)


def _full(session: Session, version: ConfigVersion,
          registry: DriverRegistry) -> ConfigVersionFull:
    out = ConfigVersionFull.model_validate(version)
    report = svc.inspect_config(session, version, registry)
    if report is not None:
        out.inspection = ConfigFileReportOut.model_validate(report)
    return out


@router.get("/api/devices/{device_id}/configs", response_model=list[ConfigVersionOut])
def list_configs(device_id: str, session: SessionDep) -> list[ConfigVersion]:
    get_device(session, device_id)
    return list(session.scalars(
        select(ConfigVersion).where(ConfigVersion.device_id == device_id)
        .order_by(ConfigVersion.created_at.desc())))


@router.get("/api/configs/diff", response_model=ConfigDiffOut)
def diff_versions(from_version: str, to_version: str, session: SessionDep) -> ConfigDiffOut:
    a, b = session.get(ConfigVersion, from_version), session.get(ConfigVersion, to_version)
    if a is None or b is None:
        raise NotFoundError("Configuration version not found")
    if a.device_id != b.device_id:
        raise ServiceError("Both versions must belong to the same device")
    d = diff_configs(a.text, b.text, label=f"{a.kind}")
    return ConfigDiffOut(from_version_id=a.id, to_version_id=b.id, unified=d.unified,
                         added=d.added, removed=d.removed, changed=d.changed)


@router.get("/api/configs/{version_id}", response_model=ConfigVersionFull)
def read_config(version_id: str, session: SessionDep,
                registry: RegistryDep) -> ConfigVersionFull:
    v = session.get(ConfigVersion, version_id)
    if v is None:
        raise NotFoundError("Configuration version not found")
    return _full(session, v, registry)


@router.get("/api/devices/{device_id}/diagnostics", response_model=DiagnosticsOut)
def diagnostics(device_id: str, session: SessionDep, registry: RegistryDep,
                actor: ActorDep) -> DiagnosticsOut:
    """Sanitized report of the last retrieved device information. Does not contact the device."""
    d = get_device(session, device_id)
    return DiagnosticsOut(text=svc.sanitized_diagnostics(session, d, registry, actor))


@router.post("/api/devices/{device_id}/operations/{operation}", response_model=OperationOut)
def run_operation(device_id: str, operation: DeviceOperation, session: SessionDep,
                  registry: RegistryDep, settings: SettingsDep,
                  actor: ActorDep) -> dict[str, Any]:
    d = get_device(session, device_id)
    return svc.run_read_only_operation(session, d, operation, registry, actor,
                                       Policy.from_settings(settings))
