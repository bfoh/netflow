"""Console bootstrap of factory-default devices.

Provisioning is the one device-changing workflow outside the deployment lifecycle: the
device cannot be reached over the network yet, so there is nothing to preview against
and nobody else to approve at the bench. It keeps the same safeguards in another form:
an exact command preview, a typed confirmation of the device name, the real-device
write switch, a factory-default check, verification by read-back, and an audit record.
"""

from __future__ import annotations

import logging
import socket
import time
from ipaddress import IPv4Interface
from typing import Any

from sqlalchemy.orm import Session

from undm.db.models import CredentialRef, Device
from undm.domain.enums import ProvisioningStatus
from undm.drivers.base import Credentials
from undm.drivers.registry import DriverRegistry
from undm.provisioning import aos_switch, sros_sar
from undm.provisioning.console import (
    ConsoleError,
    ConsoleSession,
    Transport,
    list_serial_ports,
    open_serial,
    port_lock,
)
from undm.provisioning.results import BootstrapStatus
from undm.provisioning.simulated import SimulatedArubaConsole
from undm.provisioning.simulated_sar import SimulatedSarConsole
from undm.security import credentials as creds
from undm.security.sanitize import new_mapper, sanitize
from undm.services import app_settings, audit
from undm.services.devices import save_console_settings, set_login_after_loading_needed
from undm.services.errors import ConflictError, ForbiddenError, ServiceError
from undm.services.policy import Policy
from undm.services.reach import require_bench

log = logging.getLogger(__name__)

SIMULATED_PORT = "SIMULATED"
# Driver platforms that have a console bootstrap procedure.
CONSOLE_BOOTSTRAP_PLATFORMS = frozenset({"aos_switch", "sros_sar"})
# Nokia 7705 SAR-Hmc: its console procedure is the first access (D-112), not a management
# VLAN: no bootstrap settings, and the unit is switched off and on by the person.
SAR_PLATFORM = "sros_sar"

# One simulated console per simulated device, so repeated runs see earlier changes.
_simulated_consoles: dict[str, SimulatedArubaConsole] = {}
_simulated_sar: dict[str, SimulatedSarConsole] = {}
# What a first access running on a console is doing, per device, for progress reports
# (in memory only; nothing about it is stored).
_progress: dict[str, dict[str, Any]] = {}


def reset_simulation() -> None:
    _simulated_consoles.clear()
    _simulated_sar.clear()
    _progress.clear()


def console_progress(device_id: str) -> dict[str, Any]:
    """What the device's console procedure is doing now (or did last). Read-only."""
    p = _progress.get(device_id)
    if p is None:
        return {"running": False, "stage": None, "seconds": 0, "received": 0, "last_line": ""}
    session: ConsoleSession | None = p.get("session")
    end = p.get("ended") or time.monotonic()
    return {"running": p["ended"] is None, "stage": p["stage"],
            "seconds": int(end - p["started"]),
            "received": session.received if session is not None else 0,
            "last_line": sanitize(session.last_line, p["known"]) if session is not None else ""}


def serial_ports() -> list[dict[str, str]]:
    ports = [{"port": SIMULATED_PORT, "hardware_id": "",
              "description": "Simulated switch console (for simulated devices only)"}]
    try:
        ports += list_serial_ports()
    except Exception:  # noqa: BLE001 - port enumeration must never break the page
        log.warning("could not list serial ports", exc_info=True)
    return ports


def supports_console_bootstrap(device: Device, registry: DriverRegistry) -> bool:
    return (device.driver_id in registry
            and registry.get(device.driver_id).info.platform in CONSOLE_BOOTSTRAP_PLATFORMS)


def _params(device: Device, profile: dict[str, Any] | None) -> aos_switch.BootstrapParams:
    data = profile or device.bootstrap_profile
    if not data:
        raise ServiceError("No bootstrap settings: enter the VLAN, port and address first")
    try:
        return aos_switch.BootstrapParams(
            vlan_id=int(data["vlan_id"]), vlan_name=str(data["vlan_name"]),
            untagged_port=str(data["untagged_port"]),
            address=IPv4Interface(str(data["address"])))
    except (KeyError, ValueError) as e:
        raise ServiceError(f"Invalid bootstrap settings: {e}") from e


