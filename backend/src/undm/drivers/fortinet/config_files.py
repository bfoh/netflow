"""Offline inspection of FortiOS configuration files (no device contact).

Two kinds of file are used when a FortiGate is staged, and they are applied in
different ways:

* a **full backup** - starts with a ``#config-version=...`` header line written
  by FortiOS. It is restored as a whole (it replaces the configuration);
* a **CLI script** - plain ``config / edit / set / next / end`` statements, the
  kind an engineer pastes into the CLI. It changes what it names and leaves the
  rest alone.

Everything reported here is read from the file itself. Nothing is assumed about
how a particular FortiOS release behaves; where the file alone cannot tell, the
note says so. Secret values are counted, never copied into the report.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from undm.drivers.base import ApplyMode, ConfigFileReport, SecretSlot

# "#config-version=FG101F-7.2.7-FW-build1577-240131:opmode=0:vdom=1:user=admin"
_HEADER = re.compile(
    r"^#config-version=(?P<code>[A-Za-z0-9]+)-(?P<version>\d+(?:\.\d+)+)-FW-build(?P<build>\d+)"
    r"(?:-\d+)?(?P<flags>(?::[A-Za-z_]+=[^:\s]*)*)\s*$")
# Statements that only describe configuration. Anything else in a script (for example
# "execute ...") acts immediately or may ask a question, so it is pointed out.
_CONFIG_VERBS = frozenset({
    "config", "edit", "set", "unset", "next", "end", "append", "select", "unselect",
    "clear", "delete", "purge", "move", "rename", "clone", "abort",
})
_SECRET_SETTING = re.compile(
    r"^set\s+(?:password|passwd|psksecret|secret|key|auth-pwd|priv-pwd|ppk-secret|"
    r"group-password|secondary-secret|tertiary-secret)\s+(?P<value>.+)$")
_UNESCAPED_QUOTE = re.compile(r'(?<!\\)"')


def _statements(text: str) -> list[tuple[int, str]]:
    """(line number, statement) for every line that is a statement.

    Skips blank lines, ``#`` comments and the continuation lines of multi-line
    quoted values (certificates and keys in full backups).
    """
    return [(number, line) for number, line, _ in _statements_with_flags(text)]


def _statements_with_flags(text: str) -> list[tuple[int, str, bool]]:
    """Like ``_statements``, plus whether the statement's value continues on later lines."""
    out: list[tuple[int, str, bool]] = []
    in_string = False
    for number, raw in enumerate(text.splitlines(), start=1):
        quotes = len(_UNESCAPED_QUOTE.findall(raw))
        if in_string:
            in_string = quotes % 2 == 0
            continue
        line = raw.strip()
        multi_line = quotes % 2 == 1
        if multi_line:
            in_string = True
        if line and not line.startswith("#"):
            out.append((number, line, multi_line))
    return out


def is_secret_setting(statement: str) -> bool:
    """True for a 'set <secret> <value>' statement (FortiOS displays these encrypted)."""
    return bool(_SECRET_SETTING.match(statement.strip()))


def script_statements(text: str) -> list[tuple[int, str]]:
    """The statements a CLI script sends, in order (comments and blank lines removed)."""
    return _statements(text)


def configured_hostname(text: str) -> str | None:
    """The hostname a file sets in 'config system global' (last one wins), if any."""
    blocks: list[str] = []
    found: str | None = None
    for _, line in _statements(text):
        verb = line.split()[0]
        if verb == "config":
            blocks.append(line)
        elif verb == "end" and blocks:
            blocks.pop()
        elif blocks and blocks[-1] == "config system global":
            m = re.match(r'set\s+hostname\s+"?([^"]+?)"?\s*$', line)
            if m:
                found = m.group(1)
    return found


def _name(text: str) -> str:
    return text.strip().strip('"')


def secret_slots(text: str) -> tuple[SecretSlot, ...]:
    """Secret settings whose value is written in clear text (candidates for replacement)."""
    path: list[tuple[str, str]] = []  # (kind, name)
    slots: list[SecretSlot] = []
    for number, line in _statements(text):
        verb, _, rest = line.partition(" ")
        if verb == "config":
            path.append(("config", rest.strip()))
        elif verb == "edit":
            path.append(("edit", _name(rest)))
        elif verb == "next":
            if path and path[-1][0] == "edit":
                path.pop()
        elif verb == "end":
            while path and path.pop()[0] != "config":
                pass
        elif (m := _SECRET_SETTING.match(line)) and not m.group("value").startswith("ENC "):
            setting = line.split()[1]
            slot_id = " > ".join([name for _, name in path] + [setting])
            slots.append(SecretSlot(slot_id, setting, number))
    return tuple(slots)


