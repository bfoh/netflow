"""Ping and traceroute for troubleshooting after staging (D-128).

From this PC (Windows' ping and tracert) and, where a driver has a documented command,
from a device of the system (the BFW and any capable device). One target per request,
chosen by a person; Check all covers only the system's own addresses. Every request is
audited, with the hops recorded by device for the topology's packet path.

A target that belongs to a simulated device starts no program: the answer is simulated
(SYNTHETIC) and says so.
"""

from __future__ import annotations

import ipaddress
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from undm.db.models import Device, Project
from undm.domain.troubleshoot import (
    Hop,
    KnownAddress,
    PingResult,
    TargetError,
    TraceResult,
    check_target,
    match_hops,
)
from undm.drivers.base import Capability, DeviceDriver, OperationResult
from undm.drivers.registry import DriverRegistry
from undm.services import audit, pc_tools, reach
from undm.services import devices as devsvc
from undm.services.errors import ConflictError, ForbiddenError, NotFoundError
from undm.services.policy import Policy

PC = "pc"
SIMULATED_NOTE = "Simulated: nothing was sent."
_busy: dict[str, threading.Lock] = {}
_busy_guard = threading.Lock()


def _lock(source: str) -> threading.Lock:
    with _busy_guard:
        return _busy.setdefault(source, threading.Lock())


def known_addresses(session: Session, project: Project,
                    registry: DriverRegistry) -> list[KnownAddress]:
    """Every address the system's devices have: bench, network, and those their files give
    their interfaces (read offline)."""
    out: list[KnownAddress] = []
    for d in project.devices:
        for address, where in ((d.management_address, "bench address"),
                               (d.network_address, "network address")):
            if address:
                out.append(KnownAddress(d.id, address, where))
        for c in reach.file_candidates(session, d, registry):
            out.append(KnownAddress(d.id, c.address, c.where))
    return out


def _simulated(device: Device, registry: DriverRegistry) -> bool:
    return device.driver_id in registry and registry.get(device.driver_id).info.simulated


def _owner(project: Project, registry: DriverRegistry, known: list[KnownAddress],
           target: str) -> Device | None:
    ids = {k.device_id for k in known if k.address == target}
    devices = [d for d in project.devices if d.id in ids]
    return devices[0] if len(devices) == 1 else next(
        (d for d in devices if reach.reach_of(d, registry).address == target), None)


def _check(target: str) -> str:
    try:
        return check_target(target)
    except TargetError as e:
        raise ConflictError(str(e)) from e


def _source(project: Project, source: str) -> Device | None:
    if source == PC:
        return None
    device = next((d for d in project.devices if d.id == source), None)
    if device is None:
        raise NotFoundError("The source must be this PC or a device of this system")
    return device


def _simulated_ping(source: str, target: str, count: int) -> PingResult:
    from undm.drivers.mock.lab import default_lab

    unit = default_lab().get(target)
    answers = 0 if unit is not None and not unit.reachable else count
    return PingResult(source, target, count, answers, tuple(1.0 for _ in range(answers)),
                      simulated=True, note=SIMULATED_NOTE)


def _simulated_trace(project: Project, registry: DriverRegistry, source: str,
                     target: str) -> TraceResult:
    gateway = reach.default_gateway(project)
    hops: list[Hop] = []
    if (reach.via_of(project) == "network" and gateway is not None
            and gateway.network_address and gateway.network_address != target
            and source != gateway.id):
        hops.append(Hop(1, gateway.network_address, (1.0, 1.0, 1.0)))  # through the BFW
    hops.append(Hop(len(hops) + 1, target, (1.0, 1.0, 1.0)))
    return TraceResult(source, target, hops, True, simulated=True, note=SIMULATED_NOTE)