def preview(device: Device, registry: DriverRegistry, policy: Policy,
            profile: dict[str, Any] | None) -> dict[str, Any]:
    require_bench(device.project, "console setup is done")
    if not supports_console_bootstrap(device, registry):
        return {"supported": False, "commands": [], "notes": [
            "No console bootstrap procedure exists for this device's platform yet."]}
    info = registry.get(device.driver_id).info
    if info.platform == SAR_PLATFORM:
        return _sar_preview(device, info.simulated, policy)
    params = _params(device, profile)
    login = device.credential_ref.name if device.credential_ref is not None else None
    notes = [
        "Sent over the console cable after reaching the manager prompt; the switch must be "
        "in factory-default state (no password, no site configuration).",
        ("If the switch is new and asks to 'Configure the manager credentials', UNDM sets "
         f"the device's attached login '{login}' (user and password; the password is never "
         "shown) and answers only the username and the two password prompts."
         if login else
         "New switches ask to 'Configure the manager credentials' before anything else: "
         "attach the approved login to the device first, or the bootstrap stops there."),
        ("If the switch answers only to the login it has now (an erase keeps its password), "
         f"UNDM gives it the password of '{login}' with 'password manager' (the switch asks "
         "for it twice) and saves it, so it ends on the approved login."
         if login else ""),
        f"Port {params.untagged_port} leaves the default VLAN and becomes the untagged member "
        f"of VLAN {params.vlan_id}.",
        "The configuration is saved with 'write memory' only after it has been read back "
        "and matches.",
    ]
    if info.simulated:
        notes.append("This is a simulated device: choose the SIMULATED console port.")
    else:
        problem = policy.write_problem(device.name, device.environment, simulated=False)
        if problem:
            notes.append("Blocked at the moment: " + problem)
        notes.append("Close PuTTY or any other program using the COM port before running.")
    return {"supported": True, "commands": params.commands(), "notes": [n for n in notes if n]}


def _device_credentials(device: Device) -> Credentials | None:
    if device.credential_ref is None:
        return None
    try:
        return creds.resolve(device.credential_ref.provider, device.credential_ref.locator)
    except creds.CredentialResolutionError as e:
        raise ServiceError(str(e)) from e


def _sar_preview(device: Device, simulated: bool, policy: Policy) -> dict[str, Any]:
    login = device.credential_ref.name if device.credential_ref is not None else None
    notes = [
        "For a modem straight from the factory. Press Run first, then switch the modem off "
        "and on. About 2.5 minutes later it asks for a key for 3 seconds: UNDM presses Enter "
        "at once (it waits up to 10 minutes for that question).",
        f"Console speed {sros_sar.CONSOLE_SPEED}. UNDM answers only the questions listed "
        "here, in this order; any other question ends the run with the modem's own words.",
        "The boot menu is told not to write the boot options file. The modem then starts "
        "once without its configuration and without auto-discovery, and accepts the factory "
        "login.",
        (f"The admin password becomes the password of this device's login '{login}' (never "
         "shown). The modem may refuse a password it finds too simple."
         if login else
         "Choose this device's login first: its password becomes the modem's admin password."),
        "The boot options (configuration file, persist on, no auto-discovery) are read back "
        "before 'bof save' and 'admin save'.",
        "A modem whose boot options have no auto-discovery is not a factory unit: UNDM sends "
        "no key and changes nothing.",
        "Experimental: built from the team's console recording; not yet run by UNDM on a "
        "modem.",
    ]
    if simulated:
        notes.append("This is a simulated device: choose the SIMULATED console port.")
    else:
        problem = policy.write_problem(device.name, device.environment, simulated=False)
        if problem:
            notes.append("Blocked at the moment: " + problem)
        notes.append("Close PuTTY or any other program using the COM port before running.")
    try:
        problem = sros_sar.password_problem(_device_credentials(device))
    except ServiceError as e:
        problem = str(e)
    if problem:
        notes.append("Before you run: " + problem)
    return {"supported": True, "commands": sros_sar.preview_steps(), "notes": notes,
            "procedure": "first_access"}


