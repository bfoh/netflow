"""Device use cases: driver access, read-only operations, config generation."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.configgen.engine import GenerationResult, generate
from undm.db.models import ConfigVersion, Device
from undm.domain.intent import DeviceIntent
from undm.domain.operations import DeviceOperation, is_impacting
from undm.drivers.base import Credentials, DeviceDriver, DeviceTarget
from undm.drivers.registry import DriverRegistry
from undm.security import credentials as creds
from undm.services import audit
from undm.services.errors import ConflictError, ForbiddenError, ServiceError

READ_ONLY_OPERATIONS = frozenset(
    {
        DeviceOperation.CHECK_REACHABILITY,
        DeviceOperation.GET_FACTS,
        DeviceOperation.BACKUP_CONFIGURATION,
        DeviceOperation.GET_FIRMWARE_INFORMATION,
    }
)


def build_driver(device: Device, registry: DriverRegistry) -> DeviceDriver:
    if device.driver_id not in registry:
        raise ServiceError(f"Unknown driver {device.driver_id!r}")
    if not device.management_address:
        raise ServiceError(f"Device {device.name} has no management address")
    credentials: Credentials | None = None
    driver_cls = registry.get(device.driver_id)
    if device.credential_ref is not None:
        try:
            credentials = creds.resolve(device.credential_ref.provider,
                                        device.credential_ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(str(e)) from e
    elif not driver_cls.info.simulated:
        raise ServiceError(f"Device {device.name} has no credential reference")
    target = DeviceTarget(device.id, device.management_address, device.management_port)
    return registry.create(device.driver_id, target, credentials)


def latest_config(session: Session, device_id: str, kind: str) -> ConfigVersion | None:
    return session.scalars(
        select(ConfigVersion)
        .where(ConfigVersion.device_id == device_id, ConfigVersion.kind == kind)
        .order_by(ConfigVersion.created_at.desc())
        .limit(1)
    ).first()


def generate_config(
    session: Session, device: Device, registry: DriverRegistry, actor: str
) -> tuple[GenerationResult, ConfigVersion | None]:
    if device.intent is None:
        raise ConflictError("Device has no configuration intent")
    intent = DeviceIntent.model_validate(device.intent)
    platform = registry.get(device.driver_id).info.platform
    result = generate(intent, platform)
    version = None
    if result.ok:
        assert result.text is not None and result.sha256 is not None
        version = ConfigVersion(
            device_id=device.id, kind="generated", text=result.text, sha256=result.sha256,
            platform=platform, template_version=result.template_version,
            verification=result.verification.value, created_by=actor,
        )
        session.add(version)
        session.flush()
    audit.record(
        session, actor, "config.generate", "device", device.id,
        "success" if result.ok else "rejected",
        {"platform": platform, "issues": [asdict(i) for i in result.issues]},
    )
    return result, version


def run_read_only_operation(
    session: Session, device: Device, op: DeviceOperation, registry: DriverRegistry, actor: str
) -> dict[str, Any]:
    if is_impacting(op) or op not in READ_ONLY_OPERATIONS:
        raise ForbiddenError(
            f"{op.value} changes device state; it is only available through an approved "
            "deployment workflow"
        )
    driver = build_driver(device, registry)
    now = datetime.now(UTC)
    try:
        conn = driver.connect()
        if not conn.ok:
            audit.record(session, actor, f"device.{op.value}", "device", device.id, "failed",
                         {"message": conn.message})
            return {"status": conn.status.value, "message": conn.message}
        device.last_connection_at = now
        if op is DeviceOperation.CHECK_REACHABILITY:
            result = conn
            payload: Any = None
        elif op is DeviceOperation.GET_FACTS:
            result = driver.get_device_facts()
            payload = asdict(result.data) if result.ok else None
            if result.ok:
                device.observed_facts = payload
                device.facts_retrieved_at = now
        elif op is DeviceOperation.BACKUP_CONFIGURATION:
            result = driver.backup_configuration()
            payload = None
            if result.ok:
                backup = result.data
                v = ConfigVersion(
                    device_id=device.id, kind="backup", text=backup.text,
                    sha256=hashlib.sha256(backup.text.encode()).hexdigest(),
                    reference=backup.reference, created_by=actor,
                )
                session.add(v)
                session.flush()
                device.last_backup_at = now
                payload = {"config_version_id": v.id, "reference": backup.reference}
        else:
            result = driver.get_firmware_information()
            payload = result.data
    finally:
        driver.disconnect()
    audit.record(session, actor, f"device.{op.value}", "device", device.id,
                 result.status.value, {"message": result.message})
    return {"status": result.status.value, "message": result.message, "data": payload}