def ping(session: Session, project: Project, registry: DriverRegistry, actor: str, *,
         source: str, target: str, count: int = 4, policy: Policy | None = None
         ) -> dict[str, Any]:
    target = _check(target)
    if not 1 <= count <= 10:
        raise ConflictError("Send 1 to 10 echo requests")
    known = known_addresses(session, project, registry)
    owner = _owner(project, registry, known, target)
    from_device = _source(project, source)
    if owner is not None and _simulated(owner, registry):
        result = _simulated_ping(source, target, count)
    elif from_device is not None:
        result = _device_ping(session, from_device, registry, target, count, policy)
    else:
        received, rtts, raw = pc_tools.ping(target, count)
        result = PingResult(PC, target, count, received, rtts, raw=raw)
    audit.record(session, actor, "troubleshoot.ping", "project", project.id,
                 "answered" if result.answered else "no_answer", details={
                     "source": source, "target": target, "target_device": owner.id if owner
                     else None, "sent": result.sent, "received": result.received,
                     "simulated": result.simulated})
    return {**asdict(result), "answered": result.answered,
            "target_device": owner.id if owner else None}


def traceroute(session: Session, project: Project, registry: DriverRegistry, actor: str, *,
               source: str, target: str, policy: Policy | None = None) -> dict[str, Any]:
    target = _check(target)
    known = known_addresses(session, project, registry)
    owner = _owner(project, registry, known, target)
    from_device = _source(project, source)
    lock = _lock(source)
    if not lock.acquire(blocking=False):
        raise ConflictError("A traceroute from there is running: wait until it has finished")
    try:
        if owner is not None and _simulated(owner, registry):
            result = _simulated_trace(project, registry, source, target)
        elif from_device is not None:
            result = _device_trace(session, from_device, registry, target, policy)
        else:
            hops, raw = pc_tools.traceroute(target)
            result = TraceResult(PC, target, hops, any(h.address == target for h in hops),
                                 raw=raw)
    finally:
        lock.release()
    match_hops(result.hops, known)
    audit.record(session, actor, "troubleshoot.traceroute", "project", project.id,
                 "reached" if result.reached else "not_reached", details={
                     "source": source, "target": target, "simulated": result.simulated,
                     "hops": [{"n": h.n, "address": h.address, "device": h.device_id}
                              for h in result.hops]})
    return {**asdict(result), "target_device": owner.id if owner else None}


def check_all(session: Session, project: Project, registry: DriverRegistry, actor: str, *,
              source: str = PC, policy: Policy | None = None) -> list[dict[str, Any]]:
    """Each device of the system at the address UNDM uses: two echo requests and whether its
    management port accepts a connection (no login). At most 8 at a time."""
    from undm.drivers.ssh import base as ssh_base

    if source != PC:
        return _device_check_all(session, project, registry, actor, source, policy)
    rows = [(d, reach.reach_of(d, registry)) for d in project.devices]

    def one(item: tuple[Device, reach.Reach]) -> dict[str, Any]:
        d, where = item
        row: dict[str, Any] = {"device_id": d.id, "address": where.address, "via": where.via}
        if not where.address:
            return {**row, "state": "no_address", "note": where.problem or "No address"}
        if _simulated(d, registry):
            sim = _simulated_ping(PC, where.address, 2)
            return {**row, "state": "simulated", "sent": 2, "received": sim.received,
                    "port_open": sim.received > 0, "note": SIMULATED_NOTE}
        try:
            received, rtts, _ = pc_tools.ping(where.address, 2)
            ping_part: dict[str, Any] = {"sent": 2, "received": received, "rtt_ms": rtts}
        except ConflictError as e:
            ping_part = {"sent": 0, "received": None, "note": str(e)}
        port = ssh_base.tcp_port_open(where.address, where.port or 22, timeout=2.0)
        answered = bool(ping_part.get("received")) or port
        return {**row, **ping_part, "port": where.port or 22, "port_open": port,
                "state": "answers" if answered else "no_answer"}

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, rows))
    audit.record(session, actor, "troubleshoot.check_all", "project", project.id, details={
        "source": source, "devices": len(results),
        "answered": sum(1 for r in results if r["state"] in ("answers", "simulated"))})
    return results


# -- from a device of the system (D-128) ---------------------------------------------------

