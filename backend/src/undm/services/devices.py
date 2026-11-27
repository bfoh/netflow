"""Device use cases: driver access, read-only operations, config generation."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from undm.configgen.engine import GenerationResult, UnknownPlatformError, generate
from undm.db.models import AuditEvent, ConfigVersion, Device
from undm.domain.intent import DeviceIntent
from undm.domain.operations import DeviceOperation, is_impacting
from undm.drivers.base import (
    Capability,
    ConfigFileReport,
    Credentials,
    DeviceDriver,
    DeviceTarget,
)
from undm.drivers.registry import DriverRegistry
from undm.provisioning.console import port_lock
from undm.security import credentials as creds
from undm.services import audit, reach
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


def port_off(device: Device) -> dict[str, str] | None:
    """UNDM switched off the device's management port, unsaved, so another device could
    take its address (D-107): it answers again after its next power-on."""
    extra = (device.observed_facts or {}).get("extra") or {}
    value = extra.get("management_port_off") if isinstance(extra, dict) else None
    return dict(value) if isinstance(value, dict) else None


def set_port_off(device: Device, port: str | None) -> None:
    facts = dict(device.observed_facts or {})
    extra = dict(facts.get("extra") or {})
    extra.pop("temporary_address", None)  # D-096's note, no longer used
    if port:
        extra["management_port_off"] = {"port": port, "since": datetime.now(UTC).isoformat()}
    else:
        extra.pop("management_port_off", None)
    facts["extra"] = extra
    device.observed_facts = facts


def login_after_loading_needed(device: Device) -> bool:
    """The device runs on a login its file will replace: a plan that loads the file must
    say which login is valid after loading (D-102)."""
    extra = (device.observed_facts or {}).get("extra") or {}
    return bool(isinstance(extra, dict) and extra.get("login_after_loading_needed"))


def set_login_after_loading_needed(device: Device, needed: bool) -> None:
    facts = dict(device.observed_facts or {})
    extra = dict(facts.get("extra") or {})
    if needed:
        extra["login_after_loading_needed"] = True
    else:
        extra.pop("login_after_loading_needed", None)
    facts["extra"] = extra
    device.observed_facts = facts


def _last_console_port(device: Device) -> tuple[str, datetime] | None:
    """The serial port of the device's last successful console setup or first access, and
    when (read only)."""
    session = object_session(device)
    if session is None:
        return None
    for event in session.scalars(
            select(AuditEvent).where(AuditEvent.target_id == device.id,
                                     AuditEvent.action == "provisioning.console_bootstrap",
                                     AuditEvent.outcome.in_(("bootstrapped",
                                                             "already_configured")))
            .order_by(AuditEvent.timestamp.desc())):
        port = (event.details or {}).get("serial_port")
        if isinstance(port, str) and _CONSOLE_PORT.fullmatch(port) and port != "SIMULATED":
            return port, event.timestamp
    return None


def _first_access_port(device: Device) -> str | None:
    """The serial port of the device's last successful first access, for devices set up
    before UNDM saved the port (v90, D-116). It is the port the person chose then; it is
    saved on the device and audited."""
    found = _last_console_port(device)
    session = object_session(device)
    if found is None or session is None:
        return None
    audit.record(session, "undm", "device.console_port_set", "device", device.id,
                 details={"console_port": found[0],
                          "from": f"first access on {found[1]:%Y-%m-%d %H:%M}"})
    return found[0]


_CONSOLE_PORT = re.compile(r"[A-Za-z0-9_./:\\-]{1,64}")


def build_driver(device: Device, registry: DriverRegistry,
                 via: reach.Via | None = None) -> DeviceDriver:
    """The driver for the device where its system reaches it (``via``: plans pass "bench",
    D-125). The only place a ``DeviceTarget`` is made."""
    where = reach.reach_of(device, registry, via)
    if where.driver_id not in registry:
        raise ServiceError(f"Unknown driver {where.driver_id!r}")
    driver_cls = registry.get(where.driver_id)
    caps = driver_cls.info.capabilities
    console_only = Capability.SERIAL_CONSOLE in caps and Capability.SSH not in caps
    if not where.address:
        if not console_only:
            raise ServiceError(where.problem or f"Device {device.name} has no management address")
        if Capability.CONFIGURATION_APPLY not in caps:
            raise ServiceError(
                f"{device.name} is reached over its console cable only: use Console setup. "
                "It has no network address for UNDM to test or read.")
        if not driver_cls.info.simulated and not device.console_port:
            device.console_port = _first_access_port(device)
        if not driver_cls.info.simulated and not device.console_port:
            raise ServiceError(
                f"{device.name} is reached over its console cable: say which serial port of "
                "this PC it is on (the one chosen in Console setup, e.g. COM3): Edit on its "
                "device page, Console port. Its first access saves it from now on.")
    credentials: Credentials | None = None
    if device.credential_ref is not None:
        try:
            credentials = creds.resolve(device.credential_ref.provider,
                                        device.credential_ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(str(e)) from e
    elif not driver_cls.info.simulated and Capability.GUIDED_STAGING not in caps:
        raise ServiceError(
            f"{device.name} has no login chosen. Choose one on its device page (Edit), or in "
            "Stage a system, step 1 ('Its login'). Logins are added on the system page's "
            "Logins tab.")
    target = DeviceTarget(device.id, where.address, where.port,
                          console_port=device.console_port)
    return registry.create(where.driver_id, target, credentials)


def connection(device: Device, registry: DriverRegistry) -> dict[str, Any]:
    """How UNDM reaches the device now, for the screens (menu, web link, Copy address)."""
    where = reach.reach_of(device, registry)
    caps = (sorted(c.value for c in registry.get(where.driver_id).capabilities())
            if where.driver_id in registry else [])
    return {"via": where.via, "address": where.address, "port": where.port,
            "driver_id": where.driver_id, "capabilities": caps, "problem": where.problem}


def known_addresses(device: Device) -> list[tuple[str, str]]:
    """The device's addresses, for masking text that is shared."""
    return [("ip", a) for a in (device.management_address, device.network_address) if a]


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
            out: dict[str, Any] = {"status": conn.status.value, "message": conn.message}
            if conn.diagnostics.get("login_refused"):
                out["login_refused"] = True
            return out
        device.last_connection_at = now
        if port_off(device):  # it answers again: switched off and on since (D-107)
            set_port_off(device, None)
            audit.record(session, actor, "device.management_port_on", "device", device.id)
        if op is DeviceOperation.CHECK_REACHABILITY:
            result = conn
            payload: Any = None
        elif op is DeviceOperation.GET_FACTS:
            result = driver.get_device_facts()
            payload = asdict(result.data) if result.ok else None
            if result.ok:
                pending = login_after_loading_needed(device)
                device.observed_facts = payload
                if pending:
                    set_login_after_loading_needed(device, True)
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
             ("serial", str(facts.get("serial_number") or "")), *known_addresses(device)]
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


