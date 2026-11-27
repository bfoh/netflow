"""What management services a device offers (D-130): read-only, audited, kept on the device.

``discover`` reads, without a login, which documented management ports answer and what
each presents by itself. ``netconf_hello`` logs in once with a login a person chooses and
reads the NETCONF <hello>; it runs only after a reading in which NETCONF answered. Both
are kept with the device's observed facts (``extra.services``, ``extra.netconf_hello``),
apart from what a person entered.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from undm.db.models import CredentialRef, Device
from undm.drivers.base import Capability, DeviceDriver
from undm.drivers.registry import DriverRegistry
from undm.security import credentials as creds
from undm.services import app_settings, audit
from undm.services import devices as devsvc
from undm.services.errors import ConflictError, ForbiddenError, NotFoundError
from undm.services.policy import Policy

NETCONF_PORT = 830


def _extra(device: Device) -> dict[str, Any]:
    extra = (device.observed_facts or {}).get("extra") or {}
    return dict(extra) if isinstance(extra, dict) else {}


def _keep(device: Device, key: str, value: dict[str, Any]) -> None:
    facts = dict(device.observed_facts or {})
    extra = _extra(device)
    extra[key] = value
    facts["extra"] = extra
    device.observed_facts = facts


def last(device: Device) -> dict[str, Any]:
    """The last readings kept on the device (empty when there are none)."""
    extra = _extra(device)
    return {k: extra[k] for k in ("services", "netconf_hello") if isinstance(extra.get(k), dict)}


def _driver(device: Device, registry: DriverRegistry, policy: Policy | None) -> DeviceDriver:
    if device.driver_id not in registry:
        raise ConflictError(f"Unknown driver {device.driver_id!r}")
    info = registry.get(device.driver_id).info
    if Capability.SERVICE_DISCOVERY not in info.capabilities:
        raise ConflictError(f"UNDM reads no management services for {device.name}'s model")
    problem = (policy or Policy()).read_problem(device.name, device.environment, info.simulated)
    if problem:
        raise ForbiddenError(problem)
    return devsvc.build_driver(device, registry)


def discover(session: Session, device: Device, registry: DriverRegistry, actor: str,
             policy: Policy | None = None) -> dict[str, Any]:
    driver = _driver(device, registry, policy)
    result = driver.discover_services()
    if not result.ok:
        audit.record(session, actor, "device.discover_services", "device", device.id,
                     result.status.value, {"message": result.message})
        raise ConflictError(result.message)
    reading = {**dict(result.data), "at": datetime.now(UTC).isoformat(),
               "message": result.message}
    _keep(device, "services", reading)
    audit.record(session, actor, "device.discover_services", "device", device.id, "success", {
        "address": reading.get("address"), "simulated": reading.get("simulated"),
        "open": [p["port"] for p in reading.get("ports", []) if p.get("open")]})
    return reading


def netconf_hello(session: Session, device: Device, registry: DriverRegistry, actor: str,
                  credential_ref_id: str, policy: Policy | None = None) -> dict[str, Any]:
    services = last(device).get("services") or {}
    netconf = next((p for p in services.get("ports", []) if p.get("port") == NETCONF_PORT), None)
    if not netconf or not netconf.get("open"):
        raise ConflictError("Read its management services first: NETCONF (port 830) must "
                            "answer before UNDM logs in to it")
    ref = session.get(CredentialRef, credential_ref_id)
    if ref is None:
        raise NotFoundError("Login not found")
    if not app_settings.usable_by(ref, device.project_id):
        raise ConflictError("That login belongs to another system")
    driver = _driver(device, registry, policy)
    try:
        credentials = creds.resolve(ref.provider, ref.locator)
    except creds.CredentialResolutionError as e:
        raise ConflictError(str(e)) from e
    result = driver.netconf_hello(credentials)
    now = datetime.now(UTC).isoformat()
    if not result.ok:
        audit.record(session, actor, "device.netconf_hello", "device", device.id,
                     result.status.value, {"login": ref.name, "message": result.message})
        _keep(device, "netconf_hello", {"ok": False, "at": now, "login": ref.name,
                                        "message": result.message})
        return {"ok": False, "at": now, "login": ref.name, "message": result.message}
    data = dict(result.data)
    reading = {**data, "ok": True, "at": now, "login": ref.name, "message": result.message}
    _keep(device, "netconf_hello", reading)
    audit.record(session, actor, "device.netconf_hello", "device", device.id, "success", {
        "login": ref.name, "simulated": data.get("simulated"),
        "capabilities": len(data.get("capabilities", [])),
        "modules": [m.get("name") for m in data.get("modules", [])]})
    return reading
