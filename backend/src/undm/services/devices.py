"""Device use cases: driver access, read-only operations, config generation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.configgen.engine import GenerationResult, UnknownPlatformError, generate
from undm.db.models import ConfigVersion, Device
from undm.domain.intent import DeviceIntent
from undm.domain.operations import DeviceOperation, is_impacting
from undm.drivers.base import ConfigFileReport, Credentials, DeviceDriver, DeviceTarget
from undm.drivers.registry import DriverRegistry
from undm.security import credentials as creds
from undm.services import audit
from undm.services.errors import ConflictError, ForbiddenError, ServiceError
from undm.services.policy import Policy

READ_ONLY_OPERATIONS = frozenset(
    {
        DeviceOperation.CHECK_REACHABILITY,
        DeviceOperation.GET_FACTS,
        DeviceOperation.BACKUP_CONFIGURATION,
        DeviceOperation.GET_FIRMWARE_INFORMATION,
    }
)


def temporary_address(device: Device) -> str | None:
    """The address the device runs at until its next restart, if UNDM moved it aside (D-096)."""
    extra = (device.observed_facts or {}).get("extra") or {}
    value = extra.get("temporary_address") if isinstance(extra, dict) else None
    return str(value) if value else None


def set_temporary_address(device: Device, address: str | None) -> None:
    facts = dict(device.observed_facts or {})
    extra = dict(facts.get("extra") or {})
    if address:
        extra["temporary_address"] = address
    else:
        extra.pop("temporary_address", None)
    facts["extra"] = extra
    device.observed_facts = facts


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
        raise ServiceError(
            f"{device.name} has no login chosen. Choose one on its device page (Edit), or in "
            "Stage a system, step 1 ('Its login'). Logins are added on the system page's "
            "Logins tab.")
    target = DeviceTarget(device.id, temporary_address(device) or device.management_address,
                          device.management_port)
    return registry.create(device.driver_id, target, credentials)


def latest_config(session: Session, device_id: str, kind: str) -> ConfigVersion | None:
    return session.scalars(
        select(ConfigVersion)
        .where(ConfigVersion.device_id == device_id, ConfigVersion.kind == kind)
        .order_by(ConfigVersion.created_at.desc())
        .limit(1)
    ).first()


MAX_IMPORT_BYTES = 2 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def import_config(
    session: Session, device: Device, registry: DriverRegistry, actor: str,
    filename: str, text: str,
) -> ConfigVersion:
    """Store a user-supplied configuration file as an immutable, unvalidated version.

    The text is normalised (BOM removed, CRLF -> LF) but otherwise kept exactly as
    supplied. It is NOT checked against intent; it is deployed as-is if selected.
    """
    if len(text.encode()) > MAX_IMPORT_BYTES:
        raise ServiceError(f"Configuration file is larger than {MAX_IMPORT_BYTES // 1024} KiB")
    if "\x00" in text:
        raise ServiceError("File looks binary; import a plain-text configuration file")
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ServiceError("Configuration file is empty")
    if not text.endswith("\n"):
        text += "\n"
    safe_name = _SAFE_NAME.sub("_", filename.strip())[:120] or "imported.cfg"
    platform = registry.get(device.driver_id).info.platform if device.driver_id in registry else ""
    version = ConfigVersion(
        device_id=device.id, kind="imported", text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(), platform=platform,
        verification="user_supplied_not_validated", reference=safe_name, created_by=actor,
    )
    session.add(version)
    session.flush()
    report = inspect_config(session, version, registry)
    audit.record(session, actor, "config.import", "device", device.id, details={
        "filename": safe_name, "bytes": len(text.encode()), "lines": text.count("\n"),
        "sha256": version.sha256, "file_type": report.file_type if report else "",
    })
    return version


def inspect_config(session: Session, version: ConfigVersion,
                   registry: DriverRegistry) -> ConfigFileReport | None:
    """What an imported file is, according to the device's driver (offline)."""
    if version.kind != "imported":
        return None
    device = session.get(Device, version.device_id)
    if device is None or device.driver_id not in registry:
        return None
    return registry.get(device.driver_id).inspect_config_file(version.text)


def generate_config(
    session: Session, device: Device, registry: DriverRegistry, actor: str
) -> tuple[GenerationResult, ConfigVersion | None]:
    if device.intent is None:
        raise ConflictError("Device has no configuration intent")
    intent = DeviceIntent.model_validate(device.intent)
    platform = registry.get(device.driver_id).info.platform
    try:
        result = generate(intent, platform)
    except UnknownPlatformError:
        raise ConflictError(
            f"No configuration template exists for {platform}; import a configuration "
            "file for this device instead") from None
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
    session: Session, device: Device, op: DeviceOperation, registry: DriverRegistry, actor: str,
    policy: Policy | None = None,
) -> dict[str, Any]:
    if is_impacting(op) or op not in READ_ONLY_OPERATIONS:
        raise ForbiddenError(
            f"{op.value} changes device state; it is only available through an approved "
            "deployment workflow"
        )
    if device.driver_id in registry:
        problem = (policy or Policy()).read_problem(
            device.name, device.environment, registry.get(device.driver_id).info.simulated)
        if problem:
            raise ForbiddenError(problem)
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
                moved = temporary_address(device)
                device.observed_facts = payload
                if moved:  # where it runs until its next restart is not a fact it reports
                    set_temporary_address(device, moved)
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


def sanitized_diagnostics(session: Session, device: Device, registry: DriverRegistry,
                          actor: str) -> str:
    """Shareable report of what UNDM last read from the device (no device contact)."""
    from datetime import UTC, datetime

    from undm.security.sanitize import new_mapper, sanitize

    facts = dict(device.observed_facts or {})
    extra = dict(facts.pop("extra", {}) or {})
    raw = dict(extra.pop("raw_output", {}) or {})
    known = [("hostname", device.name), ("hostname", str(facts.get("hostname") or "")),
             ("serial", str(facts.get("serial_number") or "")),
             ("ip", device.management_address)]
    mapper = new_mapper()

    def s(text: object) -> str:
        return sanitize(str(text), known, mapper)

    driver = registry.get(device.driver_id).info if device.driver_id in registry else None
    lines = [
        "UNDM sanitized diagnostics",
        f"generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"driver: {device.driver_id}"
        + (f" ({driver.maturity.value}, {driver.os_family})" if driver else ""),
        f"environment: {device.environment}",
        f"declared: {device.manufacturer} {device.model} / {device.os_family}",
        f"facts retrieved: {device.facts_retrieved_at or 'never'}",
        "",
        "== parsed facts ==",
        *[f"{k}: {s(v)}" for k, v in facts.items()],
        *[f"{k}: {s(v)}" for k, v in extra.items()],
    ]
    for command, output in raw.items():
        lines += ["", f"== raw output: {command} ==", s(output).rstrip()]
    if not raw:
        lines += ["", "(no raw command output stored: run 'Retrieve information' first)"]
    lines += ["", "Masking is automatic and best effort. Review before sharing."]
    audit.record(session, actor, "device.diagnostics.export", "device", device.id)
    return "\n".join(lines) + "\n"