def inspect_fortios_file(text: str) -> ConfigFileReport:
    lines = text.splitlines()
    header = next((m for ln in lines[:5] if (m := _HEADER.match(ln.strip()))), None)
    statements = _statements(text)
    facts: dict[str, str] = {"lines": str(len(lines)), "statements": str(len(statements))}
    notes: list[str] = []
    problems: list[str] = []

    # -- structure: every block that is opened must be closed --------------------------
    stack: list[str] = []
    leading_end = False
    seen_config = False
    for number, line in statements:
        verb = line.split()[0]
        if verb == "config":
            stack.append("config")
            seen_config = True
        elif verb == "edit":
            if "config" not in stack:
                problems.append(f"line {number}: 'edit' outside any 'config' block")
            stack.append("edit")
        elif verb == "next":
            if stack and stack[-1] == "edit":
                stack.pop()
            else:
                problems.append(f"line {number}: 'next' without an open 'edit'")
        elif verb == "end":
            if "config" not in stack:
                if not seen_config and not leading_end:
                    leading_end = True  # a deliberate "leave whatever is open" first line
                else:
                    problems.append(f"line {number}: 'end' without an open 'config' block")
                continue
            while stack.pop() != "config":  # 'end' also closes an 'edit' left open
                pass
    if stack:
        problems.append(f"{stack.count('config')} 'config' block(s) are never closed with 'end'")
    if len(problems) > 8:
        problems = [*problems[:8], f"... and {len(problems) - 8} more structure problem(s)"]

    # -- secrets: counted, never shown ---------------------------------------------------
    clear_text = encrypted = 0
    for _, line in statements:
        m = _SECRET_SETTING.match(line)
        if m:
            if m.group("value").startswith("ENC "):
                encrypted += 1
            else:
                clear_text += 1
    private_keys = text.count("PRIVATE KEY-----") // 2
    if clear_text or encrypted or private_keys:
        parts = [f"{n} {label}" for n, label in (
            (clear_text, "secret(s) in clear text"), (encrypted, "encrypted secret(s)"),
            (private_keys, "private key(s)")) if n]
        notes.append("Confidential: the file contains " + ", ".join(parts)
                     + ". Keep it and any copy or backup of it protected.")
        facts["secrets"] = str(clear_text + encrypted + private_keys)

    verbs = {line.split()[0] for _, line in statements}
    uses_vdoms = any(line in ("config global", "config vdom") for _, line in statements)

    if header:
        flags = dict(f.split("=", 1) for f in header.group("flags").split(":") if "=" in f)
        facts.update(platform_code=header.group("code"), written_by_version=header.group("version"),
                     build=header.group("build"))
        if "vdom" in flags:
            facts["vdom_mode"] = "multi-vdom" if flags["vdom"] == "1" else "single"
        notes.insert(0, (
            f"Written by FortiOS {facts['written_by_version']} (build {facts['build']}) on a unit "
            f"with platform code {facts['platform_code']}. Use it only on that model, and "
            "confirm with your procedure whether it is restored before or after a firmware "
            "upgrade."))
        notes.insert(1, (
            "It is restored as a whole: it replaces the entire configuration, including "
            "administrator accounts and interface addresses. FortiOS is expected to restart "
            "afterwards (to be confirmed on the bench)."))
        mode = facts.get("vdom_mode")
        return ConfigFileReport(
            file_type="full_backup",
            summary=(f"Full FortiOS configuration backup ({facts['platform_code']}, FortiOS "
                     f"{facts['written_by_version']}"
                     + (f", {mode}" if mode else "") + ")"),
            apply_mode=ApplyMode.REPLACE, facts=facts, notes=tuple(notes),
            problems=tuple(problems))

    if not verbs & {"config", "set", "edit"}:
        return ConfigFileReport(
            file_type="unknown", summary="Not recognised as a FortiOS configuration file",
            apply_mode=None, facts=facts,
            problems=("No FortiOS backup header and no 'config' / 'set' statements found",))

    if leading_end:
        notes.append("Starts with a bare 'end' (to leave any block left open). FortiOS answers "
                     "that line with an error message, which is expected.")
    if uses_vdoms:
        facts["vdom_mode"] = "multi-vdom"
        notes.append("Uses 'config global' / 'config vdom': the firewall must already be in "
                     "multi-VDOM mode (for example from a base configuration restored first).")
    if any(re.match(r"set\s+hostname\b", line) for _, line in statements):
        notes.append("Changes the hostname, so the CLI prompt changes while the script runs.")
    trusted = sorted({line.split(None, 2)[2] for _, line in statements
                      if re.match(r"set\s+trusthost\d+\s+\S", line)})
    if trusted:
        notes.append("Restricts administrator logins to trusted networks ("
                     + "; ".join(trusted) + "). The PC running UNDM must be inside one of them "
                     "or it loses access when that line is applied.")
    block: list[str] = []
    touches_mgmt = False
    for _, line in statements:
        verb = line.split()[0]
        if verb == "config":
            block.append(line)
        elif verb == "end" and block:
            block.pop()
        elif verb == "edit" and block and block[-1] == "config system interface" \
                and line.split(None, 1)[1].strip('"') == "mgmt":
            touches_mgmt = True
    if touches_mgmt:
        notes.append("Changes the 'mgmt' interface: the address UNDM uses to reach the firewall "
                     "may change while the script runs.")
    other = [(n, line) for n, line in statements if line.split()[0] not in _CONFIG_VERBS]
    if other:
        number, line = other[0]
        notes.append(f"{len(other)} line(s) are not configuration statements (first: line "
                     f"{number}, '{line.split()[0]} ...'). Such commands act immediately or may "
                     "ask a question; review them.")
    removals = sum(1 for _, line in statements if line.split()[0] in ("delete", "purge"))
    if removals:
        notes.append(f"{removals} statement(s) delete existing configuration ('delete'/'purge').")
    multi_line = sum(1 for _, _, flag in _statements_with_flags(text) if flag)
    if multi_line:
        facts["multi_line_values"] = str(multi_line)
        notes.append(f"{multi_line} value(s) continue over several lines (certificates or keys).")
    slots = secret_slots(text)
    if slots:
        notes.append("Secret settings whose value can be supplied from the credential store "
                     "when the file is sent: "
                     + "; ".join(f"line {slot.line} ({slot.setting})" for slot in slots) + ".")
    return ConfigFileReport(
        file_type="cli_script",
        summary=f"FortiOS CLI script ({len(statements)} statements"
                + (", multi-VDOM" if uses_vdoms else "") + ")",
        apply_mode=ApplyMode.MERGE, facts=facts, notes=tuple(notes), problems=tuple(problems),
        secret_slots=slots)