def _context(session: Session, device: Device, registry: DriverRegistry,
             target: str) -> dict[str, str]:
    """Where on the device to run it: the VDOM of its interface whose network holds the
    target, read from its files (FortiOS; other platforms have none)."""
    for c in reach.file_candidates(session, device, registry):
        net = reach.network_of(c.address, c.prefix)
        if c.vdom and net is not None and ipaddress.IPv4Address(target) in net:
            return {"vdom": c.vdom}
    return {}


def _driver_for(device: Device, registry: DriverRegistry, policy: Policy | None,
                capability: Capability) -> DeviceDriver:
    simulated = _simulated(device, registry)
    problem = (policy or Policy()).read_problem(device.name, device.environment, simulated)
    if problem:
        raise ForbiddenError(problem)
    driver = devsvc.build_driver(device, registry)
    if capability not in driver.capabilities():
        what = "ping" if capability is Capability.PING else "traceroute"
        raise ConflictError(f"UNDM has no documented {what} command for {device.name}: "
                            "choose this PC")
    return driver


def _connected(driver: DeviceDriver) -> None:
    conn = driver.connect()
    if not conn.ok:
        raise ConflictError(conn.message)


def _ping_result(device: Device, target: str, r: OperationResult, count: int) -> PingResult:
    if not r.ok:
        raise ConflictError(f"{device.name}: {r.message}")
    data = dict(r.data or {})
    received = data.get("received")
    return PingResult(device.id, target, int(data.get("sent") or count),
                      int(received) if received is not None else 0,
                      tuple(float(x) for x in data.get("rtt_ms") or ()),
                      simulated=False, raw=str(data.get("raw", "")),
                      note="" if received is not None else
                      "UNDM could not read the answer: see the output below.")


def _device_ping(session: Session, device: Device, registry: DriverRegistry, target: str,
                 count: int, policy: Policy | None) -> PingResult:
    driver = _driver_for(device, registry, policy, Capability.PING)
    _connected(driver)
    try:
        r = driver.ping(target, count, _context(session, device, registry, target))
    finally:
        driver.disconnect()
    return _ping_result(device, target, r, count)


def _device_trace(session: Session, device: Device, registry: DriverRegistry, target: str,
                  policy: Policy | None) -> TraceResult:
    driver = _driver_for(device, registry, policy, Capability.TRACEROUTE)
    _connected(driver)
    try:
        r = driver.traceroute(target, _context(session, device, registry, target))
    finally:
        driver.disconnect()
    if not r.ok:
        raise ConflictError(f"{device.name}: {r.message}")
    data = dict(r.data or {})
    hops = [Hop(int(h["n"]), h.get("address"), tuple(h.get("rtt_ms") or ()),
                timed_out=h.get("address") is None) for h in data.get("hops") or ()]
    return TraceResult(device.id, target, hops, any(h.address == target for h in hops),
                       raw=str(data.get("raw", "")))


def _device_check_all(session: Session, project: Project, registry: DriverRegistry,
                      actor: str, source: str, policy: Policy | None) -> list[dict[str, Any]]:
    """From one device (the BFW) to every other device of the system, in one session."""
    device = _source(project, source)
    assert device is not None
    driver = _driver_for(device, registry, policy, Capability.PING)
    _connected(driver)
    results: list[dict[str, Any]] = []
    try:
        for d in project.devices:
            if d.id == device.id:
                continue
            where = reach.reach_of(d, registry)
            row: dict[str, Any] = {"device_id": d.id, "address": where.address,
                                   "via": where.via}
            if not where.address:
                results.append({**row, "state": "no_address",
                                "note": where.problem or "No address"})
                continue
            r = driver.ping(where.address, 2,
                            _context(session, device, registry, where.address))
            data = dict(r.data or {}) if r.ok else {}
            received = data.get("received")
            results.append({**row, "sent": 2, "received": received,
                            "rtt_ms": data.get("rtt_ms") or [],
                            "state": "answers" if received else "no_answer",
                            "note": "" if r.ok else r.message})
    finally:
        driver.disconnect()
    audit.record(session, actor, "troubleshoot.check_all", "project", project.id, details={
        "source": source, "devices": len(results),
        "answered": sum(1 for r in results if r["state"] == "answers")})
    return results
