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
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigFileReport,
    Credentials,
    DeviceFacts,
    DriverInfo,
    DriverMaturity,
    FileAddresses,
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
from undm.drivers.fortinet.config_files import file_addresses as fortios_file_addresses
from undm.drivers.ssh import base as ssh_base
from undm.drivers.ssh.base import SSH_CAPABILITIES, Dialogue, LoginDialogueError, SshCliDriver
from undm.security.redaction import redact_text

Op = DeviceOperation
_VDOMS_ON = re.compile(r"Virtual domain configuration\s*:\s*(multiple|enable|split-task)")
# Terminal control sequences and control characters (not newline or tab) in device output.
_CONTROL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")
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
            Capability.LICENSE_FILE,
            Capability.CONFIGURATION_CHECKPOINT, Capability.FIRST_LOGIN_SETUP},
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
    # Manual license on hardware (Fortinet 7.2 documentation and community example: "This
    # operation will overwrite the current license and reboot the system! ... (y/n)").
    # Not yet run on 7.6.5 (Q-46): only this question is answered.
    _LICENSE_QUESTION: ClassVar[str] = r"overwrite the current license[\s\S]*\(y/n\)"
    transfer_timeout: ClassVar[float] = 1800.0   # transfer + check + write, until the restart
    question_timeout: ClassVar[float] = 60.0     # silence before the transfer starts
    # After a complete transfer and a quiet minute, check the SSH port this often: a unit
    # that restarts without closing the session (as a 2930F did, D-054) is noticed.
    restart_probe_interval: ClassVar[float] = 10.0
    # After fetching and checking a file without complaint the unit may show its prompt
    # again before it restarts (bench, base restore on a 101F v7.6.5, 2026-11-24: "File
    # check OK." then the prompt). UNDM then waits this long for the restart.
    restart_grace: ClassVar[float] = 180.0
    # Facts read correctly from a real unit (bench, 2026-11-24): hostname, model, version,
    # serial number, VDOM mode.
    parser_validated_on = ("FortiGate-101F v7.2.6",)
    prompt_hint: ClassVar[str] = (
        "A FortiGate asks for a new admin password at the first login, and when the password "
        "does not meet its password policy (bench: after a base file is restored): log in by "
        "hand (browser at its address, or SSH) and set the approved password.")
    # Demanded password change at login, as a 101F showed it after a base restore (bench,
    # v7.6.5, 2026-11-24): "You are forced to change your password. Old password:", then
    # the policy, "New Password:", "Confirm Password:", "Verifying password...", "Welcome!".
    answers_password_change: ClassVar[bool] = True
    _OLD_PASSWORD: ClassVar[re.Pattern[str]] = re.compile(r"(?i)Old password:\s*$")
    _NEW_PASSWORD: ClassVar[re.Pattern[str]] = re.compile(r"(?i)New Password:\s*$")
    _CONFIRM_PASSWORD: ClassVar[re.Pattern[str]] = re.compile(r"(?i)Confirm Password:\s*$")
    login_dialogue_quiet: ClassVar[float] = 5.0     # no text at all: an ordinary login
    login_dialogue_timeout: ClassVar[float] = 30.0  # silence after text: unknown question
    # FortiOS's answer to 'edit' of an entry that does not exist yet (bench, site script on
    # a 101F v7.6.5, 2026-11-24): normal, counted instead of listed as a warning.
    _NEW_ENTRY: ClassVar[re.Pattern[str]] = re.compile(r"^new entry '[^'\n]*' added$")
    # Shown on entering a VDOM ("current vf=root:0", bench, same run): information only.
    _CONTEXT_NOTE: ClassVar[re.Pattern[str]] = re.compile(r"^current vf=\S+$")
    statement_timeout: ClassVar[float] = 60.0    # per script statement
    script_poll_interval: ClassVar[float] = 0.02

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._restarting = False
        self._sent_secrets: list[str] = []

    # -- what this driver can do with supplied files ----------------------------------
    @classmethod
    def needs_file_server(cls, kind: str, mode: ApplyMode | None = None) -> bool:
        return kind in ("firmware", "license") or (kind == "configuration"
                                                    and mode is ApplyMode.REPLACE)

    @classmethod
    def file_addresses(cls, text: str) -> FileAddresses | None:
        return fortios_file_addresses(text)

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

    def _algorithm_kwargs(self) -> dict[str, object]:
        # Netmiko's FortinetSSH chooses the key exchanges itself (unless it is given some);
        # that choice works on the bench 101F, so it is left as it is.
        return {}

    def _prompt_pattern(self) -> str:
        # Any prompt on a new line: the hostname and the "(context)" change while a
        # script runs, so the prompt seen at login cannot be relied on. The line must hold
        # something besides '#': while fetching a file the unit prints lines of '#'
        # progress marks, which are not its prompt (bench, 101F v7.2.6, 2026-11-24).
        return r"\n[^\n]*[^\s#][ \t]*[#$] ?$"

    def _redact(self, text: str) -> str:
        for value in self._sent_secrets:
            text = text.replace(value, "<secret>")
        return redact_text(text)

    @staticmethod
    def _reply(statement: str, output: str) -> str:
        """What the device printed in answer to one statement (echo and prompt removed).

        Terminal control codes are dropped, and so is a line that only repeats the statement
        (bench, site script on a 101F v7.6.5, 2026-11-24: empty "warnings" and a statement
        with a double space shown as its own reply)."""
        text = _CONTROL.sub("", output.replace("\r", ""))
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
        echo = " ".join(statement.split())
        return "\n".join(ln.strip() for ln in lines
                         if ln.strip() and " ".join(ln.split()) != echo)

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

        down, next_probe = [False], [0.0]  # what the last SSH port check found, and when next

        def patient(output: str) -> bool:
            # Once the unit has asked for the file, silence is normal (checking, writing),
            # unless it is waiting for an answer UNDM does not give, or it went down: then
            # its SSH port stops answering although the session was not closed.
            record = files.last_transfer(name, client)
            if record is None or _ASKING.search(output):
                return False
            if not record.completed:
                return True
            now = time.monotonic()
            if now >= next_probe[0]:
                next_probe[0] = now + self.restart_probe_interval
                down[0] = not ssh_base.tcp_port_open(
                    self.target.management_address, self.target.port or 22)
            return not down[0]

        def fetching(_: str) -> bool:
            # The unit cannot be back at its prompt while it is still fetching the file.
            record = files.last_transfer(name, client)
            return record is not None and not record.completed and not record.error

        talk: Dialogue | None = None
        try:
            server_ip = files.offer(path, name, client)
            with self._global_context():
                talk = self._dialogue(command(server_ip), [(question, "y")],
                                      timeout=self.transfer_timeout,
                                      idle_timeout=self.question_timeout, patient=patient,
                                      prompt_ok=lambda out: not fetching(out))
                self._restarting = "y" in talk.replies and (
                    talk.ended == "closed" or (talk.ended == "timeout" and down[0]))
        except Exception as e:  # noqa: BLE001
            files.withdraw(name)
            return self._fail(op, e)
        # From here on the unit cannot fetch the file any more, nor finish a fetch that is
        # still running: a step UNDM reports as failed must not complete later. A block
        # already sent is still acknowledged, so a fetch that has just ended stays complete.
        files.withdraw(name)
        diagnostics: dict[str, object] = {"device_output": self._redact(talk.output)[-1500:]}
        transfer = self._settled_transfer(name)
        after_prompt = ""
        if (talk.ended == "prompt" and "y" in talk.replies and transfer is not None
                and transfer.completed and not self._complaint(talk.output[talk.answered_at:])):
            after_prompt, output = self._await_restart(talk.output)
            diagnostics["device_output"] = self._redact(output)[-1500:]
            self._restarting = after_prompt in ("closed", "down")
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
                    f"{': ' + transfer.error if transfer.error else ''}; "
                    f"{talk.detail or 'the exchange ended at the ' + talk.ended}). UNDM has "
                    "withdrawn the file, so the FortiGate cannot finish fetching it later.",
                diagnostics)
        if "y" not in talk.replies:
            return OperationResult.failed(
                op, "The FortiGate did not ask the expected question, so nothing was "
                    "confirmed. Its output is below.", diagnostics)
        if after_prompt == "stopped":
            return OperationResult.failed(
                op, f"The FortiGate fetched and checked the {what} and returned to its "
                    "prompt; UNDM stopped waiting for its restart on request. It may still "
                    "restart with the file: check it.", diagnostics)
        if after_prompt == "no_restart":
            return OperationResult.failed(
                op, f"The FortiGate fetched and checked the {what} and returned to its "
                    f"prompt, but did not restart within {self.restart_grace:.0f} s. Check on "
                    "the unit whether it took the file (hostname, version). Its answer is "
                    "below.", diagnostics)
        if talk.ended == "prompt" and not self._restarting:
            return OperationResult.failed(
                op, f"The FortiGate fetched the {what} but did not accept it: it returned to "
                    "its prompt without restarting. Its answer is below.", diagnostics)
        if not self._restarting:
            return OperationResult.failed(
                op, f"The FortiGate fetched the {what} but neither restarted nor returned to "
                    f"its prompt ({talk.detail}). It may be waiting for an answer UNDM does not "
                    "give; check it on the console.", diagnostics)
        if after_prompt == "closed":
            how = "returned to its prompt, then closed the session to restart"
        elif after_prompt == "down":
            how = "returned to its prompt, then restarted (its SSH port stopped answering)"
        elif talk.ended == "closed":
            how = "closed the session to restart"
        else:
            how = "is restarting (its SSH port stopped answering)"
        return OperationResult.success(
            op, {"bytes": transfer.bytes_sent},
            f"the FortiGate fetched the {what} ({transfer.bytes_sent} bytes), accepted it "
            f"and {how}")

    _IN_USE: ClassVar[re.Pattern[str]] = re.compile(r"Cannot change .+ while .+ is used")

    def merge_rerun_note(self, already: int, checked: int) -> str | None:
        # Bench 2026-11-24: a corrected site file run over the earlier site configuration
        # stopped at "Cannot change 'extintf' while the VIP entry is used."
        if checked < 20 or already * 3 < checked * 2:
            return None
        return (f"{already} of {checked} lines of this file are already on the FortiGate: a "
                "site configuration was probably loaded before. FortiOS refuses some changes "
                "to objects that are in use (bench: \"Cannot change 'extintf' while the VIP "
                "entry is used\"), so loading over it can stop part-way. For a clean load, "
                "restore the base file first, then load this file.")

    def _login_dialogue(self, conn: Any, new: Credentials) -> bool:
        """Answer the bench's forced password change; each question at most once."""
        assert self._credentials is not None
        steps = ((self._OLD_PASSWORD, "old", self._credentials.password),
                 (self._NEW_PASSWORD, "new", new.password),
                 (self._CONFIRM_PASSWORD, "confirm", new.password))
        prompt = re.compile(self._prompt_pattern())
        text, mark, answered = "", 0, set()
        last = time.monotonic()
        while True:
            chunk = str(conn.read_channel() or "")
            now = time.monotonic()
            if chunk:
                text, last = text + chunk, now
                pending = text[mark:]
                step = next((s for s in steps if s[0].search(pending)), None)
                if step is not None:
                    if step[1] in answered:
                        raise LoginDialogueError(
                            "the device asked again for its "
                            f"{'old' if step[1] == 'old' else 'new'} password: it did not "
                            "accept UNDM's answer", text)
                    conn.write_channel(step[2] + "\n")
                    answered.add(step[1])
                    mark = len(text)
                elif "Welcome!" in pending or prompt.search("\n" + pending) \
                        or "to accept" in pending:
                    if answered and "confirm" not in answered:
                        raise LoginDialogueError(
                            "the password change ended before it was confirmed", text)
                    self._hand_back(conn, pending)  # Netmiko still needs to see the prompt
                    return "confirm" in answered
                continue
            if not text and now - last > self.login_dialogue_quiet:
                return False  # nothing printed yet: Netmiko prompts for the prompt itself
            if text and now - last > self.login_dialogue_timeout:
                raise LoginDialogueError(
                    "it asked something UNDM does not answer at login", text)
            time.sleep(self.poll_interval)

    def _complaint(self, answer: str) -> bool:
        """Whether the unit's answer has an error-looking line (prompt lines ignored)."""
        return any(self._ERROR_REPLY.search(ln) for ln in answer.replace("\r", "").split("\n")
                   if ln.strip() and not re.search(r"[#$]\s*$", ln))

    def _await_restart(self, output: str) -> tuple[str, str]:
        """The unit returned to its prompt after taking a file: wait for its restart.

        Returns how the wait ended - "closed" (the unit closed the session), "down" (its
        SSH port stopped answering), "refused" (it printed an error-looking line),
        "stopped" (stop requested) or "no_restart" (``restart_grace`` passed) - and the
        session output including what came after the prompt."""
        start = next_probe = time.monotonic()
        while True:
            try:
                chunk = str(self._conn.read_channel() or "")
            except Exception:  # noqa: BLE001 - a closed session is what UNDM waits for
                return "closed", output
            if chunk:
                output += chunk
                if self._complaint(chunk):
                    return "refused", output
                continue
            now = time.monotonic()
            if now >= next_probe:
                next_probe = now + self.restart_probe_interval
                if not ssh_base.tcp_port_open(self.target.management_address,
                                              self.target.port or 22):
                    return "down", output
            if self.should_stop is not None and self.should_stop():
                return "stopped", output
            if now - start > self.restart_grace:
                return "no_restart", output
            time.sleep(self.poll_interval)

    # -- license file (EXPERIMENTAL, D-100; not yet run on hardware, Q-46) ---------------
    license_command = "execute restore manual-license tftp <file> <this PC>"

    def load_license(self, path: Path, name: str) -> OperationResult:
        op = Op.APPLY_CONFIGURATION
        if r := self._need(op):
            return r
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "license.lic"
        r = self._device_fetch(op, path, safe,
                               lambda ip: f"execute restore manual-license tftp {safe} {ip}",
                               self._LICENSE_QUESTION, "license file")
        if r.ok:
            self._restarting = False  # the wait for its return is the plan's
            return OperationResult.success(op, {"restarting": True}, r.message)
        return r

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

    def restart_notice(self, mode: ApplyMode) -> str | None:
        if mode is not ApplyMode.REPLACE:
            return None
        return ("restoring the base file: the FortiGate fetches it from this PC and restarts "
                "with it. Expect several minutes without answers. Keep it powered and "
                "connected; UNDM continues by itself")

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
        created = 0
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
            if statement.split()[0] == "edit" and self._NEW_ENTRY.match(reply):
                created += 1
                continue
            if self._CONTEXT_NOTE.match(reply):  # where the statement put the session
                continue
            if self._ERROR_REPLY.search(reply):
                in_use = (" The object exists already and is in use: a site configuration "
                          "was probably loaded before. Restore the base file, then load "
                          "this file again." if self._IN_USE.search(reply) else "")
                return OperationResult.failed(
                    op, f"The FortiGate rejected line {number} ('{shown}'): {reply[:300]}. "
                        f"{done}.{in_use}", diagnostics)
            warnings.append(f"line {number}: {reply[:200]}")
        with contextlib.suppress(Exception):  # the hostname may have changed
            self._conn.set_base_prompt()
        return OperationResult.success(
            op, {"warnings": warnings, "statements": total, "new_entries": created},
            f"{total} statements sent, every one accepted"
            + (f"; {created} new entries created ('new entry … added')" if created else "")
            + (f"; {len(warnings)} message(s) listed as warnings" if warnings else ""))

    # 'get system global' in the global context on a multi-VDOM unit (outside it: "command
    # parse error before 'global'"); bench, 101F v7.6.5 after the base file, 2026-11-24:
    # "cfg-save             : automatic".
    _CFG_SAVE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*cfg-save\s*:\s*(\S+)", re.M)

    def save_configuration(self) -> OperationResult:
        """FortiOS saves each change on 'end' when cfg-save is automatic: check that it is."""
        op = Op.SAVE_CONFIGURATION
        if r := self._need(op):
            return r
        command = "get system global | grep cfg-"
        try:
            with self._global_context():
                talk = self._dialogue(command, [], timeout=30, idle_timeout=15)
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        m = self._CFG_SAVE.search(talk.output) if talk.ended == "prompt" else None
        if m is None:
            return OperationResult.success(
                op, {"notes": ["could not read the unit's configuration save mode (cfg-save); "
                               "assumed automatic, the FortiOS default"]},
                "saved automatically (cfg-save assumed automatic, not readable)")
        mode = m.group(1)
        if mode == "automatic":
            return OperationResult.success(
                op, {"notes": ["configuration save mode on the unit: automatic (checked); "
                               "each change was saved when applied"]},
                "saved automatically (cfg-save automatic, checked)")
        undone = " and are undone after a timeout" if mode == "revert" else ""
        return OperationResult.failed(
            op, f"The unit's configuration save mode is '{mode}' (cfg-save): the changes are "
                f"applied but not saved automatically{undone}. Save the configuration on the "
                "unit now, before it restarts; UNDM does not run a save command for this mode.")

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
