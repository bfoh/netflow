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
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.db.models import (
    ConfigVersion,
    DeploymentRecord,
    DeploymentTargetRecord,
    Device,
    Project,
)
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


# -- the addresses a device's files give it ---------------------------------------------------

def _loaded_files(session: Session, device: Device) -> tuple[list[ConfigVersion], bool]:
    """The files UNDM last loaded on the device, in the order loaded (the steps of its latest
    staging plan, e.g. a FortiGate's base then site file); else its latest file, not loaded
    by UNDM (False)."""
    rows = session.execute(
        select(DeploymentRecord, DeploymentTargetRecord.config_version_id)
        .join(DeploymentTargetRecord, DeploymentTargetRecord.deployment_id == DeploymentRecord.id)
        .where(DeploymentTargetRecord.device_id == device.id,
               DeploymentRecord.kind == "configuration",
               DeploymentRecord.state == "succeeded", DeploymentRecord.dry_run.is_(False),
               DeploymentTargetRecord.config_version_id.is_not(None))
        .order_by(DeploymentRecord.created_at.desc())).all()
    if rows:
        latest = rows[0][0]
        same = [(r, v) for r, v in rows if latest.staging_id and r.staging_id == latest.staging_id]
        chosen = sorted(same, key=lambda rv: rv[0].staging_step or 0) if same else [rows[0]]
        files = [session.get(ConfigVersion, v) for _, v in chosen]
        return [f for f in files if f is not None], True
    last = session.scalars(
        select(ConfigVersion).where(ConfigVersion.device_id == device.id,
                                    ConfigVersion.kind.in_(("imported", "generated")))
        .order_by(ConfigVersion.created_at.desc()).limit(1)).first()
    return ([last] if last else []), False


def network_of(address: str, prefix: int | None) -> ipaddress.IPv4Network | None:
    """The network of an address with its prefix (a /32 when unknown)."""
    return _network_of(address, prefix)


def _network_of(address: str, prefix: int | None) -> ipaddress.IPv4Network | None:
    try:
        return ipaddress.IPv4Network(f"{address}/{prefix if prefix is not None else 32}",
                                     strict=False)
    except ValueError:
        return None


def _on_bench(address: str, prefix: int | None, bench: list[str]) -> bool:
    net = _network_of(address, prefix)
    if net is None:
        return False
    for b in bench:
        try:
            if b == address or ipaddress.IPv4Address(b) in net:
                return True
        except ValueError:
            continue
    return False


def _pc_address_towards(address: str) -> str | None:
    """This PC's own address on the way to ``address`` (nothing is sent)."""
    from undm.transfer.hub import local_address_towards

    try:
        return local_address_towards(address)
    except OSError:
        return None


@dataclass(frozen=True)
class Candidate:
    address: str
    prefix: int | None
    where: str
    line: int
    vdom: str | None
    allows: str
    file: str
    version_id: str
    on_bench: bool


def _candidates(session: Session, device: Device, registry: DriverRegistry
                ) -> tuple[list[ConfigVersion], bool, bool, list[Candidate],
                           list[dict[str, object]]]:
    driver = registry.get(device.driver_id) if device.driver_id in registry else None
    files, loaded = _loaded_files(session, device)
    bench = [d.management_address for d in device.project.devices if d.management_address]
    found_any = False
    candidates: list[Candidate] = []
    managers: list[dict[str, object]] = []
    for f in files:
        found = driver.file_addresses(f.text) if driver else None
        if found is None:
            continue
        found_any = True
        name = f.reference or f.kind
        candidates += [Candidate(a.address, a.prefix, a.where, a.line, a.vdom, a.allows, name,
                                 f.id, _on_bench(a.address, a.prefix, bench))
                       for a in found.addresses]
        managers += [{"first": m.first, "last": m.last, "text": m.text, "line": m.line,
                      "file": name} for m in found.managers]
    return files, loaded, found_any, candidates, managers


def file_candidates(session: Session, device: Device,
                    registry: DriverRegistry) -> list[Candidate]:
    """The addresses the device's files give it (offline)."""
    return _candidates(session, device, registry)[3]


def file_addresses(session: Session, device: Device, registry: DriverRegistry,
                   *, pc_address: Callable[[str], str | None] | None = None
                   ) -> dict[str, object]:
    """The addresses the device's files give it, read offline, with a suggestion for its
    network address (D-125). Nothing is sent to any device."""
    pc_address = pc_address or _pc_address_towards
    files, loaded, reader, candidates, managers = _candidates(session, device, registry)
    suggested, reason = _suggest(session, device, registry, candidates)
    toward = device.network_address or suggested
    pc = pc_address(toward) if toward else None
    allowed: bool | None = None
    if pc and managers:
        here = ipaddress.IPv4Address(pc)
        allowed = any(ipaddress.IPv4Address(str(m["first"])) <= here
                      <= ipaddress.IPv4Address(str(m["last"])) for m in managers)
    return {
        "files": [{"version_id": f.id, "name": f.reference or f.kind, "loaded": loaded,
                   "created_at": f.created_at} for f in files],
        "reader": reader, "addresses": [asdict(c) for c in candidates],
        "managers": managers, "suggested": suggested, "reason": reason,
        "pc_address": pc, "pc_allowed": allowed,
        "route_hint": route_hint(device, candidates),
    }


def _suggest(session: Session, device: Device, registry: DriverRegistry,
             candidates: list[Candidate]) -> tuple[str | None, str]:
    """One address only when the files leave no doubt; else the person chooses."""
    off_bench = [c for c in candidates if not c.on_bench]
    unique = {c.address for c in off_bench}
    if not candidates:
        return None, "Its files give it no address UNDM can read: type it."
    if not off_bench:
        return None, "Its files give it only bench addresses: type its network address."
    with_ssh = {c.address for c in off_bench if "ssh" in c.allows.split()}
    if len(with_ssh) == 1:
        return with_ssh.pop(), "The only address outside the bench that allows SSH."
    if len(unique) == 1:
        return next(iter(unique)), "The only address its files give it outside the bench."
    gateway = default_gateway(device.project)
    if gateway is not None and gateway.id != device.id:
        nets = [n for c in _candidates(session, gateway, registry)[3]
                if not c.on_bench and (n := _network_of(c.address, c.prefix)) is not None]
        inside = {a for a in unique if any(ipaddress.IPv4Address(a) in n for n in nets)}
        if len(inside) == 1:
            return inside.pop(), f"The only one in a network of {gateway.name} (the BFW)."
    return None, f"Its files give it {len(unique)} addresses outside the bench: choose one."


def route_hint(device: Device, candidates: list[Candidate]) -> str | None:
    """A Windows route command for this PC to reach the device's network through the BFW,
    shown only (UNDM never changes this PC's network settings)."""
    gateway = default_gateway(device.project)
    if gateway is None or gateway.id == device.id or not device.network_address \
            or not gateway.network_address:
        return None
    match = next((c for c in candidates if c.address == device.network_address), None)
    net = _network_of(device.network_address, match.prefix if match else 32)
    if net is None or ipaddress.IPv4Address(gateway.network_address) in net:
        return None
    return f"route add {net.network_address} mask {net.netmask} {gateway.network_address}"
