"""FortiOS over SSH. EXPERIMENTAL: no command below has been run by UNDM on a FortiGate yet.

Read-only: facts (`get system status`), running configuration (`show`), backup.
Changes, each inside an approved deployment (see docs/vendor-support/fortigate-101f-staging.md):

* Firmware: `execute restore image tftp <file> <server>`; UNDM answers "y" only to the
  "...replace the current firmware..." question.
* Full backup: `execute restore config tftp <file> <server>`; "y" only to the
  "...overwrite the current setting..." question.
* CLI script: each statement typed in turn; no question is answered (one stops the run).
* Revision: `execute backup config flash "<name>"` (syntax from one Fortinet example),
  confirmed with `execute revision list config`.

For firmware and full backups the FortiGate fetches the file from UNDM's TFTP server and
then restarts by itself. Success needs evidence: UNDM's TFTP record of the whole file,
the confirmation actually sent, and the session closed by the restart. On a multi-VDOM
unit the `execute` commands are issued inside `config global` (community guidance).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigFileReport,
    DeviceFacts,
    DriverInfo,
    DriverMaturity,
    FirmwareImageRef,
    OperationResult,
)
from undm.drivers.fortinet.config_files import (
    configured_hostname,
    insert_secret_values,
    inspect_fortios_file,
    is_secret_setting,
    script_statements,
)
from undm.drivers.ssh.base import SSH_CAPABILITIES, Dialogue, SshCliDriver
from undm.security.redaction import redact_text

Op = DeviceOperation
_VDOMS_ON = re.compile(r"Virtual domain configuration\s*:\s*(multiple|enable|split-task)")
_ASKING = re.compile(r"\?\s*(?:\(y/n\))?\s*$")


class FortiOSSsh(SshCliDriver):
    netmiko_device_type = "fortinet"
    facts_commands = ("get system status",)
    running_config_command = "show"
    info = DriverInfo(
        driver_id="ssh.fortinet.fortios",
        vendor="Fortinet",
        platform="fortios",
        os_family="FortiOS",
        description="FortiOS over SSH CLI (Netmiko 'fortinet'). Experimental, not lab-validated.",
        simulated=False,
        capabilities=SSH_CAPABILITIES | {
            Capability.FIRMWARE_UPGRADE, Capability.REBOOT, Capability.CONFIGURATION_REPLACE,
            Capability.CONFIGURATION_CHECKPOINT},
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "If console paging ('set output more') is on, Netmiko temporarily sets "
            "'config system console / set output standard' for the session and restores it on "
            "disconnect: a read-only session still makes this temporary change.",
            "Full backups are restored by TFTP (replace mode); the unit restarts and is then "
            "checked by hostname, VDOM mode and version, not line by line.",
            "CLI scripts are sent one statement at a time (merge mode). A reply that looks like "
            "an error stops the run at that line; other replies are reported as warnings. A "
            "bare 'end' before the first block may fail without stopping the run.",
            "Secret settings in a script can be filled from the credential store when sent; the "
            "values never appear in UNDM's records.",
            "Firmware by TFTP ('execute restore image tftp'); the unit installs and restarts by "
            "itself. No automatic firmware or configuration rollback.",
            "After a verified change from an imported file, a revision named after the file is "
            "saved ('execute backup config flash'); a missing revision is a warning.",
            "Not yet run on hardware: first use on a spare unit "
            "(docs/vendor-support/fortigate-101f-bench.md).",
        ),
    )

    # Replies that look like an error stop a script (FortiOS has no single error format).
    _ERROR_REPLY: ClassVar[re.Pattern[str]] = re.compile(
        r"(?i)\b(?:fail\w*|error\w*|invalid|not found|unknown|incorrect|not allowed|denied|"
        r"cannot|can't|unable|exceed\w*|conflict\w*|duplicate|out of range|return code)\b")
    # The warnings Fortinet's documentation shows before these commands (to be confirmed
    # on the bench). Only these questions are answered, and only with "y".
    _IMAGE_QUESTION: ClassVar[str] = r"replace the current firmware[\s\S]*\(y/n\)"
    _RESTORE_QUESTION: ClassVar[str] = r"overwrite the current setting[\s\S]*\(y/n\)"
    transfer_timeout: ClassVar[float] = 1800.0   # transfer + check + write, until the restart
    question_timeout: ClassVar[float] = 60.0     # silence before the transfer starts
    statement_timeout: ClassVar[float] = 60.0    # per script statement
    script_poll_interval: ClassVar[float] = 0.02

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._restarting = False
        self._sent_secrets: list[str] = []

    # -- what this driver can do with supplied files ----------------------------------
    @classmethod
    def needs_file_server(cls, kind: str, mode: ApplyMode | None = None) -> bool:
        return kind == "firmware" or (kind == "configuration" and mode is ApplyMode.REPLACE)

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        report = inspect_fortios_file(text)
        if report.file_type == "cli_script" and report.facts.get("multi_line_values"):
            return replace(report, blocked_reason=(
                "Values that continue over several lines (certificates, keys) cannot be sent "
                "statement by statement yet."))
        return report

    def prepare_for_device(self, config: str, secrets: Mapping[str, str]) -> str:
        text = insert_secret_values(config, secrets)  # raises ValueError
        self._sent_secrets = [v for v in secrets.values() if v]
        return text

    # -- verification helpers ---------------------------------------------------------
    def expected_lines(self, config: str) -> list[str]:
        # FortiOS displays secrets encrypted, so they can never be compared as written.
        return [ln for ln in super().expected_lines(config) if not is_secret_setting(ln)]

    def _prompt_pattern(self) -> str:
        # Any prompt on a new line: the hostname and the "(context)" change while a
        # script runs, so the prompt seen at login cannot be relied on.
        return r"\n[^\n]*[#$] ?$"

    def _redact(self, text: str) -> str:
        for value in self._sent_secrets:
            text = text.replace(value, "<secret>")
        return redact_text(text)

    @staticmethod
    def _reply(statement: str, output: str) -> str:
        """What the device printed in answer to one statement (echo and prompt removed)."""
        text = output.replace("\r", "")
        i = j = 0
        while i < len(text) and j < len(statement):  # the echo may wrap onto new lines
            if text[i] == statement[j]:
                i, j = i + 1, j + 1
            elif text[i] == "\n":
                i += 1
            else:
                break
        if j < len(statement):
            i = text.find("\n") + 1 if "\n" in text else len(text)
        lines = text[i:].split("\n")
        if lines and re.search(r"[#$] ?$", lines[-1]):
            lines = lines[:-1]
        return "\n".join(ln.strip() for ln in lines if ln.strip())

    # -- session --------------------------------------------------------------------
    def connect(self) -> OperationResult:
        result = super().connect()
        if result.ok:
            self._restarting = False
        return result

    def _status(self) -> str:
        return self._send("get system status")

    @contextlib.contextmanager
    def _global_context(self) -> Iterator[None]:
        """On a multi-VDOM unit, run 'execute' commands inside 'config global'."""
        entered = False
        if _VDOMS_ON.search(self._status()):
            talk = self._dialogue("config global", [], timeout=30, idle_timeout=15)
            reply = self._reply("config global", talk.output)
            if talk.ended != "prompt" or self._ERROR_REPLY.search(reply):
                raise RuntimeError(f"could not enter 'config global': {reply or talk.detail}")
            entered = True
        try:
            yield
        finally:
            if entered and self._conn is not None and not self._restarting:
                self._dialogue("end", [], timeout=30, idle_timeout=15)

    # -- read-only ------------------------------------------------------------------
    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        text = outputs.get("get system status", "")
        version_line = self._search(r"^Version\s*:\s*(.+)$", text) or ""
        model, _, version = version_line.partition(" ")
        return DeviceFacts(
            hostname=self._search(r"^Hostname\s*:\s*(\S+)", text) or prompt.rstrip("#$ "),
            vendor="Fortinet",
            model=model or "unknown",
            os_version=version.split(",")[0] if version else "unknown",
            serial_number=self._search(r"^Serial-Number\s*:\s*(\S+)", text),
            extra={"vdom_mode": self._search(r"^Virtual domain configuration\s*:\s*(\S+)", text)},
        )

    def get_firmware_information(self) -> OperationResult:
        op = Op.GET_FIRMWARE_INFORMATION
        if r := self._need(op):
            return r
        try:
            status = self._status()
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        m = re.search(r"^Version\s*:\s*\S+\s+(v?\d+(?:\.\d+)+)(?:,build(\d+))?", status, re.M)
        if not m:
            return OperationResult.failed(op, "Could not read the FortiOS version")
        return OperationResult.success(op, {"running": m.group(1), "build": m.group(2),
                                            "raw": {"get system status": status[:2000]}})

    # -- files the FortiGate fetches from UNDM -----------------------------------------
    def _device_fetch(self, op: DeviceOperation, path: Path, name: str,
                      command: Callable[[str], str], question: str, what: str
                      ) -> OperationResult:
        """Offer a file, run the command that makes the FortiGate fetch it, confirm once.

        Success only when the whole file was fetched, the expected question was answered
        and the FortiGate then closed the session to restart."""
        files = self.file_server
        if files is None:
            return OperationResult.failed(op, "No file server is available for this job")
        client = self.target.management_address

        def patient(output: str) -> bool:
            # Once the unit has asked for the file, silence is normal (checking, writing),
            # unless it is waiting for an answer UNDM does not give.
            return files.last_transfer(name, client) is not None and not _ASKING.search(output)

        talk: Dialogue | None = None
        try:
            server_ip = files.offer(path, name, client)
            with self._global_context():
                talk = self._dialogue(command(server_ip), [(question, "y")],
                                      timeout=self.transfer_timeout,
                                      idle_timeout=self.question_timeout, patient=patient)
                self._restarting = talk.ended == "closed" and "y" in talk.replies
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        diagnostics: dict[str, object] = {"device_output": self._redact(talk.output)[-1500:]}
        transfer = self._settled_transfer(name)
        if self._restarting:
            self.disconnect()
        if transfer is None:
            return OperationResult.failed(
                op, f"The FortiGate did not request the {what} from UNDM's TFTP server "
                    f"({talk.detail or 'it returned to its prompt'}). Check its output below, "
                    "this PC's firewall (inbound UDP 69) and the cabling/addresses.", diagnostics)
        if not transfer.completed:
            return OperationResult.failed(
                op, f"Transfer incomplete ({transfer.bytes_sent} of {transfer.size} bytes"
                    f"{': ' + transfer.error if transfer.error else ''}).", diagnostics)
        if "y" not in talk.replies:
            return OperationResult.failed(
                op, "The FortiGate did not ask the expected question, so nothing was "
                    "confirmed. Its output is below.", diagnostics)
        if talk.ended == "prompt":
            return OperationResult.failed(
                op, f"The FortiGate fetched the {what} but did not accept it: it returned to "
                    "its prompt without restarting. Its answer is below.", diagnostics)
        if not self._restarting:
            return OperationResult.failed(
                op, f"The FortiGate fetched the {what} but neither restarted nor returned to "
                    f"its prompt ({talk.detail}). It may be waiting for an answer UNDM does not "
                    "give; check it on the console.", diagnostics)
        return OperationResult.success(
            op, {"bytes": transfer.bytes_sent},
            f"the FortiGate fetched the {what} ({transfer.bytes_sent} bytes), accepted it "
            "and closed the session to restart")

    def stage_firmware(self, image: FirmwareImageRef) -> OperationResult:
        op = Op.STAGE_FIRMWARE
        if r := self._need(op):
            return r
        name = re.sub(r"[^A-Za-z0-9._-]", "_", image.filename)
        return self._device_fetch(op, Path(image.local_path), name,
                                  lambda ip: f"execute restore image tftp {name} {ip}",
                                  self._IMAGE_QUESTION, "image")

    def install_firmware(self) -> OperationResult:
        return OperationResult.success(
            Op.INSTALL_FIRMWARE,
            message="nothing to do: the FortiGate installs the image itself after the transfer")

    def reboot(self) -> OperationResult:
        if self._restarting:
            self._restarting = False
            return OperationResult.success(
                Op.REBOOT, message="the FortiGate restarts by itself after accepting the image")
        return OperationResult.failed(Op.REBOOT, "No restart was started by the previous step")

    # -- configuration --------------------------------------------------------------
    def _platform_problem(self, report: ConfigFileReport) -> str | None:
        code = report.facts.get("platform_code", "")
        facts = self.get_device_facts()
        model = facts.data.model if facts.ok else ""
        if not code or not model or model == "unknown":
            return None
        if re.sub(r"(?i)^FGT?", "", code).upper() != re.sub(
                r"(?i)^FortiGate-?", "", model).upper():
            return (f"The backup was written on a unit with platform code {code}; this unit "
                    f"reports {model}. Restoring it here is refused.")
        return None

    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        op = Op.APPLY_CONFIGURATION
        if r := self._need(op):
            return r
        report = inspect_fortios_file(config)
        if mode is ApplyMode.REPLACE:
            if report.file_type != "full_backup":
                return OperationResult.failed(
                    op, "Replace mode needs a full FortiOS backup (a file that starts with "
                        "'#config-version=').")
            problem = self._platform_problem(report)
            if problem:
                return OperationResult.failed(op, problem)
            return self._restore_full_backup(config)
        if report.file_type == "full_backup":
            return OperationResult.failed(
                op, "A full backup is restored as a whole (replace mode), never line by line.")
        if report.problems:
            return OperationResult.failed(
                op, "The file has structure problems: " + "; ".join(report.problems[:3]))
        return self._run_script(config)

    def _restore_full_backup(self, config: str) -> OperationResult:
        op = Op.APPLY_CONFIGURATION
        name = f"undm-{hashlib.sha256(config.encode()).hexdigest()[:10]}.conf"
        # The file holds passwords and keys: written privately, removed straight after.
        fd, tmp = tempfile.mkstemp(prefix="undm-restore-", suffix=".conf")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(config)
            result = self._device_fetch(op, Path(tmp), name,
                                        lambda ip: f"execute restore config tftp {name} {ip}",
                                        self._RESTORE_QUESTION, "configuration file")
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        if not result.ok:
            return result
        return OperationResult.success(op, {"restarting": True}, result.message)

    def _run_script(self, config: str) -> OperationResult:
        op = Op.APPLY_CONFIGURATION
        statements = script_statements(config)
        total = len(statements)
        warnings: list[str] = []
        seen_config = False
        for idx, (number, statement) in enumerate(statements):
            talk = self._dialogue(statement, [], timeout=self.statement_timeout,
                                  idle_timeout=self.statement_timeout, clear=idx == 0,
                                  poll=self.script_poll_interval)
            shown = self._redact(statement)[:160]
            done = (f"{idx} of {total} statements were accepted before it; the rest were "
                    "not sent")
            diagnostics: dict[str, object] = {
                "device_output": self._redact(talk.output)[-1500:], "line": number}
            if talk.ended != "prompt":
                return OperationResult.failed(
                    op, f"No prompt after line {number} ('{shown}'): {talk.detail}. The "
                        f"FortiGate may be asking a question (see its output). {done}.",
                        diagnostics)
            if statement.split()[0] == "config":
                seen_config = True
            reply = self._redact(self._reply(statement, talk.output))
            if not reply:
                continue
            if statement == "end" and not seen_config:
                warnings.append(f"line {number} 'end': {reply[:200]} (expected, before the "
                                "first block)")
                continue
            if self._ERROR_REPLY.search(reply):
                return OperationResult.failed(
                    op, f"The FortiGate rejected line {number} ('{shown}'): {reply[:300]}. "
                        f"{done}.", diagnostics)
            warnings.append(f"line {number}: {reply[:200]}")
        with contextlib.suppress(Exception):  # the hostname may have changed
            self._conn.set_base_prompt()
        return OperationResult.success(
            op, {"warnings": warnings, "statements": total},
            f"{total} statements sent, every one accepted"
            + (f"; {len(warnings)} message(s) listed as warnings" if warnings else ""))

    def save_configuration(self) -> OperationResult:
        op = Op.SAVE_CONFIGURATION
        if r := self._need(op):
            return r
        return OperationResult.success(
            op, message="FortiOS commits on 'end' (assumes default cfg-save automatic; "
                        "not checked)")

    def verify_configuration(self, intended: str, mode: ApplyMode) -> OperationResult | None:
        op = Op.GET_FACTS
        facts = self.get_device_facts()
        if not facts.ok:
            return OperationResult.failed(op, f"Could not read the FortiGate: {facts.message}")
        f = facts.data
        vdoms = str(f.extra.get("vdom_mode") or "unknown")
        problems: list[str] = []
        wanted = configured_hostname(intended)
        if wanted and f.hostname != wanted:
            problems.append(f"hostname is {f.hostname}, the file sets {wanted}")
        if mode is ApplyMode.REPLACE:
            report = inspect_fortios_file(intended)
            if report.facts.get("vdom_mode") == "multi-vdom" and not _VDOMS_ON.search(
                    f"Virtual domain configuration: {vdoms}"):
                problems.append(f"VDOM mode is {vdoms}, but the file is a multi-VDOM "
                                "configuration")
            if problems:
                return OperationResult.failed(op, "After the restore: " + "; ".join(problems))
            return OperationResult.success(
                op, message=f"back after the restore: hostname {f.hostname}, VDOMs {vdoms}, "
                            f"running {f.os_version} (checked by these facts, not line by "
                            "line: FortiOS converts a restored file to its own release)")
        if problems:
            return OperationResult.failed(op, "After the script: " + "; ".join(problems))
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.success(
                op, message=f"every statement was accepted; hostname {f.hostname}; read-back "
                            f"not available ({running.message})")
        expected = self.expected_lines(intended)
        present = self.present_lines(str(running.data))
        shown = sum(1 for ln in expected if ln in present)
        return OperationResult.success(
            op, message=f"every statement was accepted; hostname {f.hostname}; {shown} of "
                        f"{len(expected)} lines of the file appear in 'show' (FortiOS does not "
                        "display settings that equal their default)")

    def create_checkpoint(self, label: str) -> OperationResult:
        op = Op.CREATE_CHECKPOINT
        if r := self._need(op):
            return r
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", label)[:60]
        command = f'execute backup config flash "{name}"'
        try:
            with self._global_context():
                talk = self._dialogue(command, [], timeout=120, idle_timeout=60)
                listing = (self._send("execute revision list config")
                           if talk.ended == "prompt" else "")
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        reply = self._redact(self._reply(command, talk.output))
        if talk.ended != "prompt":
            return OperationResult.failed(op, f"No prompt after '{command}': {talk.detail}")
        if self._ERROR_REPLY.search(reply):
            return OperationResult.failed(op, f"The FortiGate refused '{command}': {reply[:200]}")
        if name not in listing:
            return OperationResult.failed(
                op, f"'{command}' was accepted, but '{name}' does not appear in "
                    "'execute revision list config'. Save the revision in the GUI if needed.")
        return OperationResult.success(op, message=f"revision '{name}' saved on the FortiGate")