# -- an SSH window on this PC (D-098) ------------------------------------------------------

_ADDRESS = re.compile(r"^[A-Za-z0-9.:-]{1,253}$")
_USER = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def ssh_command(device: Device, registry: DriverRegistry) -> list[str]:
    """The command that opens an SSH session to the device. The password is never in it:
    the person types it in the window."""
    if device.driver_id in registry and registry.get(device.driver_id).info.simulated:
        raise ConflictError("A simulated device has no SSH server to open")
    where = reach.reach_of(device, registry)
    if where.driver_id in registry and \
            Capability.SSH not in registry.get(where.driver_id).info.capabilities:
        raise ConflictError(
            f"UNDM does not reach {device.name} over SSH "
            + ("in the network" if where.via == "network" else "on the bench")
            + ": open its console window or its web page instead")
    address = where.address
    if where.problem:
        raise ConflictError(where.problem)
    if not address or not _ADDRESS.match(address) or address.startswith("-"):
        raise ConflictError(f"{device.name} has no usable management address")
    user = "admin"
    if device.credential_ref is not None:
        try:
            user = creds.resolve(device.credential_ref.provider,
                                 device.credential_ref.locator).username or user
        except creds.CredentialResolutionError as e:
            raise ServiceError(str(e)) from e
    if not _USER.match(user):
        raise ConflictError("The login's user name cannot be passed to the SSH program")
    port = where.port or 22
    # Bench units are reset and re-used at the same addresses, so their host keys change
    # often: like UNDM's own sessions, this window does not keep or check them (D-098).
    return ["ssh", "-o", "StrictHostKeyChecking=no", "-o",
            f"UserKnownHostsFile={os.devnull}", "-p", str(port), f"{user}@{address}"]


