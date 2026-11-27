"""The modem's configuration file (Nokia 7705 SAR-Hmc, D-116): what UNDM sends over the
console, line by line. Pure functions: no console, no database.

The team's file is the unit's own configuration export (``# TiMOS-…`` header, ``exit all``,
``configure`` and the indented configuration, three single ``config …`` lines, then
``admin save``). The team pastes it on the console after the first access (product owner,
2026-11-26). UNDM sends the configuration lines as written, one at a time, and does not send:
- comment lines (``#…``) and blank lines: they configure nothing;
- ``echo`` lines: they only print a heading;
- ``admin save``: UNDM saves once every line has been accepted, and checks the answer.
That choice is UNDM's (nothing is sent that the team's paste would have needed); how the
unit takes each line is shown by the bench run (Q-58).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from undm.drivers.base import (
    ApplyMode,
    ConfigFileReport,
    FileAddress,
    FileAddresses,
    address_range,
)

SLOT = "${admin_password}"  # the template's password slot (D-114)
_COMMENT = re.compile(r"^\s*#")
_ECHO = re.compile(r"^\s*echo(?:\s|$)")
_SAVE = re.compile(r"^\s*admin\s+save\b")
_PASSWORD = re.compile(r'^(\s*password\s+)"([^"]*)"(.*)$')
_NAME = re.compile(r'^\s+name\s+"([^"]+)"\s*$')
_MARKER = re.compile(r"\$\{[a-z0-9_]+\}")


@dataclass
class LoadPlan:
    """The lines to send: (line number in the file, text)."""

    lines: list[tuple[int, str]] = field(default_factory=list)
    skipped: dict[str, int] = field(
        default_factory=lambda: {"comment": 0, "blank": 0, "echo": 0, "save": 0})
    system_name: str | None = None
    password_slot: bool = False  # the password comes from the modem's login
    password_lines: int = 0
    markers: list[str] = field(default_factory=list)  # UNDM markers left (not a ready file)


def plan_load(text: str) -> LoadPlan:
    out = LoadPlan()
    in_configure = False
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.rstrip()
        if not line.strip():
            out.skipped["blank"] += 1
            continue
        if _COMMENT.match(line):
            out.skipped["comment"] += 1
            continue
        if _ECHO.match(line):
            out.skipped["echo"] += 1
            continue
        if _SAVE.match(line):
            out.skipped["save"] += 1
            continue
        stripped = line.strip()
        if stripped == "configure":
            in_configure = True
        elif stripped == "exit all":
            in_configure = False
        name = _NAME.match(line)
        if in_configure and name and out.system_name is None:
            out.system_name = name.group(1)
        password = _PASSWORD.match(line)
        if password:
            out.password_lines += 1
            out.password_slot = out.password_slot or password.group(2) == SLOT
        out.markers += [m for m in _MARKER.findall(line) if m != SLOT and m not in out.markers]
        out.lines.append((n, line))
    return out


_INTERFACE = re.compile(r'^(\s*)interface\s+"([^"]+)"')
_ADDRESS = re.compile(r"^\s+address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)\b")


def file_addresses(text: str) -> FileAddresses:
    """The addresses the file gives the modem's interfaces ('interface "<name>"', then
    'address a.b.c.d/nn' under it), with line numbers (D-125). The boot options' address
    is not in this file."""
    addresses: list[FileAddress] = []
    current: tuple[str, int] | None = None  # (name, indent)
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if _COMMENT.match(raw) or not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        if m := _INTERFACE.match(raw):
            current = (m.group(2), indent)
        elif current and raw.strip() == "exit" and indent <= current[1]:
            current = None
        elif current and (m := _ADDRESS.match(raw)):
            span = address_range(m.group(1), m.group(2))
            if span:
                addresses.append(FileAddress(m.group(1), span[2],
                                             f'interface "{current[0]}"', n))
    return FileAddresses(tuple(addresses))


def fill_password(text: str, password: str) -> str:
    """The template's password slot, filled with the modem login's password."""
    return text.replace(f'"{SLOT}"', f'"{password}"')


def literal_passwords(text: str) -> list[str]:
    """Passwords written in the file itself (not the slot). Never shown."""
    return [m.group(2) for raw in text.splitlines()
            if (m := _PASSWORD.match(raw.rstrip())) and m.group(2) != SLOT]


def is_sros_configuration(text: str) -> bool:
    lines = {ln.strip() for ln in text.splitlines()}
    return "configure" in lines and "exit all" in lines


def inspect_sros_file(text: str) -> ConfigFileReport | None:
    if not is_sros_configuration(text):
        return None
    plan = plan_load(text)
    notes = [
        f"UNDM sends its {len(plan.lines)} configuration lines over the console one at a time "
        "and stops at the first line the modem refuses; nothing is saved then.",
        "Not sent: " + ", ".join(f"{n} {what}" for what, n in (
            ("comment line(s)", plan.skipped["comment"]), ("echo line(s)", plan.skipped["echo"]),
            ("'admin save'", plan.skipped["save"])) if n)
        + ". UNDM saves with 'admin save' once every line is accepted.",
    ]
    if plan.password_slot:
        notes.append("Its admin password comes from the modem's login in UNDM.")
    elif plan.password_lines:
        notes.append("It sets the admin password written in it: UNDM loads it only if that is "
                     "the password of the modem's login.")
    problems = []
    if plan.markers:
        problems.append(f"It still holds {', '.join(plan.markers)}: generate it for the "
                        "system's zone and system first.")
    facts = {"lines to send": str(len(plan.lines))}
    if plan.system_name:
        facts["system name"] = plan.system_name
    return ConfigFileReport(
        file_type="cli_script",
        summary="Nokia SR OS configuration (7705 SAR, classic CLI), loaded over the console",
        apply_mode=ApplyMode.MERGE, facts=facts, notes=tuple(notes), problems=tuple(problems))
