"""Black Box LIG1014A over SSH. EXPERIMENTAL: read-only so far (D-074).

What the switch itself showed (bench, factory-default unit, v00.01.00, 2026-11-24):

* SSH login as ``admin`` (factory: empty password) lands at a bare ``#`` prompt (no
  hostname yet); no new password is demanded.
* ``show version``: MEMORY, FLASH, ``MAC Address``, an **empty** ``Serial Number``,
  ``System Name``, the active and alternate images, and per SID ``Board Type``,
  ``Port Count``, ``Software Version``, ``Build Date``.
* ``show running-config`` starts with ``Building configuration...`` and ends with ``end``.
* ``copy ?``: a source is ``flash:filename``, ``tftp://server/path-and-filename``,
  ``ftp://…``, ``running-config`` or ``startup-config``; file names use letters, digits,
  ``.``, ``-`` and ``_``, at most 63 characters, not starting with ``-``.
* ``reload ?``: ``cold`` (restart) and ``defaults`` (factory settings without restarting).

Netmiko type ``generic`` sends nothing at login, so no paging or terminal command whose
syntax is unconfirmed on this switch is ever sent. Every command is read up to the prompt
by UNDM's own reader (a prompt of a single ``#`` would end Netmiko's default read at the
first ``#`` of the output). The unit reports no serial number, so its base MAC address is
its identity: it is what UNDM compares after a restart.

Loading a configuration file is not built yet: the destination syntax of ``copy`` with a
TFTP source, what ``reload cold`` asks, and whether SSH is allowed by the team's
``access management`` rules after loading are to be confirmed on the bench (Q-28, Q-27).
"""

from __future__ import annotations

import re
import time
from typing import ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigFileReport,
    DeviceFacts,
    DriverInfo,
    DriverMaturity,
    OperationResult,
)
from undm.drivers.blackbox.config_files import inspect_blackbox_config
from undm.drivers.ssh.base import SshCliDriver
from undm.security.redaction import redact_text

Op = DeviceOperation


# The switch's page prompt, as it showed it (bench, v00.01.00, 2026-11-24).
_MORE = re.compile(r"-- ?more ?--, next page: Space, continue: g, quit: \^C[ \t]*")
# What a terminal uses to erase a line: CR + spaces + CR, backspaces, ANSI sequences.
_ERASE = re.compile(r"\r[ \t]*\r|(?:\x08 \x08)+|\x08|\x1b\[[0-9;?]*[ -/]*[@-~]")


def _clean(output: str) -> str:
    return _ERASE.sub("", output).replace("\r", "")


def _field(name: str, text: str) -> str:
    m = re.search(rf"^\s*{re.escape(name)}\s*:[ \t]*(.*?)\s*$", text, re.M)
    return m.group(1) if m else ""


