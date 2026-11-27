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
    FileAddresses,
    FirmwareImageRef,
    OperationResult,
)
from undm.drivers.blackbox.config_files import blackbox_file_addresses, inspect_blackbox_config
from undm.drivers.ssh import base as ssh_base
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
    parser_validated_on = ("LIG1014A v00.01.00", "LIG1014A v00.01.01")
    # Its SSH server offers no host key type that paramiko 5 still has ("Incompatible ssh
    # peer (no acceptable host key)", bench 2026-11-24); needs paramiko 3.5 (D-075).
    legacy_ssh_algorithms = True
    command_timeout: ClassVar[float] = 60.0
    load_timeout: ClassVar[float] = 300.0  # TFTP fetch of the file into the startup config
    firmware_timeout: ClassVar[float] = 1200.0  # image transfer and flash write
    restart_probe_interval: ClassVar[float] = 10.0
    restart_grace: ClassVar[float] = 180.0  # back at the prompt after an upgrade: wait this
    #                                         long for a restart the switch starts by itself
    command_quiet: ClassVar[float] = 20.0
    info = DriverInfo(
        driver_id="ssh.blackbox.lig1014a",
        vendor="Black Box",
        platform="blackbox_lig1014a",
        os_family="Black Box LIG1014A",
        description="Black Box LIG1014A over SSH CLI. Experimental: connection, device "
                    "information, backup; loading a complete file (passed once on hardware).",
        simulated=False,
        capabilities=frozenset({Capability.SSH, Capability.CONFIGURATION_BACKUP,
                                Capability.CONFIGURATION_APPLY,
                                Capability.CONFIGURATION_REPLACE,
                                Capability.FIRMWARE_UPGRADE, Capability.REBOOT,
                                Capability.RESTART, Capability.FIRMWARE_SECONDARY_IMAGE}),
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
            "the hostname and the file's lines. Passed once on hardware (factory unit, "
            "2026-11-24).",
            "Firmware: 'firmware upgrade tftp://<pc>/<file>' (syntax from the switch's help); "
            "nothing is answered, the whole image must arrive and the switch must restart by "
            "itself; the active image's version is checked afterwards. UNDM never swaps images "
            "or restarts the switch for an upgrade. Passed once on hardware (v00.01.00 -> "
            "v00.01.01, 2026-11-24): the switch restarted by itself after the write.",
            "Both image banks (D-110, EXPERIMENTAL): the upgrade writes the bank that is not "
            "running and starts from it, so the old version stays in the alternate bank (seen "
            "on the bench, 2026-11-24/26). 'Also the backup slot' runs the same upgrade a "
            "second time, which fills the other bank; UNDM then checks that both banks show "
            "the version. Not yet run on hardware.",
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._restarting = False

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        return inspect_blackbox_config(text)

    @classmethod
    def file_addresses(cls, text: str) -> FileAddresses | None:
        return blackbox_file_addresses(text)

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
        return kind == "firmware" or (kind == "configuration" and mode is ApplyMode.REPLACE)

    # -- firmware (D-080) -----------------------------------------------------------------
    def get_firmware_information(self) -> OperationResult:
        op = Op.GET_FIRMWARE_INFORMATION
        if r := self._need(op):
            return r
        try:
            text = self._send("show version")
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        active = _image_version("Active Image", text) or _field("Software Version", text)
        if not active:
            return OperationResult.failed(op, "Could not read the active image's version")
        alternate = _image_version("Alternate Image", text)
        return OperationResult.success(op, {
            "running": active, "alternate": alternate, "secondary": alternate or None,
            "raw": {"show version": text[:2000]}})

    def stage_firmware_secondary(self, image: FirmwareImageRef) -> OperationResult:
        """The alternate bank (D-110): the same 'firmware upgrade' again. The switch writes
        the bank that is not running and restarts from it, so afterwards both banks hold the
        version. The caller waits for the restart (``data["restarting"]``) and checks both."""
        r = self.stage_firmware(image)
        if not r.ok:
            return OperationResult.failed(Op.STAGE_FIRMWARE_SECONDARY, r.message, r.diagnostics)
        return OperationResult.success(
            Op.STAGE_FIRMWARE_SECONDARY, {**(r.data or {}), "restarting": True},
            f"second upgrade for the alternate bank: {r.message}")

    def stage_firmware(self, image: FirmwareImageRef) -> OperationResult:
        """'firmware upgrade tftp://<pc>/<file>' (syntax from the switch's help). Nothing is
        answered; success needs the whole transfer and then a restart the switch starts by
        itself. 'firmware swap' and 'reload' are not used: which image they would start is
        not known yet."""
        op = Op.STAGE_FIRMWARE
        if r := self._need(op):
            return r
        files = self.file_server
        if files is None:
            return OperationResult.failed(op, "No file server is available for this job")
        client = self.target.management_address
        name = image.filename
        if not _SWITCH_FILE_NAME.fullmatch(name):
            name = f"undm-{image.sha256[:10]}.dat"  # a name the switch accepts
        down, next_probe = [False], [0.0]

        def fetching(_: str) -> bool:
            record = files.last_transfer(name, client)
            return record is not None and not record.completed and not record.error

        def patient(_: str) -> bool:
            # Silence is normal while the image is fetched and written to flash, unless the
            # switch went down without closing the session (its SSH port stops answering).
            record = files.last_transfer(name, client)
            if record is None or record.error:
                return False
            if not record.completed:
                return True
            now = time.monotonic()
            if now >= next_probe[0]:
                next_probe[0] = now + self.restart_probe_interval
                down[0] = not ssh_base.tcp_port_open(client, self.target.port or 22)
            return not down[0]

        self._restarting = False
        try:
            server_ip = files.offer(Path(image.local_path), name, client)
            talk = self._dialogue(f"firmware upgrade tftp://{server_ip}/{name}", [],
                                  timeout=self.firmware_timeout,
                                  idle_timeout=self.command_quiet, patient=patient,
                                  prompt_ok=lambda out: not fetching(out))
        except Exception as e:  # noqa: BLE001
            files.withdraw(name)
            return self._fail(op, e)
        files.withdraw(name)  # a fetch still running is cut off (D-063)
        transfer = self._settled_transfer(name)
        reply = _answer(talk.output)
        diagnostics: dict[str, object] = {
            "device_output": " ".join(redact_text(reply).split())[-600:]}
        notes = [f"switch: {ln.strip()}" for ln in reply.splitlines() if ln.strip()][-6:]
        if transfer is None:
            return OperationResult.failed(
                op, "The switch did not request the image from UNDM's TFTP server "
                    f"({talk.detail or 'it returned to its prompt'}). Its answer is below; "
                    "check this PC's firewall (inbound UDP 69). Nothing was changed.",
                diagnostics)
        if not transfer.completed:
            return OperationResult.failed(
                op, f"Transfer incomplete ({transfer.bytes_sent} of {transfer.size} bytes; "
                    "UNDM has withdrawn the image).", diagnostics)
        how = ""
        if talk.ended == "closed" or (talk.ended == "timeout" and down[0]):
            how = ("closed the session to restart" if talk.ended == "closed"
                   else "is restarting (its SSH port stopped answering)")
        elif talk.ended == "prompt":
            complaint = _complaint(reply)
            if complaint:
                return OperationResult.failed(
                    op, f"The switch fetched the image but refused it: \"{complaint}\".",
                    diagnostics)
            after = self._await_restart()
            if after:
                how = f"returned to its prompt, then {after}"
            else:
                slots = self.get_firmware_information()
                state = (f"active {slots.data['running']}, alternate "
                         f"{slots.data.get('alternate') or '?'}" if slots.ok else "unknown")
                return OperationResult.failed(
                    op, "The switch fetched the image and returned to its prompt, but did not "
                        f"restart within {self.restart_grace:.0f} s (images: {state}). UNDM "
                        "does not swap images or restart it before the switch's behaviour is "
                        "known; its answer is below.", diagnostics)
        else:
            return OperationResult.failed(
                op, f"The switch fetched the image but neither restarted nor returned to its "
                    f"prompt ({talk.detail or talk.ended}); check it on the console.",
                diagnostics)
        self._restarting = True
        self.disconnect()
        return OperationResult.success(
            op, {"bytes": transfer.bytes_sent, "notes": notes},
            f"the switch fetched the image ({transfer.bytes_sent} bytes) and {how}")

    def _await_restart(self) -> str:
        """After a clean return to the prompt: wait for a restart the switch starts by
        itself (session closed, or SSH port down). Empty if none within restart_grace."""
        start = next_probe = time.monotonic()
        while time.monotonic() - start <= self.restart_grace:
            try:
                self._conn.read_channel()
            except Exception:  # noqa: BLE001 - the session closed: restarting
                return "closed the session to restart"
            now = time.monotonic()
            if now >= next_probe:
                next_probe = now + self.restart_probe_interval
                if not ssh_base.tcp_port_open(self.target.management_address,
                                              self.target.port or 22):
                    return "restarted (its SSH port stopped answering)"
            if self.should_stop is not None and self.should_stop():
                return ""
            time.sleep(self.poll_interval)
        return ""

    def install_firmware(self) -> OperationResult:
        return OperationResult.success(
            Op.INSTALL_FIRMWARE,
            message="nothing to do: the switch writes the image itself after the transfer")

    def reboot(self) -> OperationResult:
        if self._restarting:
            self._restarting = False
            return OperationResult.success(
                Op.REBOOT, message="the switch restarts by itself after the upgrade")
        return OperationResult.failed(Op.REBOOT, "No restart was started by the previous step")

    # The restart UNDM sends after loading a file, proven on the bench (D-077, D-099).
    restart_command = "reload cold"

    def restart(self) -> OperationResult:
        op = Op.REBOOT
        if r := self._need(op):
            return r
        try:
            talk = self._dialogue("reload cold", [], timeout=60, idle_timeout=self.command_quiet,
                                  restarting=_RELOADING,
                                  prompt_ok=lambda out: not re.search(_RELOADING, out))
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        if talk.ended in ("restarting", "closed"):
            self._conn = None  # the session is gone
            return OperationResult.success(op, message="the switch is restarting ('reload cold')")
        return OperationResult.failed(
            op, f"The switch did not restart ({talk.detail or talk.ended}).",
            {"device_output": " ".join(redact_text(_clean(talk.output)).split())[-600:],
             "unchanged": True})

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
        shown_vlans = set().union(*[_vlans(ln) for ln in present if _VLAN_LIST.match(ln)])
        missing = [ln for ln in expected if ln not in present
                   and not (_VLAN_LIST.match(ln) and _vlans(ln) <= shown_vlans)]
        shown = len(expected) - len(missing)
        result = OperationResult.success(
            op, {"warnings": [f"not shown by 'show running-config': {ln[:120]}"
                              for ln in missing[:10]]},
            f"restarted with the file: name {have or '(none)'}; {shown} of {len(expected)} "
            "lines of the file appear in 'show running-config'")
        return result


_RELOADING = r"Cold reload in progress"
# 'vlan 168,222,1001,1006' (file) may be shown in another form, e.g. with VLAN 1 or as a
# range (bench, 2026-11-24: the line was not shown as written): compared as sets of VLANs.
_VLAN_LIST = re.compile(r"^vlan [0-9][0-9,\- ]*$")


def _vlans(line: str) -> set[int]:
    found: set[int] = set()
    for part in line.split(None, 1)[1].replace(" ", "").split(","):
        if "-" in part:
            low, _, high = part.partition("-")
            if low.isdigit() and high.isdigit():
                found.update(range(int(low), int(high) + 1))
        elif part.isdigit():
            found.add(int(part))
    return found


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


def _image_version(section: str, text: str) -> str:
    m = re.search(rf"^{section}\s*\n-+\s*\n(.*?)(?:\n\s*\n|\Z)", text, re.M | re.S)
    return _field("Version", m.group(1)) if m else ""


# File names the switch accepts in a URL ('copy ?', 'firmware upgrade ?').
_SWITCH_FILE_NAME = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.-]{0,62}")


def _active_image(text: str) -> str:
    return _image("Active Image", text)


def _alternate_image(text: str) -> str:
    return _image("Alternate Image", text)