def unsafe_cli_value(value: str) -> str | None:
    """Why a secret cannot be typed into the FortiOS CLI as a quoted value, if it cannot."""
    if not value:
        return "is empty"
    if len(value) > 128:
        return "is longer than 128 characters"
    if any(ord(c) < 0x20 or ord(c) > 0x7E for c in value):
        return "contains a non-printable or non-ASCII character"
    if any(c in value for c in '"\\?'):
        return ('contains " or \\ or ?, which UNDM cannot type safely into the FortiOS CLI '
                "yet ('?' opens the CLI help)")
    return None


def insert_secret_values(config: str, secrets: Mapping[str, str],
                         mask: str | None = None) -> str:
    """The script with each secret slot's value replaced (quoted) by the given value.

    With ``mask`` the slot gets ``ENC <mask>`` instead of the value (for simulations,
    which must never hold the real value). Raises ValueError for an unknown slot, a
    file that is not a script, or a value that cannot be typed safely.
    """
    if not secrets:
        return config
    report = inspect_fortios_file(config)
    if report.file_type != "cli_script":
        raise ValueError("Secret values can only be inserted into a CLI script")
    slots = {slot.slot_id: slot for slot in report.secret_slots}
    unknown = sorted(set(secrets) - set(slots))
    if unknown:
        raise ValueError(f"The file has no secret setting {', '.join(unknown)}")
    lines = config.splitlines(keepends=True)
    for slot_id, value in secrets.items():
        slot = slots[slot_id]
        problem = unsafe_cli_value(value)
        if problem:
            raise ValueError(f"The value for {slot.setting} (line {slot.line}) {problem}")
        m = re.match(r"^(\s*set\s+\S+\s+).*?(\r?\n)?$", lines[slot.line - 1])
        assert m is not None  # slots are only made from 'set <setting> <value>' lines
        shown = f"ENC {mask}" if mask is not None else f'"{value}"'
        lines[slot.line - 1] = f"{m.group(1)}{shown}{m.group(2) or ''}"
    return "".join(lines)
