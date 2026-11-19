"""Offline inspection of Black Box switch configuration files (no device contact).

The team loads a complete configuration file through each switch's web interface. Two
formats are in use (product owner, 2026-11-19):

* LIG1014A: the switch's CLI syntax (``hostname``, ``interface GigabitEthernet 1/1``,
  ``interface vlan 168``, ``access management ...``, ``!`` separators, final ``end``);
* LE2700A: an XML export (``<configuration>`` with ``<platform>``, ``<global>`` and
  ``<switch>`` sections, each value in a ``val`` attribute, syntax given in comments).

Everything reported here is read from the file itself; how a switch treats the file when
it is loaded is not assumed. Secret values are never copied into the report.
"""

from __future__ import annotations

import base64
import binascii
import re
import xml.etree.ElementTree as ET

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


def _expand_ports(spec: str) -> set[int]:
    return _vlan_set(spec) if spec and spec != "none" else set()


def _val(node: ET.Element | None, path: str) -> str | None:
    found = node.find(path) if node is not None else None
    return found.get("val") if found is not None else None


_SECRET_ATTR = re.compile(r"(?i)password|secret|community")
_RW_GROUP = re.compile(r"(?i)rw")
_ANY = "0.0.0.0"  # noqa: S104 - an address value read from the file, not a socket bind