def launch_window(argv: list[str]) -> None:
    """Start a console program in a new window on this PC (Windows only)."""
    if os.name != "nt":
        raise ConflictError("Opening an SSH window is available when UNDM runs on Windows "
                            "(the bench PC)")
    exe = shutil.which("ssh") or os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"),
                                              "System32", "OpenSSH", "ssh.exe")
    if not os.path.exists(exe):
        raise ConflictError("Windows' SSH program (OpenSSH client) is not installed on "
                            "this PC")
    subprocess.Popen([exe, *argv[1:]],  # noqa: S603 - fixed program, checked arguments
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def open_ssh(session: Session, device: Device, registry: DriverRegistry,
             actor: str) -> dict[str, str]:
    argv = ssh_command(device, registry)
    launch_window(argv)
    audit.record(session, actor, "device.session_opened", "device", device.id,
                 details={"program": "ssh", "address": argv[-1].split("@", 1)[1]})
    return {"command": " ".join(argv)}


# -- a console window on this PC (D-118) ---------------------------------------------------

def _putty() -> str | None:
    found = shutil.which("putty")
    if found:
        return found
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
        path = os.path.join(base, "PuTTY", "putty.exe") if base else ""
        if path and os.path.exists(path):
            return path
    return None


# Speeds a serial console can be set to (the person may type another model's speed).
CONSOLE_SPEEDS = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)


def console_settings(device: Device, registry: DriverRegistry, *, port: str | None = None,
                     speed: int | None = None) -> tuple[str | None, int | None, str]:
    """The COM port and speed for the device's console window (D-126), and where the
    speed comes from: the one chosen, else the device's saved one, else the one its model's
    driver documents (with its source); the port likewise, else its last console setup."""
    driver_cls = registry.get(device.driver_id) if device.driver_id in registry else None
    last = _last_console_port(device)
    chosen_port = port or device.console_port or (last[0] if last else None)
    if speed:
        return chosen_port, speed, "chosen now"
    if device.console_speed:
        return chosen_port, device.console_speed, "saved for this device"
    if driver_cls is not None and driver_cls.console_speed:
        return chosen_port, driver_cls.console_speed, driver_cls.console_speed_source or "its model"
    return chosen_port, None, ""


def console_command(device: Device, registry: DriverRegistry, *, port: str | None = None,
                    speed: int | None = None) -> tuple[str, list[str], str, int]:
    """(program, command, port, speed) that opens a terminal on the device's console cable,
    for any real device (D-126, amends D-118). PuTTY when it is installed ("-serial",
    "-sercfg" from PuTTY's manual), else pySerial's own terminal (miniterm, installed with
    UNDM). Nothing is typed into it by UNDM."""
    if device.driver_id not in registry:
        raise ServiceError(f"Unknown driver {device.driver_id!r}")
    if registry.get(device.driver_id).info.simulated:
        raise ConflictError("A simulated device has no console to open")
    chosen_port, chosen_speed, _source = console_settings(device, registry, port=port,
                                                          speed=speed)
    if not chosen_port:
        raise ConflictError(f"Choose the COM port of this PC that {device.name}'s console cable "
                            "is on.")
    if chosen_port == "SIMULATED" or not _CONSOLE_PORT.fullmatch(chosen_port) \
            or chosen_port.startswith("-"):
        raise ConflictError("That console port cannot be passed to a terminal program")
    if not chosen_speed:
        raise ConflictError(f"Choose the console speed of {device.name}: UNDM has no documented "
                            "speed for its model.")
    if chosen_speed not in CONSOLE_SPEEDS:
        raise ConflictError(f"{chosen_speed} is not a console speed UNDM offers "
                            f"({', '.join(map(str, CONSOLE_SPEEDS))})")
    if port_lock(chosen_port).locked():
        raise ConflictError(f"UNDM is using {chosen_port} now (Console setup or a plan): open the "
                            "window when it has finished.")
    putty = _putty()
    if putty:
        return ("putty", [putty, "-serial", chosen_port, "-sercfg", f"{chosen_speed},8,n,1,N"],
                chosen_port, chosen_speed)
    return ("miniterm", [sys.executable, "-m", "serial.tools.miniterm", chosen_port,
                         str(chosen_speed)], chosen_port, chosen_speed)