def _tcp_reachable(address: str, port: int = 22, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False


def identify_console(
    session: Session, device: Device, registry: DriverRegistry, actor: str, *,
    serial_port: str, baudrate: int, current_credential_ref_id: str | None,
) -> dict[str, Any]:
    """Read which switch is on the console, changing nothing (D-095).

    Logs in with the switch's current login and returns the hostname of its prompt and
    whether it holds configuration, so a person confirms an erase by the name UNDM read
    instead of typing a name they would first have to look up with a terminal program."""
    require_bench(device.project, "console setup is done")
    if not supports_console_bootstrap(device, registry):
        raise ServiceError("No console procedure exists for this device's platform")
    if registry.get(device.driver_id).info.platform == SAR_PLATFORM:
        raise ServiceError("Reading the name from the console is for the 2930F. The modem "
                           "shows its own name at the end of its first access.")
    if device.locked_by_deployment_id:
        raise ConflictError("Device is locked by a running deployment")
    simulated = registry.get(device.driver_id).info.simulated
    if simulated != (serial_port == SIMULATED_PORT):
        raise ServiceError(
            "Simulated devices use the SIMULATED console port" if simulated
            else "A real device needs a real serial port, not the simulated console")
    current: Credentials | None = None
    if current_credential_ref_id:
        ref = session.get(CredentialRef, current_credential_ref_id)
        if not app_settings.usable_by(ref, device.project_id):
            raise ConflictError("Current login: credential not found in this project")
        try:
            current = creds.resolve(ref.provider, ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(f"Credential '{ref.name}': {e}") from e
    lock = port_lock(serial_port if not simulated else f"sim:{device.id}")
    if not lock.acquire(blocking=False):
        raise ConflictError(f"{serial_port} is already in use by another console session")
    transport: Transport | None = None
    out: dict[str, Any]
    try:
        try:
            if simulated:
                sim = _simulated_consoles.setdefault(device.id, SimulatedArubaConsole())
                sim._state, sim._enters = "asleep", 0  # noqa: SLF001 - new console session
                transport = sim
                console = aos_switch.ArubaOSSwitchConsole(
                    ConsoleSession(sim, read_timeout=2.0, settle_time=0), current,
                    wake_delay=0.0)
            else:
                transport = open_serial(serial_port, baudrate)
                console = aos_switch.ArubaOSSwitchConsole(ConsoleSession(transport), current,
                                                          wake_delay=0.5)
            console.read_only = True
            name = console.login()
            findings: list[str] = []
            if device.bootstrap_profile:
                findings = aos_switch.site_config_findings(
                    console.running_config(), _params(device, None))
            else:
                # Without bootstrap settings: any hostname of its own means it was set up.
                findings = [] if name.lower().startswith("aruba-") else ["hostname"]
            out = {"state": "configured" if findings else "factory_default", "hostname": name,
                   "message": (f"The switch on this console is '{name}' and holds "
                               "configuration." if findings else
                               f"The switch on this console ('{name}') is already at factory "
                               "default: run the setup without 'erase first'.")}
        except aos_switch.NewSwitchError:
            out = {"state": "new", "hostname": "",
                   "message": "The switch on this console is new (it asks to set its manager "
                              "credentials): run the setup without 'erase first'."}
        except ConsoleError as e:
            out = {"state": "unknown", "hostname": "",
                   "message": f"Could not read the switch's name: {e}"}
    finally:
        if transport is not None and not simulated:
            transport.close()
        lock.release()
    audit.record(session, actor, "provisioning.console_identify", "device", device.id,
                 details={"serial_port": serial_port, "state": out["state"]})
    return out


def run_console_bootstrap(
    session: Session, device: Device, registry: DriverRegistry, policy: Policy, actor: str, *,
    serial_port: str, baudrate: int, profile: dict[str, Any] | None,
    confirm_device_name: str, allow_configured: bool,
    erase_existing: bool = False, current_credential_ref_id: str | None = None,
    confirm_hostname: str | None = None,
) -> dict[str, Any]:
    require_bench(device.project, "console setup and first access are done")
    if not supports_console_bootstrap(device, registry):
        raise ServiceError("No console bootstrap procedure exists for this device's platform")
    if confirm_device_name.strip() != device.name:
        raise ConflictError("Confirmation does not match the device name")
    if device.locked_by_deployment_id:
        raise ConflictError("Device is locked by a running deployment")
    if registry.get(device.driver_id).info.platform == SAR_PLATFORM:
        return _run_sar_first_access(session, device, registry, policy, actor,
                                     serial_port=serial_port, baudrate=baudrate)
    params = _params(device, profile)
    simulated = registry.get(device.driver_id).info.simulated
    if simulated != (serial_port == SIMULATED_PORT):
        raise ServiceError(
            "Simulated devices use the SIMULATED console port" if simulated
            else "A real device needs a real serial port, not the simulated console")
    if not simulated:
        problem = policy.write_problem(device.name, device.environment, simulated=False)
        if problem:
            raise ForbiddenError(problem)

    credentials: Credentials | None = None
    if device.credential_ref is not None:
        try:
            credentials = creds.resolve(device.credential_ref.provider,
                                        device.credential_ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(str(e)) from e

    # Erase a preconfigured switch first (D-057): opt-in, with its current login and the
    # hostname typed by the technician, checked against the switch before anything is sent.
    erase: aos_switch.EraseRequest | None = None
    current_ref: CredentialRef | None = None
    current: Credentials | None = None
    if current_credential_ref_id and not erase_existing:
        # The login the switch has now (D-102): tried when the approved login is refused.
        current_ref = session.get(CredentialRef, current_credential_ref_id)
        if not app_settings.usable_by(current_ref, device.project_id):
            raise ConflictError("Current login: credential not found in this project")
        try:
            current = creds.resolve(current_ref.provider, current_ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(f"Credential '{current_ref.name}': {e}") from e
    if erase_existing:
        if not current_credential_ref_id or not (confirm_hostname or "").strip():
            raise ConflictError("To erase a preconfigured switch, choose its current login and "
                                "type its current hostname (as shown in its console prompt)")
        current_ref = session.get(CredentialRef, current_credential_ref_id)
        if not app_settings.usable_by(current_ref, device.project_id):
            raise ConflictError("Current login: credential not found in this project")
        if credentials is None or not credentials.password:
            raise ConflictError(
                "After the erase the switch is set up with this device's login, which has no "
                "password (or none is chosen). Choose the approved login as the device's login "
                "(Stage a system, step 1, or Edit on the device page), then run again. "
                "Nothing was erased.")
        try:
            current = creds.resolve(current_ref.provider, current_ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(f"Credential '{current_ref.name}': {e}") from e
        erase = aos_switch.EraseRequest(current, (confirm_hostname or "").strip())

    lock = port_lock(serial_port if not simulated else f"sim:{device.id}")
    if not lock.acquire(blocking=False):
        raise ConflictError(f"{serial_port} is already in use by another bootstrap")
    transport: Transport | None = None
    try:
        try:
            if simulated:
                sim = _simulated_consoles.setdefault(device.id, SimulatedArubaConsole())
                sim._state, sim._enters = "asleep", 0  # noqa: SLF001 - new console session
                transport = sim
                console_session = ConsoleSession(sim, read_timeout=2.0, settle_time=0)
                wake = 0.0
            else:
                transport = open_serial(serial_port, baudrate)
                console_session = ConsoleSession(transport)
                wake = 0.5
        except ConsoleError as e:
            raise ServiceError(str(e)) from e
        result = aos_switch.bootstrap(
            aos_switch.ArubaOSSwitchConsole(console_session, credentials, wake_delay=wake),
            params, allow_configured=allow_configured, erase=erase, current=current)
    finally:
        if transport is not None and not simulated:
            transport.close()
        lock.release()

    ok = result.status in (aos_switch.BootstrapStatus.BOOTSTRAPPED,
                           aos_switch.BootstrapStatus.ALREADY_CONFIGURED)
    address = str(params.address.ip)
    stored_profile = {"vlan_id": params.vlan_id, "vlan_name": params.vlan_name,
                      "untagged_port": params.untagged_port, "address": str(params.address)}
    device.bootstrap_profile = stored_profile
    reachable: bool | None = None
    hint = ""
    if ok and result.kept_current_login and current_ref is not None \
            and device.credential_ref_id != current_ref.id:
        # The switch still answers to the login it had: UNDM must use that one until its
        # file sets the approved password ('Login after loading', D-102).
        audit.record(session, actor, "device.credential_changed", "device", device.id,
                     details={"from": device.credential_ref_id, "to": current_ref.id,
                              "reason": "the switch kept its previous password"})
        device.credential_ref_id = current_ref.id
        set_login_after_loading_needed(device, True)
    if ok:
        device.provisioning_status = ProvisioningStatus.BOOTSTRAPPED.value
        if not device.management_address:
            device.management_address = address
        if not simulated:
            # Its console window opens with the port and speed that worked (D-126).
            save_console_settings(session, device, serial_port, baudrate, actor,
                                  "console setup")
            reachable = _tcp_reachable(address)
            hint = ("SSH port answers: continue with Test connection on the device page."
                    if reachable else
                    f"The switch does not answer on {address}:22 from this PC yet. Plug its "
                    f"port {params.untagged_port} into the bench switch the PC is on (or into "
                    f"the PC directly), check that the PC has an address in "
                    f"{params.address.network} (for example "
                    f"{params.address.network.network_address + 50}), then press Test (Stage a "
                    "system, step 3) or Test connection (device page).")
    known = [("hostname", device.name), ("ip", address)]
    shown = sanitize(result.transcript, known)
    # A failed setup keeps the console's last words for the bench log (passwords are never in
    # the transcript: UNDM writes "(password: not shown)" instead).
    tail = shown[-1500:] if result.status.value == "failed" else None
    audit.record(session, actor, "provisioning.console_bootstrap", "device", device.id,
                 result.status.value, {
                     "serial_port": serial_port, "profile": stored_profile,
                     "commands_sent": result.commands_sent, "findings": result.findings,
                     "verified": result.verified, "saved": result.saved,
                     "message": result.message, "allow_configured": allow_configured,
                     "first_login_credentials_set": result.credentials_set,
                     "no_manager_password": result.no_password,
                     "manager_password_set": result.password_set,
                     "erase_existing": erase_existing, "erased_hostname": result.erased,
                     "kept_current_login": result.kept_current_login,
                     "current_login": current_ref.name if current_ref else None,
                     "credential": device.credential_ref.name if device.credential_ref
                     else None, **({"transcript_tail": tail} if tail else {})})
    return {
        "status": result.status.value, "message": result.message,
        "commands_sent": result.commands_sent, "findings": result.findings,
        "verified": result.verified, "saved": result.saved, "transcript": result.transcript,
        "credentials_set": result.credentials_set, "erased": result.erased,
        "no_password": result.no_password, "password_set": result.password_set,
        "sanitized_transcript": shown,
        "network_reachable": reachable, "network_hint": hint,
    }


def _run_sar_first_access(
    session: Session, device: Device, registry: DriverRegistry, policy: Policy, actor: str, *,
    serial_port: str, baudrate: int,
) -> dict[str, Any]:
    """First access to a factory Nokia 7705 SAR-Hmc (D-112). The caller has checked the
    typed device name and that no plan holds the device."""
    simulated = registry.get(device.driver_id).info.simulated
    if simulated != (serial_port == SIMULATED_PORT):
        raise ServiceError(
            "Simulated devices use the SIMULATED console port" if simulated
            else "A real device needs a real serial port, not the simulated console")
    if not simulated:
        problem = policy.write_problem(device.name, device.environment, simulated=False)
        if problem:
            raise ForbiddenError(problem)
    credentials = _device_credentials(device)
    problem = sros_sar.password_problem(credentials)
    if problem:
        raise ConflictError(f"{problem} Nothing was sent to the modem.")

    lock = port_lock(serial_port if not simulated else f"sim:{device.id}")
    if not lock.acquire(blocking=False):
        raise ConflictError(f"{serial_port} is already in use by another console session")
    transport: Transport | None = None
    progress: dict[str, Any] = {"stage": "opening", "started": time.monotonic(), "ended": None,
                                "session": None, "known": [("hostname", device.name)]}
    _progress[device.id] = progress
    try:
        try:
            if simulated:
                sim = _simulated_sar.setdefault(device.id, SimulatedSarConsole())
                sim.key_window = 0.0
                sim.power_cycle()  # "switched off and on" as the run starts
                transport = sim
                console_session = ConsoleSession(sim, read_timeout=2.0, settle_time=0)
                timing = sros_sar.Timing(power_on=2.0, menu=2.0, boot=2.0, command=2.0)
            else:
                transport = open_serial(serial_port, baudrate)
                console_session = ConsoleSession(transport)
                timing = sros_sar.Timing()
        except ConsoleError as e:
            raise ServiceError(str(e)) from e
        progress["session"] = console_session
        result = sros_sar.first_access(console_session, credentials, timing,
                                       on_stage=lambda stage: progress.update(stage=stage))
    finally:
        progress["ended"] = time.monotonic()
        if transport is not None and not simulated:
            transport.close()
        lock.release()

    ok = result.status in (BootstrapStatus.BOOTSTRAPPED, BootstrapStatus.ALREADY_CONFIGURED)
    if ok:
        device.provisioning_status = ProvisioningStatus.BOOTSTRAPPED.value
        if not simulated:  # its file is loaded over the same port later (D-116)
            save_console_settings(session, device, serial_port, baudrate, actor,
                                  "first access")
    known = [("hostname", device.name)]
    if result.facts.get("name"):
        known.append(("hostname", result.facts["name"]))
    # A factory unit is named after its serial number: mask the names its prompts show.
    known += [("hostname", n) for n in sros_sar.prompt_names(result.transcript)]
    progress["known"] = known
    mapper = new_mapper()
    shown = sanitize(result.transcript, known, mapper)
    diagnostics = {k: sanitize(v, known, mapper) for k, v in result.diagnostics.items()}
    if diagnostics:
        shown += "\n\n--- Technical details (UNDM) ---\n" + "\n".join(
            f"{k}:\n{v}" if "\n" in v else f"{k}: {v}" for k, v in diagnostics.items())
    tail = shown[-1500:] if result.status.value == "failed" else None
    audit.record(session, actor, "provisioning.console_bootstrap", "device", device.id,
                 result.status.value, {
                     "procedure": "sros_sar_first_access", "serial_port": serial_port,
                     "commands_sent": result.commands_sent, "findings": result.findings,
                     "verified": result.verified, "saved": result.saved,
                     "message": result.message, "admin_password_set": result.password_set,
                     "facts": result.facts, "diagnostics": diagnostics,
                     "credential": device.credential_ref.name if device.credential_ref
                     else None, **({"transcript_tail": tail} if tail else {})})
    hint = ("Next: its configuration file, loaded over this console port by a plan (Stage "
            "a system, step 4)." if ok else "")
    return {
        "status": result.status.value, "message": result.message,
        "commands_sent": result.commands_sent, "findings": result.findings,
        "verified": result.verified, "saved": result.saved, "transcript": result.transcript,
        "credentials_set": False, "erased": "", "no_password": False,
        "password_set": result.password_set, "sanitized_transcript": shown,
        "network_reachable": None, "network_hint": hint, "facts": result.facts,
        "diagnostics": diagnostics,
    }
