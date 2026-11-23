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
import threading
from ipaddress import IPv4Interface
from typing import Any

from sqlalchemy.orm import Session

from undm.db.models import CredentialRef, Device
from undm.domain.enums import ProvisioningStatus
from undm.drivers.base import Credentials
from undm.drivers.registry import DriverRegistry
from undm.provisioning import aos_switch
from undm.provisioning.console import (
    ConsoleError,
    ConsoleSession,
    Transport,
    list_serial_ports,
    open_serial,
)
from undm.provisioning.simulated import SimulatedArubaConsole
from undm.security import credentials as creds
from undm.security.sanitize import sanitize
from undm.services import audit
from undm.services.errors import ConflictError, ForbiddenError, ServiceError
from undm.services.policy import Policy

log = logging.getLogger(__name__)

SIMULATED_PORT = "SIMULATED"
# Driver platforms that have a console bootstrap procedure.
CONSOLE_BOOTSTRAP_PLATFORMS = frozenset({"aos_switch"})

_port_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()
# One simulated console per simulated device, so repeated runs see earlier changes.
_simulated_consoles: dict[str, SimulatedArubaConsole] = {}


def reset_simulation() -> None:
    _simulated_consoles.clear()


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
    if not supports_console_bootstrap(device, registry):
        return {"supported": False, "commands": [], "notes": [
            "No console bootstrap procedure exists for this device's platform yet."]}
    params = _params(device, profile)
    info = registry.get(device.driver_id).info
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
    return {"supported": True, "commands": params.commands(), "notes": notes}


def _tcp_reachable(address: str, port: int = 22, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_console_bootstrap(
    session: Session, device: Device, registry: DriverRegistry, policy: Policy, actor: str, *,
    serial_port: str, baudrate: int, profile: dict[str, Any] | None,
    confirm_device_name: str, allow_configured: bool,
    erase_existing: bool = False, current_credential_ref_id: str | None = None,
    confirm_hostname: str | None = None,
) -> dict[str, Any]:
    if not supports_console_bootstrap(device, registry):
        raise ServiceError("No console bootstrap procedure exists for this device's platform")
    if confirm_device_name.strip() != device.name:
        raise ConflictError("Confirmation does not match the device name")
    if device.locked_by_deployment_id:
        raise ConflictError("Device is locked by a running deployment")
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
    if erase_existing:
        if not current_credential_ref_id or not (confirm_hostname or "").strip():
            raise ConflictError("To erase a preconfigured switch, choose its current login and "
                                "type its current hostname (as shown in its console prompt)")
        current_ref = session.get(CredentialRef, current_credential_ref_id)
        if current_ref is None or current_ref.project_id != device.project_id:
            raise ConflictError("Current login: credential not found in this project")
        if credentials is None or not credentials.password:
            raise ConflictError("After the erase the switch is set up with the device's login: "
                                "attach the approved login to the device first")
        try:
            current = creds.resolve(current_ref.provider, current_ref.locator)
        except creds.CredentialResolutionError as e:
            raise ServiceError(f"Credential '{current_ref.name}': {e}") from e
        erase = aos_switch.EraseRequest(current, (confirm_hostname or "").strip())

    with _registry_lock:
        lock = _port_locks.setdefault(serial_port if not simulated else f"sim:{device.id}",
                                      threading.Lock())
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
            params, allow_configured=allow_configured, erase=erase)
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
    if ok:
        device.provisioning_status = ProvisioningStatus.BOOTSTRAPPED.value
        if not device.management_address:
            device.management_address = address
        if not simulated:
            reachable = _tcp_reachable(address)
            hint = ("SSH port answers: continue with Test connection on the device page."
                    if reachable else
                    f"The switch does not answer on {address}:22 from this PC yet. Connect "
                    f"the PC to port {params.untagged_port} and give its wired adapter an "
                    f"address in {params.address.network} (for example "
                    f"{params.address.network.network_address + 50}).")
    audit.record(session, actor, "provisioning.console_bootstrap", "device", device.id,
                 result.status.value, {
                     "serial_port": serial_port, "profile": stored_profile,
                     "commands_sent": result.commands_sent, "findings": result.findings,
                     "verified": result.verified, "saved": result.saved,
                     "message": result.message, "allow_configured": allow_configured,
                     "first_login_credentials_set": result.credentials_set,
                     "no_manager_password": result.no_password,
                     "erase_existing": erase_existing, "erased_hostname": result.erased,
                     "current_login": current_ref.name if current_ref else None,
                     "credential": device.credential_ref.name if device.credential_ref
                     else None})
    known = [("hostname", device.name), ("ip", address)]
    return {
        "status": result.status.value, "message": result.message,
        "commands_sent": result.commands_sent, "findings": result.findings,
        "verified": result.verified, "saved": result.saved, "transcript": result.transcript,
        "credentials_set": result.credentials_set, "erased": result.erased,
        "no_password": result.no_password,
        "sanitized_transcript": sanitize(result.transcript, known),
        "network_reachable": reachable, "network_hint": hint,
    }
