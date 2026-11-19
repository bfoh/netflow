"""Offline inspection of ArubaOS-Switch (2930F) configuration files (no device contact).

The team's files are complete switch configurations as written by the switch itself
(first line ``; JL260A Configuration Editor; Created on release #WC.16.08.0026``),
with the team's change history in ``;`` comment lines. Today they are uploaded through
the switch's web interface. Everything reported here is read from the file; how the
switch treats a line when the file is loaded is not assumed. Secret values (SNMP
communities, password hashes) are counted, never copied into the report. Comment lines
are not quoted either: they can hold site names and addresses.
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass, field

from undm.drivers.base import ApplyMode, ConfigFileReport

_HEADER = re.compile(r"^; (?P<pn>[A-Z0-9]+) Configuration Editor; Created on release "
                     r"#(?P<release>\S+)")
_MANAGER = re.compile(r"^ip authorized-managers (\S+) (\S+)(?: access (\S+))?"
                      r"(?: access-method (\S+))?")


def _ports(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        if a.isdigit() and (not b or b.isdigit()):
            out.extend(range(int(a), int(b or a) + 1))
    return out


def _span(ports: list[int]) -> str:
    return ", ".join(map(str, sorted(set(ports))))


@dataclass
class Vlan:
    vid: int
    names: list[str] = field(default_factory=list)
    untagged: list[int] = field(default_factory=list)
    tagged: list[int] = field(default_factory=list)
    address: tuple[str, str] | None = None


@dataclass
class SwitchFile:
    hostname: str | None
    product_number: str | None
    release: str | None
    ports: dict[int, bool]  # port -> enabled
    vlans: dict[int, Vlan]
    vlan_order: list[int]
    lines: list[str]

    def management_addresses(self) -> list[tuple[int, str, str]]:
        return [(v.vid, *v.address) for v in self.vlans.values() if v.address]


def parse(text: str) -> SwitchFile:
    lines = text.splitlines()
    head = next((m for ln in lines[:3] if (m := _HEADER.match(ln))), None)
    ports: dict[int, bool] = {}
    vlans: dict[int, Vlan] = {}
    order: list[int] = []
    hostname = None
    block: tuple[str, int] | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if m := re.match(r'^hostname "?([^"]+?)"?$', line):
            hostname = m.group(1)
        if m := re.match(r"^interface (\d+)$", line):
            block = ("interface", int(m.group(1)))
            ports.setdefault(block[1], True)
            continue
        if m := re.match(r"^vlan (\d+)$", line):
            vid = int(m.group(1))
            block = ("vlan", vid)
            vlans.setdefault(vid, Vlan(vid))
            order.append(vid)
            continue
        if line == "exit":
            block = None
            continue
        if block and block[0] == "interface" and line == "disable":
            ports[block[1]] = False
        elif block and block[0] == "vlan":
            v = vlans[block[1]]
            if m := re.match(r'^name "?([^"]*?)"?$', line):
                v.names.append(m.group(1))
            elif m := re.match(r"^untagged (\S+)$", line):
                v.untagged += _ports(m.group(1))
            elif m := re.match(r"^tagged (\S+)$", line):
                v.tagged += _ports(m.group(1))
            elif m := re.match(r"^ip address (\S+) (\S+)$", line):
                v.address = (m.group(1), m.group(2))
    return SwitchFile(hostname, head.group("pn") if head else None,
                      head.group("release") if head else None, ports, vlans, order, lines)


def address_after_loading(text: str, current: str) -> str | None:
    """The address in the file on the same subnet as ``current`` (None if there is none)."""
    try:
        here = ipaddress.ip_address(current)
    except ValueError:
        return None
    for _, address, mask in parse(text).management_addresses():
        try:
            net = ipaddress.ip_network(f"{address}/{mask}", strict=False)
        except ValueError:
            continue
        if here in net:
            return address
    return None


def inspect_aos_switch_file(text: str) -> ConfigFileReport:
    f = parse(text)
    facts: dict[str, str] = {"lines": str(len(f.lines))}
    if not f.product_number and not (f.ports and f.vlans):
        return ConfigFileReport(
            file_type="unknown", summary="Not recognised as an ArubaOS-Switch configuration",
            apply_mode=None, facts=facts,
            problems=("No 'Configuration Editor' header and no 'interface <n>' / 'vlan <id>' "
                      "sections found",))
    notes: list[str] = []
    stmts = [ln.strip() for ln in f.lines if ln.strip() and not ln.lstrip().startswith(";")]
    if f.hostname:
        facts["hostname"] = f.hostname
    if f.product_number:
        facts["product_number"] = f.product_number
    if f.release:
        facts["written_by_release"] = f.release
        notes.append(f"Written by a {f.product_number} on release {f.release}. Use it only on "
                     f"that model; it is loaded as the switch's whole startup configuration.")
    disabled = [p for p, on in f.ports.items() if not on]
    facts["ports"] = str(len(f.ports))
    facts["ports_disabled"] = str(len(disabled))

    # -- where the switch answers after loading ----------------------------------------
    where = []
    for vid, address, mask in f.management_addresses():
        v = f.vlans[vid]
        carried = []
        if v.untagged:
            carried.append("untagged on port " + _span(v.untagged))
        if v.tagged:
            carried.append("tagged on port " + _span(v.tagged))
        where.append(f"VLAN {vid} {address} / {mask}"
                     + (f" ({'; '.join(carried)})" if carried else ""))
    if where:
        facts["management_addresses"] = str(len(where))
        notes.append("After loading, the switch answers at: " + "; ".join(where) + ".")
    managers = []
    for line in stmts:
        if m := _MANAGER.match(line):
            managers.append(f"{m.group(1)} / {m.group(2)} ({m.group(3) or 'manager'}, "
                            f"{m.group(4) or 'all methods'})")
    if managers:
        notes.append("Management is limited to these addresses ('ip authorized-managers'): "
                     + "; ".join(managers) + ". The PC running UNDM must be inside one of "
                     "them after loading.")

    # -- what changes about access ------------------------------------------------------
    if "no telnet-server" in stmts:
        notes.append("Telnet is switched off.")
    if "web-management ssl" in stmts and "no web-management" in stmts:
        notes.append("The web interface becomes HTTPS-only, which needs an HTTPS certificate "
                     "on the switch"
                     + (" (the file's own comments say to create it before loading)"
                        if any(ln.startswith(";") and "certificate" in ln.lower()
                               for ln in f.lines) else "") + ".")
    if "no tftp client" in stmts:
        notes.append("The file switches off the switch's TFTP client: once it is active, the "
                     "switch can no longer fetch firmware or files by TFTP. Upgrade the "
                     "firmware before loading it.")
    if "ip ssh filetransfer" in stmts:
        notes.append("SSH file transfer (SCP/SFTP) is switched on.")
    bare = [ln for ln in stmts if re.fullmatch(r"password (manager|operator)", ln)]
    logins = [ln for ln in stmts if re.match(r"password (manager|operator)\b", ln)]
    if logins:
        notes.append("The file sets the switch's login ('password manager' / 'password "
                     "operator'"
                     + (", here without a value" if bare and len(bare) == len(logins) else "")
                     + "). In the plan choose the login valid after loading, so UNDM can log "
                       "in after the restart.")

    # -- consistency checks (reported, not blocking: the file is loaded this way today) ----
    for vid, count in Counter(f.vlan_order).items():
        if count > 1:
            names = f.vlans[vid].names
            notes.append(f"Check: VLAN {vid} is defined {count} times"
                         + (f" (names {', '.join(repr(n) for n in names)}; the last one wins)"
                            if len(set(names)) > 1 else "") + ".")

    # -- secrets: counted, never shown ---------------------------------------------------
    communities = sum(1 for ln in stmts if ln.startswith("snmp-server community "))
    hashes = sum(1 for ln in stmts
                 if re.match(r"password (manager|operator) \S+", ln) and ln not in bare)
    if communities or hashes:
        facts["secrets"] = str(communities + hashes)
        notes.append(f"Confidential: {communities} SNMP community string(s)"
                     + (f" and {hashes} password value(s)" if hashes else "")
                     + " in the file. Keep it and any copy of it protected.")

    return ConfigFileReport(
        file_type="full_config",
        summary=(f"Complete ArubaOS-Switch configuration ({f.product_number or 'model unknown'}"
                 f", {len(f.ports)} ports" + (f", hostname {f.hostname}" if f.hostname else "")
                 + ")"),
        apply_mode=ApplyMode.REPLACE, facts=facts, notes=tuple(notes), problems=())
