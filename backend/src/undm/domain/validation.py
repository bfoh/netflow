"""Platform-independent validation of device intent."""

from dataclasses import dataclass
from enum import StrEnum

from undm.domain.intent import DeviceIntent


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    path: str = ""


def validate_intent(intent: DeviceIntent) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    seen_vlans: set[int] = set()
    for i, vlan in enumerate(intent.vlans):
        if vlan.vlan_id in seen_vlans:
            issues.append(
                ValidationIssue(
                    Severity.ERROR, "duplicate_vlan", f"VLAN {vlan.vlan_id} defined twice",
                    f"vlans[{i}]",
                )
            )
        seen_vlans.add(vlan.vlan_id)

    seen_ifaces: set[str] = set()
    for i, iface in enumerate(intent.interfaces):
        key = iface.interface.lower()
        if key in seen_ifaces:
            issues.append(
                ValidationIssue(
                    Severity.ERROR, "duplicate_interface",
                    f"Interface {iface.interface} has more than one address entry",
                    f"interfaces[{i}]",
                )
            )
        seen_ifaces.add(key)
        if iface.address.network.prefixlen < 31 and iface.address.ip in (
            iface.address.network.network_address,
            iface.address.network.broadcast_address,
        ):
            issues.append(
                ValidationIssue(
                    Severity.ERROR, "invalid_host_address",
                    f"{iface.address} is a network or broadcast address",
                    f"interfaces[{i}].address",
                )
            )
        svi = iface.svi_vlan
        if svi is not None and svi not in seen_vlans:
            issues.append(
                ValidationIssue(
                    Severity.WARNING, "svi_without_vlan",
                    f"{iface.interface} has an address but VLAN {svi} is not defined",
                    f"interfaces[{i}]",
                )
            )

    nets = [(i, x.address.network) for i, x in enumerate(intent.interfaces)]
    for a in range(len(nets)):
        for b in range(a + 1, len(nets)):
            if nets[a][1].overlaps(nets[b][1]):
                issues.append(
                    ValidationIssue(
                        Severity.ERROR, "overlapping_subnets",
                        f"{nets[a][1]} and {nets[b][1]} overlap on the same device",
                        f"interfaces[{nets[b][0]}]",
                    )
                )

    connected = [x.address.network for x in intent.interfaces]
    for i, route in enumerate(intent.static_routes):
        if connected and not any(route.next_hop in n for n in connected):
            issues.append(
                ValidationIssue(
                    Severity.WARNING, "next_hop_not_connected",
                    f"Next hop {route.next_hop} is not in any subnet defined on this device",
                    f"static_routes[{i}]",
                )
            )
    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity is Severity.ERROR for i in issues)