def save_console_settings(session: Session, device: Device, port: str | None,
                          speed: int | None, actor: str, why: str) -> None:
    """Keep the console port and speed used, so the next window opens with them."""
    changes: dict[str, object] = {}
    if port and port != "SIMULATED" and port != device.console_port:
        changes["console_port"] = port
        device.console_port = port
    if speed and speed != device.console_speed:
        changes["console_speed"] = speed
        device.console_speed = speed
    if changes:
        audit.record(session, actor, "device.console_port_set", "device", device.id,
                     details={**changes, "from": why})


def launch_console(argv: list[str]) -> None:
    """Start the terminal program in a new window on this PC (Windows only)."""
    if os.name != "nt":
        raise ConflictError("Opening a console window is available when UNDM runs on Windows "
                            "(the bench PC)")
    subprocess.Popen(argv,  # noqa: S603 - fixed programs, checked arguments
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def open_console(session: Session, device: Device, registry: DriverRegistry,
                 actor: str, *, port: str | None = None,
                 speed: int | None = None) -> dict[str, str | int]:
    program, argv, used_port, used_speed = console_command(device, registry, port=port,
                                                           speed=speed)
    launch_console(argv)
    # What the person chose is kept; a port found from its last console setup too.
    save_console_settings(session, device, used_port if port or not device.console_port
                          else None, speed, actor, "console window")
    audit.record(session, actor, "device.session_opened", "device", device.id,
                 details={"program": program, "console_port": used_port,
                          "console_speed": used_speed})
    return {"program": program, "console_port": used_port, "console_speed": used_speed,
            "command": " ".join(argv)}


# -- reachability of a system's devices (D-099) --------------------------------------------

def reachability(session: Session, project_id: str,
                 registry: DriverRegistry) -> list[dict[str, str]]:
    """For each device: does its management port accept a TCP connection now? No login,
    nothing sent. Simulated devices are reported as such."""
    from concurrent.futures import ThreadPoolExecutor

    from undm.drivers.ssh import base as ssh_base

    devices = list(session.scalars(select(Device).where(Device.project_id == project_id)))

    def check(d: Device) -> dict[str, str]:
        simulated = d.driver_id in registry and registry.get(d.driver_id).info.simulated
        where = reach.reach_of(d, registry)
        address = where.address
        if simulated:
            state = "simulated"
        elif not address:
            state = "no_network_address" if where.via == "network" else "no_address"
        else:
            state = ("answers" if ssh_base.tcp_port_open(address, where.port or 22,
                                                         timeout=2.0) else "no_answer")
        return {"device_id": d.id, "address": address or "", "state": state,
                "via": where.via}

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(check, devices))


# -- one device's log (D-099) ---------------------------------------------------------------

def device_log(session: Session, device: Device, limit: int = 500) -> list[dict[str, Any]]:
    """Everything UNDM recorded about one device, newest first: audit entries (console
    setups, tests, renames, plans) and the events of its plans."""
    from undm.db.models import AuditEvent, DeploymentEventRecord, DeploymentRecord

    rows: list[dict[str, Any]] = []
    for a in session.scalars(select(AuditEvent).where(AuditEvent.target_id == device.id)
                             .order_by(AuditEvent.timestamp.desc()).limit(limit)):
        details = dict(a.details or {})
        text = str(details.get("message") or "")
        rows.append({"time": a.timestamp, "source": "audit", "kind": a.action,
                     "status": a.outcome or "", "message": text, "actor": a.actor,
                     "plan_id": details.get("deployment")})
    events = session.execute(
        select(DeploymentEventRecord, DeploymentRecord.kind)
        .join(DeploymentRecord, DeploymentRecord.id == DeploymentEventRecord.deployment_id)
        .where(DeploymentEventRecord.device_id == device.id)
        .order_by(DeploymentEventRecord.timestamp.desc()).limit(limit))
    for e, kind in events:
        rows.append({"time": e.timestamp, "source": "plan", "kind": f"{kind}.{e.stage}",
                     "status": e.status, "message": e.message, "actor": "",
                     "plan_id": e.deployment_id})
    rows.sort(key=lambda r: _aware(r["time"]), reverse=True)
    return rows[:limit]


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)
