"""Generic SSH/CLI driver built on Netmiko.

EXPERIMENTAL. Written from public documentation of each platform's CLI and of
Netmiko, and tested only against fake connections. Nothing here has been
validated on lab equipment yet; see docs/vendor-support/support-matrix.md.

What it does:
* read-only: connect, facts (best-effort parsing; raw output kept), running
  config, backup (the running config is stored by UNDM; nothing is written to
  the device);
* impacting: apply configuration lines in *merge* mode, save.
What it does NOT do: replace mode, rollback, firmware. Those are reported as
UNSUPPORTED so the orchestrator ends in manual recovery instead of guessing.

Success is never assumed from transmission: errors printed by the device fail
the operation, and the orchestrator verifies by reading the configuration back.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigurationBackup,
    DeviceDriver,
    DeviceFacts,
    OperationResult,
    TransferInfo,
)
from undm.security.redaction import redact_text

Op = DeviceOperation
C = Capability

SSH_CAPABILITIES = frozenset(
    {C.SSH, C.CONFIGURATION_BACKUP, C.CONFIGURATION_APPLY}
)

# Lines that carry no configuration or are never displayed in running config.
_ALWAYS_IGNORED = {"!", "end", "exit", "next", "no shutdown", "set status up"}


@dataclass(frozen=True)
class Dialogue:
    """How an interactive command ended, with everything the device printed."""

    output: str
    replies: list[str]
    ended: Literal["prompt", "closed", "timeout"]
    detail: str = ""

    @property
    def tail(self) -> str:
        """The end of the device output, safe to show (secrets redacted)."""
        return redact_text(self.output)[-1500:]


def _default_factory(**kwargs: Any) -> Any:
    from netmiko import ConnectHandler  # imported lazily: heavy dependency

    return ConnectHandler(**kwargs)


class SshCliDriver(DeviceDriver):
    netmiko_device_type: ClassVar[str]
    facts_commands: ClassVar[tuple[str, ...]]
    running_config_command: ClassVar[str]
    # Device output that means a configuration line was rejected.
    error_pattern: ClassVar[str] = (
        r"% ?Invalid input|% ?Incomplete command|% ?Ambiguous command|Invalid input"
        r"|Command fail|parse error|Unknown action|entry not found|not found in datasource"
    )
    # Header/comment lines in configuration files that must not be sent to the device.
    skip_line_patterns: ClassVar[tuple[str, ...]] = (r"^\s*!", r"^\s*#")
    # Model/firmware combinations on which the facts parser was checked against real output.
    parser_validated_on: ClassVar[tuple[str, ...]] = ()
    connect_timeout: ClassVar[int] = 15
    read_timeout: ClassVar[int] = 120
    poll_interval: ClassVar[float] = 0.2  # pause between reads while a dialogue is quiet
    # Replaced in tests with a fake connection factory.
    connection_factory: ClassVar[Callable[..., Any]] = staticmethod(_default_factory)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._conn: Any = None

    # -- helpers ------------------------------------------------------------------
    def _need(self, op: DeviceOperation) -> OperationResult | None:
        if self._conn is None:
            return OperationResult.failed(op, "Not connected")
        return None

    def _send(self, command: str) -> str:
        return str(self._conn.send_command(command, read_timeout=self.read_timeout))

    def _prompt_pattern(self) -> str:
        base = re.escape(str(getattr(self._conn, "base_prompt", "") or ""))
        return (base + r"[^\n]*[#>]\s*$") if base else r"[#>]\s*$"

    def _dialogue(self, command: str, answers: list[tuple[str, str]], *, timeout: float,
                  idle_timeout: float = 60.0,
                  patient: Callable[[str], bool] | None = None,
                  clear: bool = True, poll: float | None = None) -> Dialogue:
        """Run a command that asks questions and report how the exchange ended.

        ``answers`` is an ordered list of (question regex, reply). When the output ends
        with a known question the reply is sent. The exchange ends at the prompt
        ("prompt"), when the device closes the session ("closed"), or when it goes
        quiet ("timeout"). An unknown question is never answered: the device then goes
        quiet and the caller gets its text back, after ``idle_timeout`` rather than
        after the whole ``timeout``. ``patient(output so far)`` may report that silence
        is expected (for example while the device writes a file it has received).

        Never raises for device behaviour; the caller decides what each ending means.
        ``clear=False`` skips discarding unread output first (for back-to-back statements
        that each ended at the prompt); ``poll`` overrides the pause between reads.
        """
        conn = self._conn
        enter = str(getattr(conn, "RETURN", "\n"))
        prompt = re.compile(self._prompt_pattern())
        questions = [(re.compile(f"(?:{q})\\s*$"), a) for q, a in answers]
        output, replies, answered = "", [], 0
        try:
            if clear:
                conn.clear_buffer()
            conn.write_channel(command + enter)
            start = last_data = time.monotonic()
            while True:
                chunk = str(conn.read_channel() or "")
                now = time.monotonic()
                if chunk:
                    output, last_data = output + chunk, now
                    pending = output[answered:]
                    reply = next((a for q, a in questions if q.search(pending)), None)
                    if reply is not None:
                        conn.write_channel(reply + enter)
                        replies.append(reply)
                        answered = len(output)
                    elif prompt.search(pending):
                        return Dialogue(output, replies, "prompt")
                    continue
                if now - start > timeout:
                    return Dialogue(output, replies, "timeout",
                                    f"not finished after {timeout:.0f} s")
                if now - last_data > idle_timeout and not (patient and patient(output)):
                    return Dialogue(output, replies, "timeout",
                                    f"no output for {idle_timeout:.0f} s")
                time.sleep(self.poll_interval if poll is None else poll)
        except Exception as e:  # noqa: BLE001 - a closed session is an ending, not a crash
            return Dialogue(output, replies, "closed",
                            f"{type(e).__name__}: {redact_text(str(e))[:200]}")

    def _settled_transfer(self, name: str, wait: float = 5.0,
                          since: TransferInfo | None = None) -> TransferInfo | None:
        """The device's latest fetch of ``name``, once the server has finished recording it.

        The device can return to its prompt a moment before the server has processed
        the final acknowledgement, so an unfinished record is given a short grace period.
        ``since`` is the record seen before the command was sent: a second copy of the same
        file must not be mistaken for the first one, so that record counts as no fetch.
        """
        assert self.file_server is not None
        client = self.target.management_address
        deadline = time.monotonic() + wait
        while True:
            record = self.file_server.last_transfer(name, client)
            if record is not None and record is since:
                record = None
            if record is None or record.completed or record.error \
                    or time.monotonic() >= deadline:
                return record
            time.sleep(0.05)

    def _fail(self, op: DeviceOperation, err: Exception) -> OperationResult:
        # Exception text may echo device output; redact before it reaches logs/audit.
        return OperationResult.failed(op, f"{type(err).__name__}: {redact_text(str(err))[:500]}")

    def config_lines(self, config: str) -> list[str]:
        """Lines to send: drop blanks, comments and file headers."""
        skip = [re.compile(p) for p in self.skip_line_patterns]
        return [ln.rstrip() for ln in config.splitlines()
                if ln.strip() and not any(p.search(ln) for p in skip)]

    def expected_lines(self, config: str) -> list[str]:
        lines = [ln.strip() for ln in self.config_lines(config)]
        return [ln for ln in lines if ln.lower() not in _ALWAYS_IGNORED]

    def present_lines(self, running: str) -> set[str]:
        return {ln.strip() for ln in running.splitlines() if ln.strip()}

    def _connect_kwargs(self) -> dict[str, object]:
        """Extra Netmiko arguments for a platform (never logged)."""
        return {}

    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        raise NotImplementedError

    @staticmethod
    def _search(pattern: str, text: str) -> str | None:
        m = re.search(pattern, text, flags=re.MULTILINE)
        return m.group(1).strip() if m else None

    # -- session --------------------------------------------------------------------
    def connect(self) -> OperationResult:
        op = Op.CHECK_REACHABILITY
        if self._credentials is None:
            return OperationResult.failed(op, "No credentials: attach a credential to the device")
        try:
            from netmiko.exceptions import (
                NetmikoAuthenticationException,
                NetmikoTimeoutException,
            )
        except ImportError:  # pragma: no cover - dependency is declared
            return OperationResult.failed(op, "netmiko is not installed")
        try:
            self._conn = self.connection_factory(
                device_type=self.netmiko_device_type,
                host=self.target.management_address,
                port=self.target.port or 22,
                username=self._credentials.username,
                password=self._credentials.password,
                conn_timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
                fast_cli=False,
                **self._connect_kwargs(),
            )
        except NetmikoAuthenticationException:
            return OperationResult.failed(op, "Authentication failed (check the credential)")
        except NetmikoTimeoutException:
            return OperationResult.failed(
                op, f"Timed out connecting to {self.target.management_address}:"
                    f"{self.target.port or 22} (unreachable, filtered, or SSH disabled)")
        except Exception as e:  # noqa: BLE001 - report any transport error cleanly
            return self._fail(op, e)
        return OperationResult.success(
            op, message=f"SSH session established ({self.info.os_family})")

    def disconnect(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):  # best effort
                self._conn.disconnect()
            self._conn = None

    # -- read-only ------------------------------------------------------------------
    def get_device_facts(self) -> OperationResult:
        op = Op.GET_FACTS
        if r := self._need(op):
            return r
        try:
            outputs = {cmd: self._send(cmd) for cmd in self.facts_commands}
            prompt = str(self._conn.find_prompt())
            facts = self.parse_facts(outputs, prompt)
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        validated = self.parser_validated_on
        facts.extra.update({
            "parser": ("checked against real output: " + "; ".join(validated)
                       + " (best effort elsewhere)") if validated
            else "best_effort_not_lab_verified",
            "raw_output": {k: v[:4000] for k, v in outputs.items()},
        })
        return OperationResult.success(op, facts)

    def get_running_configuration(self) -> OperationResult:
        op = Op.GET_RUNNING_CONFIGURATION
        if r := self._need(op):
            return r
        try:
            return OperationResult.success(op, self._send(self.running_config_command))
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)

    def backup_configuration(self) -> OperationResult:
        op = Op.BACKUP_CONFIGURATION
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.failed(op, running.message)
        text = str(running.data)
        if not text.strip():
            return OperationResult.failed(op, "Device returned an empty configuration")
        ref = "undm-stored-" + hashlib.sha256(text.encode()).hexdigest()[:12]
        return OperationResult.success(
            op, ConfigurationBackup(self.target.device_id, text, ref),
            message="running configuration stored by UNDM (nothing written to the device)",
        )

    # -- impacting ------------------------------------------------------------------
    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        op = Op.APPLY_CONFIGURATION
        if mode is not ApplyMode.MERGE:
            return OperationResult.unsupported(op, "Only merge mode is supported over SSH")
        if r := self._need(op):
            return r
        lines = self.config_lines(config)
        if not lines:
            return OperationResult.failed(op, "Nothing to send after removing comments")
        try:
            from netmiko.exceptions import ConfigInvalidException

            output = self._conn.send_config_set(
                lines, error_pattern=self.error_pattern, read_timeout=self.read_timeout)
        except ConfigInvalidException as e:
            return OperationResult.failed(
                op, "Device rejected a configuration line; it may be partially applied",
                {"device_output": redact_text(str(e))[-2000:]})
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        return OperationResult.success(
            op, message=f"{len(lines)} line(s) sent",
            data={"output": redact_text(str(output))[-2000:]})

    def save_configuration(self) -> OperationResult:
        op = Op.SAVE_CONFIGURATION
        if r := self._need(op):
            return r
        try:
            output = self._conn.save_config()
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        return OperationResult.success(op, message="configuration saved",
                                       data={"output": redact_text(str(output))[-500:]})
