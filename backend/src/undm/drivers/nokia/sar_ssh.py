"""Nokia 7705 SAR-Hmc in the network after staging: read over SSH. EXPERIMENTAL (D-127).

On the bench the modem is reached over its console cable only (``sar_console``). Once its
file is loaded it has a network address, and the product owner reports that it answers SSH
there (Q-61, USER-CONFIRMED; not yet run from UNDM). This driver only reads:

- the SSH session is opened by Netmiko with its ``generic`` device type, which in Netmiko
  4.8 is its terminal-server class: it sends nothing when the session opens (no paging or
  terminal commands of another platform; Netmiko's ``nokia_sros`` type would send
  ``//environment more false``, which UNDM has not verified on this unit);
- the session's channel is read and written like the console, and the bench-proven
  ``SarConsole`` does the rest: the prompt, ``environment no more``, ``show system
  information`` (facts), ``admin display-config`` (backup) and ``logout`` at the end;
- if no prompt shows up by itself after the login, one Enter is sent to ask for it.

Applying, saving and every other change are unsupported: in the network UNDM does not change
devices, and changes on the bench go over the console.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    DriverInfo,
    DriverMaturity,
    OperationResult,
)
from undm.drivers.nokia.sar_console import NokiaSarConsole
from undm.drivers.ssh.base import _default_factory
from undm.provisioning import sros_sar
from undm.provisioning.console import ConsoleError, ConsoleSession, ConsoleTimeoutError
from undm.security.redaction import redact_text

_OP = DeviceOperation
_READ_ONLY = ("In the network UNDM only reads the modem: changes are made on the bench, over "
              "its console cable.")


class _Channel:
    """A Netmiko session's channel as a console transport (bytes in, bytes out)."""

    def __init__(self, conn: Any, poll: float = 0.05) -> None:
        self.conn = conn
        self.poll = poll

    def read(self, size: int = 1) -> bytes:
        text = str(self.conn.read_channel() or "")
        if not text:
            time.sleep(self.poll)
            return b""
        return text.encode("utf-8", "replace")

    def write(self, data: bytes) -> int | None:
        self.conn.write_channel(data.decode("utf-8", "replace"))
        return len(data)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.conn.disconnect()


class NokiaSarSsh(NokiaSarConsole):
    info: ClassVar[DriverInfo] = DriverInfo(
        driver_id="ssh.nokia.sar",
        vendor="Nokia",
        platform="sros_sar",
        os_family="SR OS (7705 SAR)",
        description="Nokia 7705 SAR-Hmc in the network, over SSH (experimental): reads only "
                    "(facts, backup)",
        simulated=False,
        capabilities=frozenset({Capability.SSH, Capability.CONFIGURATION_BACKUP}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "Used once the system is in the network (D-125): on the bench the modem is reached "
            "over its console cable.",
            "Not yet run on a modem: the product owner reports SSH answers after its file is "
            "loaded (Q-61). It sends only 'environment no more', 'show system information', "
            "'admin display-config' and 'logout'.",
        ),
    )
    network_driver_id: ClassVar[str | None] = None
    connection_factory: ClassVar[Callable[..., Any]] = staticmethod(_default_factory)
    connect_timeout: ClassVar[int] = 15

    def connect(self) -> OperationResult:
        op = _OP.CHECK_REACHABILITY
        if self._console is not None:
            return OperationResult.success(op, message="logged in")
        if self._credentials is None:
            return OperationResult.failed(op, "The modem has no login chosen in UNDM.")
        try:
            from netmiko.exceptions import (
                NetmikoAuthenticationException,
                NetmikoTimeoutException,
            )
        except ImportError:  # pragma: no cover - dependency is declared
            return OperationResult.failed(op, "netmiko is not installed")
        where = f"{self.target.management_address}:{self.target.port or 22}"
        try:
            conn = self.connection_factory(
                device_type="generic", host=self.target.management_address,
                port=self.target.port or 22, username=self._credentials.username,
                password=self._credentials.password, conn_timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout, banner_timeout=self.connect_timeout,
                fast_cli=False)
        except NetmikoAuthenticationException:
            return OperationResult.failed(
                op, f"The modem refused the login (user '{self._credentials.username}'). "
                    "Choose the login its first access set as the device's login.",
                {"login_refused": True})
        except NetmikoTimeoutException as e:
            return OperationResult.failed(
                op, f"No SSH answer from the modem at {where}. Check that this PC reaches its "
                    "network address through the BFW (route) and that SSH is on.",
                {"no_answer": True, "detail": " ".join(redact_text(str(e)).split())[-300:]})
        except Exception as e:  # noqa: BLE001 - report any transport error cleanly
            return OperationResult.failed(op, f"{type(e).__name__}: {redact_text(str(e))[:300]}")
        self._transport = _Channel(conn)
        self._session = ConsoleSession(self._transport, read_timeout=self.wake_timeout,
                                       settle_time=self.settle_time,
                                       secrets=[self._credentials.password])
        self._console = sros_sar.SarConsole(self._session,
                                            sros_sar.Timing(command=self.line_timeout))
        try:
            try:
                self._session.read_until_any([sros_sar.PROMPT], self.wake_timeout)
            except ConsoleTimeoutError:
                self._session.write_line("")  # Enter: asks for the prompt
                self._session.read_until_any([sros_sar.PROMPT], self.wake_timeout)
            self._console.command("environment no more")
        except ConsoleError as e:
            output = self._tail()
            self.disconnect()
            return OperationResult.failed(
                op, f"Logged in over SSH, but the modem did not show its prompt ({e}).",
                {"device_output": output, "login_accepted": True})
        return OperationResult.success(op, message=f"logged in over SSH at {where}")

    def disconnect(self) -> None:
        if self._session is not None:
            with contextlib.suppress(Exception):
                self._session.write_line("logout")  # the session then ends
        if self._transport is not None:
            self._transport.close()
        self._console = self._session = self._transport = None
        self._locked = None

    # -- nothing is changed in the network -------------------------------------------
    def prepare_for_device(self, config: str, secrets: Mapping[str, str]) -> str:
        raise ValueError(_READ_ONLY)

    def check_before_apply(self, config: str, mode: ApplyMode) -> OperationResult | None:
        return OperationResult.failed(_OP.APPLY_CONFIGURATION, _READ_ONLY)

    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        return OperationResult.unsupported(_OP.APPLY_CONFIGURATION, _READ_ONLY)

    def save_configuration(self) -> OperationResult:
        return OperationResult.unsupported(_OP.SAVE_CONFIGURATION, _READ_ONLY)

    def verify_configuration(self, intended: str, mode: ApplyMode) -> OperationResult | None:
        return OperationResult.unsupported(_OP.APPLY_CONFIGURATION, _READ_ONLY)

    def manual_recovery(self) -> str | None:
        return None


NETWORK_DRIVERS: tuple[type[NokiaSarConsole], ...] = (NokiaSarSsh,)
