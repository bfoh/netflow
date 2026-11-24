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

Loading the team's file (D-077), from the switch's help and the bench: ``copy
tftp://<pc>/<file> ?`` lists ``startup-config`` as a destination; ``reload cold`` asks
nothing, prints "% Cold reload in progress, please stand by." (the prompt may still follow)
and the session closes; error replies start with ``%``. Whether SSH is still allowed by
the file's ``access management`` rules after loading is shown by the first real load
(Q-27).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
import time
from pathlib import Path
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
    load_timeout: ClassVar[float] = 300.0  # TFTP fetch of the file into the startup config
    command_quiet: ClassVar[float] = 20.0
    info = DriverInfo(
        driver_id="ssh.blackbox.lig1014a",
        vendor="Black Box",
        platform="blackbox_lig1014a",
        os_family="Black Box LIG1014A",
        description="Black Box LIG1014A over SSH CLI. Experimental: connection, device "
                    "information, backup; loading a complete file (not yet run on hardware).",
        simulated=False,
        capabilities=frozenset({Capability.SSH, Capability.CONFIGURATION_BACKUP,
                                Capability.CONFIGURATION_APPLY,
                                Capability.CONFIGURATION_REPLACE}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "Test connection, Retrieve information ('show version') and backup ('show "
            "running-config') checked on a factory unit (v00.01.00). Nothing is sent at login "
            "(Netmiko 'generic'); long output continues with 'g' at the switch's page prompt.",
            "The unit reports no serial number; its base MAC address is used as its "
            "identity.",
            "Loading the team's complete file (replace mode): the switch fetches it by TFTP "
            "into its startup configuration ('copy tftp://<pc>/<file> startup-config'), then "
            "'reload cold'; UNDM waits, logs in (login after loading), checks the MAC address, "
            "the hostname and the file's lines. Not yet run on hardware.",
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
        return _answer(output, command)

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

    # -- loading the team's file (D-077) ------------------------------------------------
    @classmethod
    def needs_file_server(cls, kind: str, mode: ApplyMode | None = None) -> bool:
        return kind == "configuration" and mode is ApplyMode.REPLACE

    def restart_notice(self, mode: ApplyMode) -> str | None:
        if mode is not ApplyMode.REPLACE:
            return None
        return ("loading the file: the switch fetches it from this PC into its startup "
                "configuration and restarts with it ('reload cold'). Expect a few minutes "
                "without answers; UNDM continues by itself")

    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        """Complete file only: TFTP into the startup configuration, then 'reload cold'."""
        op = Op.APPLY_CONFIGURATION
        if mode is not ApplyMode.REPLACE:
            return OperationResult.unsupported(
                op, "The LIG1014A takes the team's file as a whole (replace mode) only")
        if r := self._need(op):
            return r
        report = inspect_blackbox_config(config)
        if report.file_type != "full_config" or report.facts.get("ports") is None:
            return OperationResult.failed(
                op, "Replace mode needs a complete LIG1014A configuration file (CLI text)")
        files = self.file_server
        if files is None:
            return OperationResult.failed(op, "No file server is available for this job")
        client = self.target.management_address
        # File names the switch accepts ('copy ?'): letters, digits, . - _; at most 63.
        name = f"undm-{hashlib.sha256(config.encode()).hexdigest()[:10]}.txt"

        def fetching(_: str) -> bool:
            record = files.last_transfer(name, client)
            return record is not None and not record.completed and not record.error

        fd, tmp = tempfile.mkstemp(prefix="undm-config-", suffix=".txt")
        talk = None
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(config)
            server_ip = files.offer(Path(tmp), name, client)
            talk = self._dialogue(
                f"copy tftp://{server_ip}/{name} startup-config", [],
                timeout=self.load_timeout, idle_timeout=self.command_quiet,
                patient=fetching, prompt_ok=lambda out: not fetching(out))
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        finally:
            files.withdraw(name)  # a fetch still running is cut off (D-063)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        assert talk is not None
        transfer = self._settled_transfer(name)
        reply = _answer(talk.output)
        diagnostics: dict[str, object] = {
            "device_output": " ".join(redact_text(reply).split())[-600:]}
        if transfer is None:
            return OperationResult.failed(
                op, "The switch did not request the file from UNDM's TFTP server "
                    f"({talk.detail or 'it returned to its prompt'}). Its answer is below; "
                    "check this PC's firewall (inbound UDP 69). Nothing was changed.",
                diagnostics)
        if not transfer.completed:
            return OperationResult.failed(
                op, f"Transfer incomplete ({transfer.bytes_sent} of {transfer.size} bytes). "
                    "The switch was not restarted.", diagnostics)
        if talk.ended != "prompt":
            return OperationResult.failed(
                op, f"The switch fetched the file but did not return to its prompt "
                    f"({talk.detail or talk.ended}). It was not restarted; check it.",
                diagnostics)
        complaint = _complaint(reply)
        if complaint or not _IMPORTED.search(reply):
            why = (f"refused it: \"{complaint}\"" if complaint
                   else "did not confirm it (no \"Import Done!\")")
            return OperationResult.failed(
                op, f"The switch fetched the file but {why}. It was not restarted; its "
                    "startup configuration may be unchanged.", diagnostics)
        saved = re.search(r"Saving (\d+) bytes to flash:startup-config", reply)
        notes = [f"switch: {ln.strip()}" for ln in reply.splitlines()
                 if ln.strip().startswith("%") or _IMPORTED.search(ln)]
        if saved and int(saved.group(1)) != transfer.size:
            notes.append(f"the switch saved {saved.group(1)} bytes; UNDM sent "
                         f"{transfer.size} (it may store the file in its own form)")
        # 'reload cold' asks nothing: "% Cold reload in progress, please stand by." and the
        # session closes (bench, factory unit, 2026-11-24).
        # The prompt can still appear after that line (bench): it does not end the step.
        talk2 = self._dialogue("reload cold", [], timeout=60, idle_timeout=self.command_quiet,
                               restarting=_RELOADING,
                               prompt_ok=lambda out: not re.search(_RELOADING, out))
        if talk2.ended not in ("restarting", "closed"):
            return OperationResult.failed(
                op, "The file is in the startup configuration, but the switch did not "
                    f"restart ({talk2.detail or talk2.ended}); it takes effect at its next "
                    "restart. Restart it to finish.",
                {"device_output": " ".join(redact_text(_clean(talk2.output)).split())[-600:]})
        self.disconnect()
        return OperationResult.success(
            op, {"restarting": True, "notes": notes},
            f"the switch fetched the file ({transfer.bytes_sent} bytes) into its startup "
            "configuration and is restarting with it ('reload cold')")

    def save_configuration(self) -> OperationResult:
        return OperationResult.success(
            Op.SAVE_CONFIGURATION,
            message="nothing to save: the file was loaded as the startup configuration")

    def verify_configuration(self, intended: str, mode: ApplyMode) -> OperationResult | None:
        """After the restart: hostname as in the file, and the file's lines in the running
        configuration (reported; the switch may show some differently)."""
        op = Op.GET_FACTS
        facts = self.get_device_facts()
        if not facts.ok:
            return OperationResult.failed(op, f"Could not read the switch: {facts.message}")
        wanted = inspect_blackbox_config(intended).facts.get("hostname") or ""
        have = facts.data.hostname
        if wanted and have != wanted:
            return OperationResult.failed(
                op, f"The switch's name is '{have or '(none)'}', the file sets '{wanted}': "
                    "it does not run the file.")
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.failed(op, running.message)
        present = {ln.strip() for ln in str(running.data).splitlines()}
        expected = [ln.strip() for ln in self.config_lines(intended)
                    if ln.strip() and ln.strip() not in ("end",)]
        missing = [ln for ln in expected if ln not in present]
        shown = len(expected) - len(missing)
        result = OperationResult.success(
            op, {"warnings": [f"not shown by 'show running-config': {ln[:120]}"
                              for ln in missing[:10]]},
            f"restarted with the file: name {have or '(none)'}; {shown} of {len(expected)} "
            "lines of the file appear in 'show running-config'")
        return result


_RELOADING = r"Cold reload in progress"


def _answer(output: str, command: str | None = None) -> str:
    """What the switch printed for a command: echo (first line) and prompt removed."""
    lines = _clean(output).split("\n")
    if lines and (command is None or command in lines[0]):
        lines = lines[1:]  # the echo
    if lines and re.fullmatch(r"[^#]*#\s*", lines[-1]):
        lines = lines[:-1]  # the prompt
    return "\n".join(lines).strip("\n")


# A successful load (bench, 2026-11-24): "% Loading /<file> from TFTP server <pc>",
# "% Saving <n> bytes to flash:startup-config", "Import Done! Configuration will become
# active after reboot!". The '%' lines there are progress, not errors.
_IMPORTED = re.compile(r"Import Done!")
_PROGRESS = re.compile(r"^% (?:Loading \S+ from TFTP server|Saving \d+ bytes to )")


def _complaint(reply: str) -> str:
    """A '%' line that is not progress (bench errors: "% Invalid word detected at '^'
    marker.", "% Incomplete command.")."""
    for line in reply.splitlines():
        text = line.strip()
        if text.startswith("%") and not _PROGRESS.match(text):
            return text[:200]
    return ""


def _image(section: str, text: str) -> str:
    m = re.search(rf"^{section}\s*\n-+\s*\n(.*?)(?:\n\s*\n|\Z)", text, re.M | re.S)
    if not m:
        return ""
    return f"{_field('Image', m.group(1))} {_field('Version', m.group(1))}".strip()


def _active_image(text: str) -> str:
    return _image("Active Image", text)


def _alternate_image(text: str) -> str:
    return _image("Alternate Image", text)
