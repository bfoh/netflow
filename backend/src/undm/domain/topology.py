"""Topology graph validation.

The graph (devices + links between named interfaces) is the source of truth;
canvas coordinates are layout only. A designed link is intent, never evidence
that a cable exists.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from ipaddress import IPv4Interface

from undm.domain.validation import Severity, ValidationIssue


@dataclass(frozen=True)
class NodeInfo:
    device_id: str
    name: str
    # interface name (lower-case) -> address, from the device intent
    addresses: dict[str, IPv4Interface] = field(default_factory=dict)
    vlans: frozenset[int] = frozenset()


@dataclass(frozen=True)
class LinkInfo:
    link_id: str
    a_device: str
    a_interface: str
    b_device: str
    b_interface: str
    mode: str  # access / trunk / routed
    vlans: tuple[int, ...] = ()


def validate_topology(nodes: list[NodeInfo], links: list[LinkInfo]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_id = {n.device_id: n for n in nodes}

    def add(sev: Severity, code: str, msg: str, path: str) -> None:
        issues.append(ValidationIssue(sev, code, msg, path))

    def label(dev: str, iface: str) -> str:
        return f"{by_id[dev].name if dev in by_id else dev}:{iface}"

    # Interface used by more than one link.
    uses: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ln in links:
        uses[(ln.a_device, ln.a_interface.lower())].append(ln.link_id)
        uses[(ln.b_device, ln.b_interface.lower())].append(ln.link_id)
    for (dev, iface), ids in uses.items():
        if len(ids) > 1:
            add(Severity.ERROR, "interface_used_twice",
                f"{label(dev, iface)} is used by {len(ids)} links", f"links/{ids[1]}")

    for ln in links:
        path = f"links/{ln.link_id}"
        if ln.a_device == ln.b_device:
            add(Severity.ERROR, "self_link", f"link connects {by_id[ln.a_device].name} to itself",
                path)
            continue
        a, b = by_id.get(ln.a_device), by_id.get(ln.b_device)
        if a is None or b is None:
            add(Severity.ERROR, "unknown_device", "link refers to a device outside the project",
                path)
            continue
        if ln.mode == "routed":
            ia = a.addresses.get(ln.a_interface.lower())
            ib = b.addresses.get(ln.b_interface.lower())
            if ia and ib:
                if ia.network != ib.network:
                    add(Severity.ERROR, "subnet_mismatch",
                        f"{label(a.device_id, ln.a_interface)} {ia} and "
                        f"{label(b.device_id, ln.b_interface)} {ib} are in different subnets",
                        path)
            else:
                missing = [label(n.device_id, i) for n, i, addr in
                           ((a, ln.a_interface, ia), (b, ln.b_interface, ib)) if not addr]
                add(Severity.WARNING, "routed_link_without_address",
                    f"routed link: no address in the intent for {', '.join(missing)}", path)
        else:
            if ln.mode == "access" and len(ln.vlans) != 1:
                add(Severity.ERROR, "access_link_vlan_count",
                    "an access link carries exactly one VLAN", path)
            for node in (a, b):
                undefined = sorted(set(ln.vlans) - node.vlans)
                if undefined:
                    add(Severity.WARNING, "vlan_not_defined",
                        f"VLAN(s) {', '.join(map(str, undefined))} on this link are not defined "
                        f"in {node.name}'s intent", path)

    # The same IP address on two interfaces anywhere in the project.
    seen: dict[str, str] = {}
    for n in nodes:
        for iface, addr in n.addresses.items():
            ip = str(addr.ip)
            here = f"{n.name}:{iface}"
            if ip in seen:
                add(Severity.ERROR, "duplicate_ip",
                    f"{ip} is assigned to both {seen[ip]} and {here}", f"devices/{n.device_id}")
            else:
                seen[ip] = here

    if len(nodes) > 1:
        linked = {ln.a_device for ln in links} | {ln.b_device for ln in links}
        for n in nodes:
            if n.device_id not in linked:
                add(Severity.WARNING, "isolated_device", f"{n.name} has no links",
                    f"devices/{n.device_id}")
    return issues
