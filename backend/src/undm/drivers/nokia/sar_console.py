"""Nokia 7705 SAR-Hmc: reached over its console cable only. EXPERIMENTAL.

The unit has no management address from the factory, and the team stages it entirely over
the console:
- its first access (``undm.provisioning.sros_sar``, D-112) runs from Console setup;
- loading its configuration file is a normal plan (preview, approval, run; D-116), done by
  this driver over the device's console port.

What the driver sends, all from the team's console recording, the bench runs and Nokia's
7705 SAR Basic System Configuration Guide:
- the login (``Login:`` / ``Password:``) with the device's login, ``environment no more``
  and ``logout`` at the end (as in the first access);
- ``show system information`` for the facts (bench, 2026-11-26);
- ``admin display-config`` to read the running configuration (Nokia's guide: "admin
  display-config [detail | index]"; read-only). The team's file is this command's output;
- the file's configuration lines, one at a time, waiting for the prompt after each, and
  stopping at the first line answered with ``MINOR:``, ``MAJOR:``, ``CRITICAL:`` or
  ``Error:`` (Nokia's message formats);
- ``admin save``, which must answer "Completed." (bench).
Until ``admin save``, nothing is written to the unit's configuration file: switched off and
on, it starts with its saved configuration.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping
from typing import ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigFileReport,
    ConfigurationBackup,
    Credentials,
    DeviceDriver,
    DeviceFacts,
    DeviceTarget,
    DriverInfo,
    DriverMaturity,
    OperationResult,
)
from undm.drivers.nokia import sar_files
from undm.provisioning import sros_sar
from undm.provisioning.console import (
    ConsoleError,
    ConsoleSession,
    ConsoleTimeoutError,
    Transport,
    open_serial,
    port_lock,
)

_OP = DeviceOperation
NOT_SAVED = ("Nothing was saved: switched off and on, the modem starts with its saved "
             "configuration.")


class _Refused(Exception):
    def __init__(self, message: str, output: str = "", login_refused: bool = False) -> None:
        super().__init__(message)
        self.output = output
        self.login_refused = login_refused


class NokiaSarConsole(DeviceDriver):
    info: ClassVar[DriverInfo] = DriverInfo(
        driver_id="console.nokia.sar",
        vendor="Nokia",
        platform="sros_sar",
        os_family="SR OS (7705 SAR)",
        description="Nokia 7705 SAR-Hmc over its console cable (experimental): first access, "
                    "and its configuration file loaded line by line",
        simulated=False,
        capabilities=frozenset({Capability.SERIAL_CONSOLE, Capability.CONFIGURATION_BACKUP,
                                Capability.CONFIGURATION_APPLY}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="console",
        notes=(
            "Console cable only: the unit has no management address from the factory. UNDM "
            "uses the console port saved on the device (its first access saves it).",
            "First access (Console setup) passed once on hardware, 2026-11-26 (D-112).",
            "Loading its configuration (D-116): lines are sent one at a time and the load "
            "stops at the first refused line, unsaved. Passed once on hardware, 2026-11-26 "
            "(149 lines, about one minute).",
        ),
    )
    console_speed: ClassVar[int | None] = sros_sar.CONSOLE_SPEED
    # Replaced in tests by a simulated console.
    open_console: ClassVar[Callable[[str, int], Transport]] = staticmethod(open_serial)
    wake_timeout: ClassVar[float] = 10.0
    line_timeout: ClassVar[float] = 40.0
    settle_time: ClassVar[float] = 0.15

    def __init__(self, target: DeviceTarget, credentials: Credentials | None = None) -> None:
        super().__init__(target, credentials)
        self._session: ConsoleSession | None = None
        self._console: sros_sar.SarConsole | None = None
        self._transport: Transport | None = None
        self._locked: str | None = None
        self._saved = False  # 'admin save' confirmed during this plan

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        return sar_files.inspect_sros_file(text)

    # -- the console session ---------------------------------------------------------
    def connect(self) -> OperationResult:
        if self._console is not None:
            return OperationResult.success(_OP.CHECK_REACHABILITY, message="logged in")
        port = self.target.console_port
        if not port:
            return OperationResult.failed(
                _OP.CHECK_REACHABILITY,
                "UNDM does not know which serial port of this PC the modem's console cable "
                "is on: its first access in Console setup saves it, or set it with Edit on "
                "the device page.")
        if self._credentials is None:
            return OperationResult.failed(_OP.CHECK_REACHABILITY,
                                          "The modem has no login chosen in UNDM.")
        lock = port_lock(port)
        if not lock.acquire(blocking=False):
            return OperationResult.failed(
                _OP.CHECK_REACHABILITY,
                f"{port} is in use by another console session (Console setup or another "
                "plan). Try again when it has finished.")
        self._locked = port
        try:
            self._transport = type(self).open_console(port, sros_sar.CONSOLE_SPEED)
            self._session = ConsoleSession(self._transport, read_timeout=self.wake_timeout,
                                           settle_time=self.settle_time,
                                           secrets=[self._credentials.password])
            self._console = sros_sar.SarConsole(
                self._session, sros_sar.Timing(command=self.line_timeout))
            self._login(self._console, self._credentials)
        except ConsoleError as e:
            self.disconnect()
            return OperationResult.failed(_OP.CHECK_REACHABILITY, str(e))
        except _Refused as e:
            output = self._tail()
            self.disconnect()
            return OperationResult.failed(_OP.CHECK_REACHABILITY, str(e), diagnostics={
                "device_output": output, **({"login_refused": True} if e.login_refused
                                            else {})})
        return OperationResult.success(_OP.CHECK_REACHABILITY,
                                       message=f"logged in over the console on {port}")

    def _login(self, console: sros_sar.SarConsole, creds: Credentials) -> None:
        s = console.s
        for _ in range(3):
            s.write_line("")  # Enter: wakes the console up
            try:
                idx, _text = s.read_until_any(
                    [sros_sar.PROMPT, sros_sar.LOGIN, sros_sar.PASSWORD], self.wake_timeout)
            except ConsoleTimeoutError:
                continue
            if idx == 2:  # it asked for a password: an empty one makes it ask to log in
                continue
            if idx == 0 and not console.logout():  # someone is logged in: log out first
                continue
            if console.login(creds.username, creds.password, self.wake_timeout):
                console.command("environment no more")
                return
            raise _Refused(f"The modem refused the login (user '{creds.username}'). Choose "
                           "the login its first access set as the device's login.",
                           login_refused=True)
        raise _Refused(f"No login prompt from the modem on {self.target.console_port}. Check "
                       "that its console cable is on this port and that it is switched on and "
                       "started (about 3 minutes after power-on).")

    def disconnect(self) -> None:
        if self._console is not None:
            with contextlib.suppress(ConsoleError):
                self._console.logout()
        if self._transport is not None:
            with contextlib.suppress(OSError):
                self._transport.close()
        if self._locked is not None:
            port_lock(self._locked).release()
        self._console = self._session = self._transport = None
        self._locked = None

    def _tail(self, size: int = 1500) -> str:
        return self._session.transcript_text[-size:] if self._session is not None else ""

    def _ensure(self, op: DeviceOperation) -> OperationResult | None:
        """Logged in, or the reason it is not."""
        if self._console is None:
            conn = self.connect()
            if not conn.ok:
                return OperationResult.failed(op, conn.message, diagnostics=conn.diagnostics)
        return None

    def _command(self, op: DeviceOperation, cmd: str) -> tuple[OperationResult | None, str]:
        problem = self._ensure(op)
        if problem:
            return problem, ""
        assert self._console is not None
        try:
            return None, self._console.command(cmd)
        except ConsoleError as e:
            return OperationResult.failed(op, f"'{cmd}': {e}", diagnostics={
                "device_output": self._tail()}), ""

    # -- reads -------------------------------------------------------------------------
    def get_device_facts(self) -> OperationResult:
        problem, out = self._command(_OP.GET_FACTS, "show system information")
        if problem:
            return problem
        info = sros_sar.parse_system_information(out)
        if not info.get("name"):
            return OperationResult.failed(_OP.GET_FACTS, "The modem's system information was "
                                          "not recognised.", diagnostics={"device_output": out})
        return OperationResult.success(_OP.GET_FACTS, DeviceFacts(
            hostname=info["name"], vendor="Nokia", model=info.get("type", ""),
            os_version=info.get("version", ""), extra={
                "unsaved_changes": info.get("unsaved_changes", ""),
                "saved_config": info.get("saved_config", "")}))

    def get_running_configuration(self) -> OperationResult:
        problem, out = self._command(_OP.GET_RUNNING_CONFIGURATION, "admin display-config")
        if problem:
            return problem
        refused = sros_sar.ERROR.search(out)
        if refused or "configure" not in out:
            return OperationResult.failed(
                _OP.GET_RUNNING_CONFIGURATION,
                f"'admin display-config' was not answered with a configuration"
                f"{': ' + refused.group(0) if refused else ''}",
                diagnostics={"device_output": out[-1500:]})
        return OperationResult.success(_OP.GET_RUNNING_CONFIGURATION, _without_echo(out))

    def backup_configuration(self) -> OperationResult:
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.failed(_OP.BACKUP_CONFIGURATION, running.message,
                                          diagnostics=running.diagnostics)
        return OperationResult.success(_OP.BACKUP_CONFIGURATION, ConfigurationBackup(
            self.target.device_id, str(running.data),
            "running configuration before loading (unsaved until 'admin save')"))

    # -- the load ----------------------------------------------------------------------
    def prepare_for_device(self, config: str, secrets: Mapping[str, str]) -> str:
        plan = sar_files.plan_load(config)
        if plan.password_slot:
            problem = sros_sar.password_problem(self._credentials)
            if problem:
                raise ValueError(problem)
            assert self._credentials is not None
            return sar_files.fill_password(config, self._credentials.password)
        return config

    def check_before_apply(self, config: str, mode: ApplyMode) -> OperationResult | None:
        op = _OP.APPLY_CONFIGURATION
        if not sar_files.is_sros_configuration(config):
            return OperationResult.failed(op, "This is not a configuration file of the modem "
                                          "(no 'exit all' and 'configure' lines).")
        if mode is not ApplyMode.MERGE:
            return OperationResult.failed(op, "The modem's file is loaded line by line on top "
                                          "of its configuration (merge), not as a replacement.")
        plan = sar_files.plan_load(config)
        if plan.markers:
            return OperationResult.failed(op, f"The file still holds {', '.join(plan.markers)}:"
                                          " generate it for the system's zone and system.")
        if plan.password_slot:
            problem = sros_sar.password_problem(self._credentials)
            if problem:
                return OperationResult.failed(op, problem)
        written = sar_files.literal_passwords(config)
        if written and (self._credentials is None
                        or any(p != self._credentials.password for p in written)):
            return OperationResult.failed(op, "The file sets an admin password that is not the "
                                          "password of the modem's login: choose the login "
                                          "with that password, or generate the file from the "
                                          "template (it takes the login's password).")
        return None

    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        op = _OP.APPLY_CONFIGURATION
        if mode is not ApplyMode.MERGE:
            return OperationResult.unsupported(op, "The modem's file is loaded in merge mode")
        problem = self._ensure(op)
        if problem:
            return problem
        assert self._console is not None and self._session is not None
        plan = sar_files.plan_load(config)
        for secret in sar_files.literal_passwords(config):
            if secret not in self._session.secrets:
                self._session.secrets.append(secret)
        sent = 0
        for number, line in plan.lines:
            try:
                out = self._console.command(line)
            except ConsoleError as e:
                return OperationResult.failed(op, f"File line {number}: no answer from the "
                                              f"modem ({e}). {sent} line(s) were accepted. "
                                              f"{NOT_SAVED}",
                                              diagnostics={"device_output": self._tail()})
            refused = sros_sar.ERROR.search(out)
            if refused:
                return OperationResult.failed(
                    op, f"File line {number} '{self._session.mask(line.strip())[:120]}': the "
                    f"modem answered '{self._session.mask(refused.group(0))[:200]}'. {sent} "
                    f"line(s) before it were accepted. {NOT_SAVED}",
                    diagnostics={"device_output": self._tail()})
            sent += 1
        skipped = plan.skipped
        return OperationResult.success(op, {"notes": [
            f"{sent} configuration line(s) sent over the console, each accepted; not sent: "
            f"{skipped['comment']} comment, {skipped['echo']} echo, {skipped['save']} "
            "'admin save' line(s)"]}, message=f"{sent} line(s) accepted")

    def save_configuration(self) -> OperationResult:
        op = _OP.SAVE_CONFIGURATION
        problem, out = self._command(op, "admin save")
        if problem:
            return problem
        refused = sros_sar.ERROR.search(out)
        if refused or "Completed." not in out:
            return OperationResult.failed(
                op, "'admin save' was not confirmed"
                f"{' (' + refused.group(0)[:200] + ')' if refused else ' (no Completed.)'}. "
                "Every line was accepted, but the configuration may not be saved.",
                diagnostics={"device_output": out[-1500:]})
        self._saved = True
        return OperationResult.success(op, {"notes": ["saved ('admin save': Completed.)"]},
                                       message="saved ('admin save': Completed.)")

    def manual_recovery(self) -> str | None:
        if self._saved:
            return ("Its configuration was saved ('admin save'): check the modem on its "
                    "console before staging it again.")
        return NOT_SAVED + " Then make a new plan."

    def verify_configuration(self, intended: str, mode: ApplyMode) -> OperationResult | None:
        """Independent evidence (D-031): log in again with the modem's login (the file set
        its password), then its system information must show the file's system name and
        nothing unsaved."""
        op = _OP.APPLY_CONFIGURATION
        self.disconnect()
        conn = self.connect()
        if not conn.ok:
            return OperationResult.failed(op, f"after loading, the modem's login does not work "
                                          f"any more: {conn.message}",
                                          diagnostics=conn.diagnostics)
        facts = self.get_device_facts()
        if not facts.ok:
            return OperationResult.failed(op, facts.message, diagnostics=facts.diagnostics)
        data: DeviceFacts = facts.data
        wanted = sar_files.plan_load(intended).system_name
        if wanted and data.hostname != wanted:
            return OperationResult.failed(op, f"the modem calls itself '{data.hostname}', not "
                                          f"'{wanted}' as its file says")
        if str(data.extra.get("unsaved_changes", "")).strip().lower() != "no":
            return OperationResult.failed(op, "the modem reports changes since its last save")
        return OperationResult.success(op, message=(
            f"logged in again with its login; system name {data.hostname}; nothing unsaved"))

    def expected_lines(self, config: str) -> list[str]:
        """The file's configuration lines the unit shows as written (indentation ignored).
        Not the password line (the unit shows its hash) or the single ``config …`` lines
        (shown inside their section)."""
        out = []
        for _, line in sar_files.plan_load(config).lines:
            text = line.strip()
            if text in ("exit", "exit all", "configure") or text.startswith(("config ",
                                                                           "password ")):
                continue
            out.append(text)
        return out

    def present_lines(self, running: str) -> set[str]:
        return {ln.strip() for ln in running.splitlines() if ln.strip()}


def _without_echo(out: str) -> str:
    """The command's answer without its first line (the command echoed)."""
    first, _, rest = out.partition("\n")
    return rest if "display-config" in first else out


CONSOLE_DRIVERS: tuple[type[DeviceDriver], ...] = (NokiaSarConsole,)
