"""Where UNDM reaches a device: on the bench or in the network (D-125).

A system is staged on the bench (each device at its bench address, ``management_address``).
After staging it is moved to the network: the laptop sits on a port of the system's BFW,
which routes it to each device's network address, the one its file gave it
(``network_address``). Every connection UNDM makes, and every window it opens, takes its
address, port and driver from :func:`reach_of`; nothing else reads those fields to connect.

Changing devices stays on the bench: plans, console setup, first access and guided steps
call :func:`require_bench`. In the network the system may be a live site, so its real
devices are marked production there and UNDM's own logins to them need the start-up
setting ``UNDM_ALLOW_PRODUCTION_READ_ONLY`` (the existing read gate).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.db.models import Device, Project
from undm.domain.enums import DeviceCategory, DeviceEnvironment
from undm.drivers.registry import DriverRegistry
from undm.services import audit
from undm.services.errors import ConflictError, NotFoundError

Via = Literal["bench", "network"]
VIAS: tuple[Via, ...] = ("bench", "network")


@dataclass(frozen=True)
class Reach:
    via: Via
    address: str  # "" when it has none there yet
    port: int | None
    driver_id: str
    problem: str | None = None  # why UNDM cannot reach it there (no address yet)


def via_of(project: Project | None) -> Via:
    return "network" if project is not None and project.reached_via == "network" else "bench"


def network_driver_id(device: Device, registry: DriverRegistry) -> str:
    """The driver for the device in the network: its driver's network driver where one is
    declared and known, else its own."""
    if device.driver_id in registry:
        other = registry.get(device.driver_id).network_driver_id
        if other and other in registry:
            return other
    return device.driver_id


def reach_of(device: Device, registry: DriverRegistry, via: Via | None = None) -> Reach:
    """How UNDM reaches the device: on the bench or in the network (its system's choice
    unless ``via`` is given; plans always pass "bench")."""
    where: Via = via or via_of(device.project)
    if where == "bench":
        return Reach("bench", device.management_address or "", device.management_port,
                     device.driver_id)
    address = device.network_address or ""
    return Reach("network", address, device.management_port,
                 network_driver_id(device, registry),
                 None if address else
                 f"{device.name} has no network address yet: set it on its system's In the "
                 "network tab (or move the system back to the bench)")


def require_bench(project: Project | None, what: str) -> None:
    """Changes are made on the bench only (D-125): refuse them for a system in the network."""
    if via_of(project) == "network":
        name = project.name if project is not None else "This system"
        raise ConflictError(
            f"{name} is in the network (reached through its BFW): {what} only on the bench. "
            "Move the system back to the bench on its In the network tab first.")


# -- a device's network address -------------------------------------------------------------

def check_network_address(value: str) -> str:
    """One IPv4 unicast address, as typed or read from a file."""
    text = value.strip()
    try:
        ip = ipaddress.IPv4Address(text)
    except ValueError as e:
        raise ConflictError(f"'{text}' is not an IPv4 address (for example 198.51.100.10)") \
            from e
    if (ip.is_multicast or ip.is_unspecified or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or text.endswith(".255")):
        raise ConflictError(f"{text} cannot be a device's address")
    return str(ip)


def set_network_address(session: Session, device: Device, address: str | None, actor: str,
                        *, source: dict[str, object] | None = None) -> Device:
    """Set (or clear, with None or "") the device's network address. ``source`` says where
    it came from (a file and line, or typed) and is kept in the audit."""
    if device.locked_by_deployment_id:
        raise ConflictError("Device is locked by a running plan")
    value = check_network_address(address) if address and address.strip() else None
    if value is not None:
        clash = session.scalars(select(Device.name).where(
            Device.project_id == device.project_id, Device.id != device.id,
            Device.network_address == value)).first()
        if clash:
            raise ConflictError(f"{clash} of this system already has {value} as its network "
                                "address")
    before = device.network_address
    device.network_address = value
    session.flush()
    if before != value:
        audit.record(session, actor, "device.network_address_set", "device", device.id,
                     details={"from": before, "to": value, **(source or {"source": "typed"})})
    return device


# -- moving a system between the bench and the network ----------------------------------------

def default_gateway(project: Project) -> Device | None:
    """The BFW: the one chosen, else the system's only firewall."""
    if project.network_gateway_id:
        chosen = next((d for d in project.devices if d.id == project.network_gateway_id), None)
        if chosen is not None:
            return chosen
    firewalls = [d for d in project.devices if d.category == DeviceCategory.FIREWALL.value]
    return firewalls[0] if len(firewalls) == 1 else None


def set_reached_via(session: Session, project: Project, via: str, actor: str,
                    registry: DriverRegistry, *, gateway_device_id: str | None = None
                    ) -> Project:
    """Move the system to the network (through its BFW) or back to the bench.

    In the network the system may be a live site: its real devices are marked production,
    so UNDM's own logins to them need UNDM_ALLOW_PRODUCTION_READ_ONLY. Back on the bench they
    are lab devices again. Simulated devices keep their environment."""
    if via not in VIAS:
        raise ConflictError("Choose 'bench' or 'network'")
    busy = [d.name for d in project.devices if d.locked_by_deployment_id]
    if busy:
        raise ConflictError(f"A plan is running on {', '.join(sorted(busy))}: wait until it "
                            "has finished")
    gateway: Device | None = None
    if gateway_device_id:
        gateway = next((d for d in project.devices if d.id == gateway_device_id), None)
        if gateway is None:
            raise NotFoundError("The BFW must be a device of this system")
    elif via == "network":
        gateway = default_gateway(project)
    if via == "network":
        if gateway is None:
            raise ConflictError("Choose the system's BFW (the FortiGate the laptop is "
                                "connected to) first")
        if not gateway.network_address:
            raise ConflictError(f"Set the network address of {gateway.name} (the BFW) first")
    if gateway is not None:
        project.network_gateway_id = gateway.id
    before = via_of(project)
    marked: list[str] = []
    if before != via:
        target_env = (DeviceEnvironment.PRODUCTION if via == "network"
                      else DeviceEnvironment.LAB).value
        for d in project.devices:
            simulated = d.driver_id in registry and registry.get(d.driver_id).info.simulated
            if not simulated and d.environment != target_env:
                d.environment = target_env
                marked.append(d.name)
    project.reached_via = via
    session.flush()
    if before != via or gateway_device_id:
        audit.record(session, actor, "system.reached_via_changed", "project", project.id,
                     details={"from": before, "to": via,
                              "gateway": gateway.name if gateway else None,
                              "environment": (("production" if via == "network" else "lab")
                                              if marked else None),
                              "devices": sorted(marked)})
    return project
