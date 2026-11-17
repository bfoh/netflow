"""Vendor-neutral configuration intent for a single device.

This first slice covers hostname, VLANs, layer-3 interface addresses and
static routes. Further concepts (access/trunk ports, routing protocols,
security policy, NTP/syslog/AAA, ...) are added incrementally.
"""

import re
from ipaddress import IPv4Address, IPv4Interface, IPv4Network

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VlanIntent(_Model):
    vlan_id: int = Field(ge=1, le=4094)
    name: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None and not _NAME_RE.match(v):
            raise ValueError("VLAN name must be 1-32 chars of letters, digits, '_', '.', '-'")
        return v


class InterfaceAddressIntent(_Model):
    """A layer-3 address on a named interface.

    ``interface`` is the platform's interface name (e.g. ``port1``,
    ``GigabitEthernet1``) or the vendor-neutral SVI form ``vlan<N>``.
    """

    interface: str = Field(min_length=1, max_length=64)
    address: IPv4Interface
    description: str | None = Field(default=None, max_length=80)
    enabled: bool = True

    @property
    def svi_vlan(self) -> int | None:
        m = re.fullmatch(r"vlan(\d{1,4})", self.interface, flags=re.IGNORECASE)
        return int(m.group(1)) if m else None


class StaticRouteIntent(_Model):
    prefix: IPv4Network
    next_hop: IPv4Address
    egress_interface: str | None = None


class DeviceIntent(_Model):
    hostname: str
    vlans: tuple[VlanIntent, ...] = ()
    interfaces: tuple[InterfaceAddressIntent, ...] = ()
    static_routes: tuple[StaticRouteIntent, ...] = ()

    @field_validator("hostname")
    @classmethod
    def _hostname(cls, v: str) -> str:
        if not _HOSTNAME_RE.match(v):
            raise ValueError("hostname must be an RFC 1123 label (letters, digits, hyphens; 1-63)")
        return v
