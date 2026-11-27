"""Ping and traceroute results, and the one rule for what may be pinged (D-128). Pure: no
programs, no devices, no database.

A target is one IPv4 address typed or chosen by a person: never a name, a range or a
network, so a request cannot turn into a scan (SECURITY_BOUNDARIES)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field


class TargetError(ValueError):
    """Not an address UNDM pings."""


def check_target(text: str, prefix: int | None = None) -> str:
    """One IPv4 unicast address; ``prefix`` (when known) also refuses its network's
    broadcast and network addresses."""
    value = text.strip()
    if not value or value.startswith("-") or any(c in value for c in "/ ,*") \
            or value.count(".") != 3:
        raise TargetError(f"'{text.strip()[:40]}' is not one IPv4 address (for example "
                          "198.51.100.10): names, ranges and networks are not pinged")
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError as e:
        raise TargetError(f"'{value[:40]}' is not an IPv4 address") from e
    if ip.is_unspecified or ip == ipaddress.IPv4Address("255.255.255.255") \
            or ip.is_multicast or ip.is_reserved:
        raise TargetError(f"{ip} is not a device's address (broadcast, multicast or reserved)")
    if prefix is not None and prefix < 31:
        net = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
        if ip in (net.network_address, net.broadcast_address):
            raise TargetError(f"{ip} is the network or broadcast address of {net}")
    return str(ip)


@dataclass(frozen=True)
class PingResult:
    source: str  # "pc" or a device id
    target: str
    sent: int
    received: int
    rtt_ms: tuple[float, ...] = ()
    simulated: bool = False
    raw: str = ""
    note: str = ""

    @property
    def answered(self) -> bool:
        return self.received > 0


@dataclass
class Hop:
    n: int
    address: str | None  # None: no answer at this hop
    rtt_ms: tuple[float | None, ...] = ()
    timed_out: bool = False
    # The device of the system that has this address, when exactly one has it.
    device_id: str | None = None
    interface: str | None = None
    # Devices that share the address (two 2930F at 192.168.1.1 on the bench): no guess.
    candidates: list[str] = field(default_factory=list)


@dataclass
class TraceResult:
    source: str
    target: str
    hops: list[Hop]
    reached: bool
    simulated: bool = False
    raw: str = ""
    note: str = ""


@dataclass(frozen=True)
class KnownAddress:
    """An address of a device of the system, and where it sits on it."""

    device_id: str
    address: str
    interface: str | None = None


def match_hops(hops: list[Hop], known: list[KnownAddress]) -> list[Hop]:
    """Name each hop's device when exactly one device of the system has its address; when
    several have it, list them as candidates and name none."""
    for hop in hops:
        if hop.address is None:
            continue
        owners: dict[str, KnownAddress] = {}
        for k in known:
            if k.address == hop.address:
                owners.setdefault(k.device_id, k)
        if len(owners) == 1:
            only = next(iter(owners.values()))
            hop.device_id, hop.interface = only.device_id, only.interface
        elif owners:
            hop.candidates = sorted(owners)
    return hops
