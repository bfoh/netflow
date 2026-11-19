"""Offline inspection of Black Box switch configuration files (no device contact).

The team loads a complete configuration file through the switch's web interface. The
file uses the switch's CLI syntax (``hostname``, ``interface GigabitEthernet 1/1``,
``interface vlan 168``, ``access management ...``, ``!`` separators, final ``end``).
Everything reported here is read from the file itself; how the switch treats the file
when it is loaded is not assumed. Secret values are never copied into the report.
"""

from __future__ import annotations

import base64
import binascii
import re

from undm.drivers.base import ApplyMode, ConfigFileReport

_PORT = re.compile(r"^interface\s+GigabitEthernet\s+(\d+/\d+)\s*$")
_VLAN_IF = re.compile(r"^interface\s+vlan\s+(\d+)\s*$", re.IGNORECASE)
_USER = re.compile(r"^username\s+(\S+)\s+privilege\s+\d+\s+password\s+(encrypted|unencrypted)"
                   r"\s+(\S+)")
_ACCESS = re.compile(r"^access management\s+(\d+)\s+(\d+)\s+(\S+)(?:\s+to\s+(\S+))?\s*(.*)$")


def _vlan_set(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                out.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.add(int(part))
    return out


def _readable_base64(value: str) -> bool:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return bool(raw) and all(0x20 <= c < 0x7F for c in raw)


def _blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Top-level statements with their indented sub-lines."""
    blocks: list[tuple[str, list[str]]] = []
    for ln in lines:
        if not ln.strip() or ln.strip().startswith("!"):
            continue
        if ln[0] in " \t" and blocks:
            blocks[-1][1].append(ln.strip())
        else:
            blocks.append((ln.strip(), []))
    return blocks


def inspect_blackbox_file(text: str) -> ConfigFileReport:
    lines = text.splitlines()
    blocks = _blocks(lines)
    ports = {m.group(1): body for head, body in blocks if (m := _PORT.match(head))}
    vlan_ifs = {int(m.group(1)): body for head, body in blocks if (m := _VLAN_IF.match(head))}
    facts: dict[str, str] = {"lines": str(len(lines))}
    if not ports and not vlan_ifs:
        return ConfigFileReport(
            file_type="unknown", summary="Not recognised as a Black Box switch configuration",
            apply_mode=None, facts=facts,
            problems=("No 'interface GigabitEthernet <unit>/<port>' or 'interface vlan' "
                      "sections found",))
    notes: list[str] = []
    problems: list[str] = []
    hostname = next((head.split(None, 1)[1] for head, _ in blocks
                     if head.startswith("hostname ") and len(head.split()) > 1), None)
    if hostname:
        facts["hostname"] = hostname
    shut = sorted(p for p, body in ports.items() if "shutdown" in body)
    facts["ports"] = str(len(ports))
    facts["ports_shut_down"] = str(len(shut))
    if not any(head == "end" for head, _ in blocks):
        problems.append("The file does not end with 'end'; it may be incomplete")

    # -- where the switch can be managed after loading -------------------------------------
    access: dict[int, list[str]] = {}
    trunk: dict[int, list[str]] = {}
    for port, body in ports.items():
        mode_trunk = "switchport mode trunk" in body
        for sub in body:
            if not mode_trunk and (m := re.match(r"switchport access vlan (\d+)$", sub)):
                access.setdefault(int(m.group(1)), []).append(port)
            if mode_trunk and (m := re.match(r"switchport trunk allowed vlan (\S+)$", sub)):
                for vid in _vlan_set(m.group(1)):
                    trunk.setdefault(vid, []).append(port)
    addresses = []
    for vid, body in sorted(vlan_ifs.items()):
        m = next((re.match(r"ip address (\S+) (\S+)$", sub) for sub in body
                  if sub.startswith("ip address ")), None)
        if not m:
            continue
        where = []
        if access.get(vid):
            where.append("untagged on port " + ", ".join(sorted(access[vid])))
        if trunk.get(vid):
            where.append("on trunk port " + ", ".join(sorted(trunk[vid])))
        addresses.append(f"VLAN {vid} {m.group(1)} / {m.group(2)}"
                         + (f" ({'; '.join(where)})" if where else " (no port carries it)"))
    if addresses:
        facts["management_addresses"] = str(len(addresses))
        notes.append("After loading, the switch answers at: " + "; ".join(addresses) + ".")

    rules = []
    enabled = False
    for head, _ in blocks:
        if head == "access management":
            enabled = True
        elif m := _ACCESS.match(head):
            services = m.group(5).strip() or "all services"
            span = f"{m.group(3)}–{m.group(4)}" if m.group(4) else m.group(3)
            rules.append(f"VLAN {m.group(2)} {span} ({services})")
    if enabled and rules:
        notes.append("Management access is restricted ('access management') to: "
                     + "; ".join(rules) + ". The PC running UNDM must match one of these "
                     "after loading. Whether SSH is covered by 'telnet' is not confirmed.")
    if any(head == "no ip telnet" for head, _ in blocks):
        notes.append("Telnet is switched off by the file.")
    if any(head == "ip http secure-server" for head, _ in blocks):
        notes.append("The web interface is switched to HTTPS.")

    # -- secrets: described, never shown -----------------------------------------------
    readable = clear = other = 0
    for head, _ in blocks:
        if m := _USER.match(head):
            if m.group(2) == "unencrypted":
                clear += 1
            elif _readable_base64(m.group(3)):
                readable += 1
            else:
                other += 1
    if readable or clear or other:
        parts = []
        if readable:
            parts.append(f"{readable} password(s) marked 'encrypted' that are only base64-"
                         "encoded: anyone with the file can read them")
        if clear:
            parts.append(f"{clear} password(s) in clear text")
        if other:
            parts.append(f"{other} encrypted password(s)")
        notes.append("Confidential: the file contains " + "; ".join(parts)
                     + ". Keep it and any copy of it protected.")
        facts["secrets"] = str(readable + clear + other)

    return ConfigFileReport(
        file_type="full_config",
        summary=(f"Complete Black Box switch configuration ({len(ports)} ports"
                 + (f", hostname {hostname}" if hostname else "") + ")"),
        apply_mode=ApplyMode.REPLACE, facts=facts, notes=tuple(notes), problems=tuple(problems))