def inspect_blackbox_xml(text: str) -> ConfigFileReport:
    """The XML export used for the LE2700A."""
    facts: dict[str, str] = {"lines": str(len(text.splitlines())), "format": "xml"}
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        return ConfigFileReport(
            file_type="unknown", summary="XML file with a document type declaration",
            apply_mode=None, facts=facts,
            problems=("The file declares a document type or entities, which a switch export "
                      "does not; it is not processed",))
    try:
        # Safe here: declarations were refused above, so no entity can be defined or
        # expanded, and ElementTree never fetches external resources.
        root = ET.fromstring(text)  # noqa: S314
    except ET.ParseError as e:
        return ConfigFileReport(file_type="unknown", summary="XML file that cannot be read",
                                apply_mode=None, facts=facts, problems=(f"XML error: {e}",))
    glob, switch, platform = root.find("global"), root.find("switch"), root.find("platform")
    if root.tag != "configuration" or platform is None or (glob is None and switch is None):
        return ConfigFileReport(
            file_type="unknown", summary="Not recognised as a Black Box switch configuration",
            apply_mode=None, facts=facts,
            problems=("Expected <configuration> with <platform> and <global>/<switch> sections",))
    facts.update({k: v for k, v in (("platform_id", _val(platform, "pid")),
                                     ("platform_version", _val(platform, "version"))) if v})
    notes: list[str] = []
    hostname = _val(glob, "system/name")
    if hostname:
        facts["hostname"] = hostname

    # -- ports -------------------------------------------------------------------------
    all_ports: set[int] = set()
    enabled: set[int] = set()
    port_table = switch.find("port/port_table") if switch is not None else None
    for entry in port_table if port_table is not None else []:
        ports = _expand_ports(entry.get("port", ""))
        all_ports |= ports
        if entry.get("state") == "enabled":
            enabled |= ports
    if all_ports:
        facts["ports"] = str(max(all_ports))
        facts["ports_enabled"] = str(len(enabled))

    # -- where the switch can be managed after loading --------------------------------
    ip = glob.find("ip") if glob is not None else None
    addr, mask, vid = _val(ip, "addr"), _val(ip, "mask"), _val(ip, "vid")
    if _val(ip, "dhcp_client") == "enabled":
        notes.append("The switch takes its address by DHCP after loading.")
    elif addr and vid and vid.isdigit():
        members: set[int] = set()
        untagged: set[int] = set()
        vlan = switch.find("vlan") if switch is not None else None
        for entry in vlan.findall("vlan_table/entry") if vlan is not None else []:
            if entry.get("vid") == vid:
                members |= _expand_ports(entry.get("port", ""))
        for entry in vlan.findall("port_table/entry") if vlan is not None else []:
            if entry.get("pvid") == vid and entry.get("tx_tag") in ("untag_all", "untag_pvid"):
                untagged |= _expand_ports(entry.get("port", ""))
        untagged &= members
        tagged = members - untagged
        def ports_text(ports: set[int]) -> str:
            return ", ".join(f"{p}" + ("" if p in enabled or not enabled else " (disabled)")
                             for p in sorted(ports))

        where = []
        if untagged:
            where.append("untagged on port " + ports_text(untagged))
        if tagged:
            where.append("tagged on port " + ports_text(tagged))
        facts["management_addresses"] = "1"
        notes.append(
            f"After loading, the switch answers only at {addr} / {mask or '?'} on VLAN {vid}"
            + (f" ({'; '.join(where)})" if where else " (no port carries that VLAN)")
            + ". The address it had before is gone: to reach it again the PC needs an "
              "address in that subnet on one of those ports.")

    # -- access ------------------------------------------------------------------------
    access = []
    if _val(glob, "ssh/mode"):
        access.append(f"SSH {_val(glob, 'ssh/mode')}")
    if _val(glob, "https/mode"):
        access.append(f"HTTPS {_val(glob, 'https/mode')}"
                      + (f" (redirect from HTTP {_val(glob, 'https/redirect')})"
                         if _val(glob, "https/redirect") else ""))
    logins = [f"{e.get('client')}: {e.get('method')}"
              for e in (glob.findall("auth/client_table/entry") if glob is not None else [])]
    if access or logins:
        notes.append("Access: " + "; ".join(access)
                     + (". Login methods — " + ", ".join(logins) if logins else "") + ".")
    accounts = [e for e in root.iter() if re.search(r"(?i)^(users?|accounts?)$", e.tag)]
    if not accounts:
        notes.append("The file contains no administrator accounts or passwords.")

    # -- SNMP and secrets: described, never shown --------------------------------------
    snmp = glob.find("snmp") if glob is not None else None
    if snmp is not None and _val(snmp, "mode") == "enabled":
        rw_names = {e.get("security_name") for e in snmp.findall("group_table/entry")
                    if _RW_GROUP.search(e.get("group_name", ""))}
        open_rw = [e for e in snmp.findall("community_table/entry")
                   if e.get("community") in rw_names
                   and e.get("source_ip") == _ANY and e.get("source_mask") == _ANY]
        well_known = any(e.get("community") in ("public", "private")
                         for e in snmp.findall("community_table/entry"))
        notes.append(f"SNMP {_val(snmp, 'version') or ''} is on"
                     + ("; a read-write community is accepted from any address" if open_rw
                        else "")
                     + ("; it uses the well-known default community names" if well_known
                        else "") + ".")
    secrets = sum(1 for e in root.iter() for k, v in e.attrib.items()
                  if v and (_SECRET_ATTR.search(k) or (k == "val" and _SECRET_ATTR.search(e.tag))))
    if secrets:
        facts["secrets"] = str(secrets)
        notes.append(f"Confidential: {secrets} community string(s) or password value(s) in the "
                     "file. Keep it and any copy of it protected.")

    return ConfigFileReport(
        file_type="full_config",
        summary=("Complete Black Box switch configuration (XML"
                 + (f", {facts['ports']} ports" if "ports" in facts else "")
                 + (f", hostname {hostname}" if hostname else "") + ")"),
        apply_mode=ApplyMode.REPLACE, facts=facts, notes=tuple(notes), problems=())


def inspect_blackbox_config(text: str) -> ConfigFileReport:
    """Either Black Box format, chosen by content."""
    head = text.lstrip()[:200]
    if head.startswith("<?xml") or head.startswith("<configuration"):
        return inspect_blackbox_xml(text)
    return inspect_blackbox_file(text)