class BlackBoxLig1014aSsh(SshCliDriver):
    """Black Box LIG1014A industrial switch, SSH CLI."""

    netmiko_device_type = "generic"
    facts_commands = ("show version",)
    running_config_command = "show running-config"
    skip_line_patterns = (r"^\s*!", r"^Building configuration")
    # 'show version' layout checked against the switch's own output (bench, 2026-11-24).
    parser_validated_on = ("LIG1014A v00.01.00",)
    # Its SSH server offers no host key type that paramiko 5 still has ("Incompatible ssh
    # peer (no acceptable host key)", bench 2026-11-24); needs paramiko 3.5 (D-075).
    legacy_ssh_algorithms = True
    command_timeout: ClassVar[float] = 60.0
    command_quiet: ClassVar[float] = 20.0
    info = DriverInfo(
        driver_id="ssh.blackbox.lig1014a",
        vendor="Black Box",
        platform="blackbox_lig1014a",
        os_family="Black Box LIG1014A",
        description="Black Box LIG1014A over SSH CLI. Experimental: connection, device "
                    "information and backup only.",
        simulated=False,
        capabilities=frozenset({Capability.SSH, Capability.CONFIGURATION_BACKUP}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "Read-only: Test connection, Retrieve information ('show version') and backup "
            "('show running-config'). Nothing is sent at login (Netmiko 'generic').",
            "The unit reports no serial number; its base MAC address is used as its "
            "identity.",
            "Loading the team's configuration file is not built yet (to confirm on the "
            "bench: 'copy' with a TFTP source into the startup configuration, what "
            "'reload cold' asks, SSH after loading).",
        ),
    )

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        return inspect_blackbox_config(text)

    # -- reading ----------------------------------------------------------------------
    def _prompt_pattern(self) -> str:
        # Factory: '#'; with a hostname: '<hostname>#'. A line holding no other '#'.
        return r"(?:^|\n)[^\n#]*#\s*$"

    def _send(self, command: str) -> str:
        """Run a read command and return its output (echo, pager and prompt removed).

        At the switch's page prompt ("-- more --, next page: Space, continue: g, quit: ^C",
        bench 2026-11-24) UNDM presses 'g', the switch's own option for the rest of the
        output without further pauses; nothing else is ever answered."""
        conn = self._conn
        prompt = re.compile(self._prompt_pattern())
        conn.clear_buffer()
        conn.write_channel(command + str(getattr(conn, "RETURN", "\n")))
        output, pages = "", 0
        start = last = time.monotonic()
        while True:
            chunk = str(conn.read_channel() or "")
            now = time.monotonic()
            if chunk:
                output, last = output + chunk, now
                if _MORE.search(output):
                    pages += 1
                    if pages > 3:  # 'g' leaves no further pauses: something else is going on
                        raise RuntimeError(f"the switch kept pausing the output of '{command}'")
                    output = _MORE.sub("", output)
                    conn.write_channel("g")
                    continue
                if prompt.search(output):
                    break
                continue
            if now - start > self.command_timeout or now - last > self.command_quiet:
                shown = " ".join(redact_text(output).split())[-300:]
                raise RuntimeError(
                    f"no prompt after '{command}' (no output for {self.command_quiet:.0f} s); "
                    f"it showed: “{shown}”. The switch may be waiting for an answer UNDM "
                    "does not give.")
            time.sleep(self.poll_interval)
        lines = _clean(output).split("\n")
        if lines and command in lines[0]:
            lines = lines[1:]  # the echo
        if lines and re.fullmatch(r"[^#]*#\s*", lines[-1]):
            lines = lines[:-1]  # the prompt
        return "\n".join(lines).strip("\n")

    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        text = outputs.get("show version", "")
        model = _field("Board Type", text)
        mac = _field("MAC Address", text)
        if not model or not mac:
            raise ValueError("'show version' did not show 'Board Type' and 'MAC Address' "
                             "as the LIG1014A does")
        serial = _field("Serial Number", text)
        return DeviceFacts(
            hostname=_field("System Name", text) or prompt.strip().rstrip("#").strip(),
            vendor="Black Box",
            model=model,
            os_version=_field("Software Version", text) or _field("Version", text),
            serial_number=serial or mac,
            extra={
                "identity": ("serial number" if serial
                             else "base MAC address (the unit reports no serial number)"),
                "mac_address": mac,
                "port_count": _field("Port Count", text),
                "active_image": _active_image(text),
                "alternate_image": _alternate_image(text),
            },
        )

    def get_running_configuration(self) -> OperationResult:
        result = super().get_running_configuration()
        if result.ok:
            text = str(result.data)
            body = [ln for ln in text.splitlines() if not ln.startswith("Building configuration")]
            if not any(ln.strip() == "end" for ln in body[-3:]):
                return OperationResult.failed(
                    Op.GET_RUNNING_CONFIGURATION,
                    "The configuration read from the switch is incomplete (it does not end "
                    "with 'end'); nothing was stored.")
            return OperationResult.success(result.operation, "\n".join(body).strip("\n"))
        return result

    # -- changes: not built yet -------------------------------------------------------
    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        return OperationResult.unsupported(
            Op.APPLY_CONFIGURATION,
            "Loading a configuration on the LIG1014A is not built yet (the load procedure "
            "is still being confirmed on the bench)")

    def save_configuration(self) -> OperationResult:
        return OperationResult.unsupported(Op.SAVE_CONFIGURATION,
                                           "Not built yet for the LIG1014A")


def _image(section: str, text: str) -> str:
    m = re.search(rf"^{section}\s*\n-+\s*\n(.*?)(?:\n\s*\n|\Z)", text, re.M | re.S)
    if not m:
        return ""
    return f"{_field('Image', m.group(1))} {_field('Version', m.group(1))}".strip()


def _active_image(text: str) -> str:
    return _image("Active Image", text)


def _alternate_image(text: str) -> str:
    return _image("Alternate Image", text)
