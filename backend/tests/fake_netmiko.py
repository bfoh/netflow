"""Fake Netmiko connections for SSH driver tests.

The command outputs below are SYNTHETIC examples written for these tests in the
general shape of each platform's output. They exercise the drivers' logic; they
are not captured from real devices and do not prove parser accuracy on hardware.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from netmiko.exceptions import ConfigInvalidException

IOSXE_SHOW_VERSION = """Cisco IOS XE Software, Version 17.09.04a
lab-r1 uptime is 2 weeks, 1 day
cisco ISR4331/K9 (1RU) processor with 1795999K/6147K bytes of memory.
Processor board ID FDO0000TEST
"""
AOSCX_SHOW_SYSTEM = """Hostname                : lab-sw1
Product Name            : JL659A 6300M 48SR5 CL6 PoE 4SFP56 Swch
Chassis Serial Nbr      : SG00TEST01
"""
AOSCX_SHOW_VERSION = """Version      : FL.10.13.1000
"""
FORTIOS_STATUS = """Version: FortiGate-60F v7.2.8,build1639,240313 (GA.M)
Serial-Number: FGT60FTK00000000
Hostname: lab-fw1
Virtual domain configuration: disable
"""


@dataclass
class Scenario:
    outputs: dict[str, str] = field(default_factory=dict)
    running: str = "hostname lab-r1\n"
    bad_lines: set[str] = field(default_factory=set)
    hidden_lines: set[str] = field(default_factory=lambda: {"no shutdown"})
    prompt: str = "lab-r1#"
    connect_error: Exception | None = None
    calls: list[tuple[str, object]] = field(default_factory=list)
    saved: int = 0
    # Optional stateful device (see fake_aos_switch.py) behind the connection.
    device: object | None = None


class FakeConnection:
    def __init__(self, scenario: Scenario, **kwargs: object) -> None:
        self.s = scenario
        self.kwargs = kwargs
        scenario.calls.append(("connect", {k: v for k, v in kwargs.items()
                                          if k not in ("password", "secret")}))

    RETURN = "\n"

    # Netmiko's connection steps (BaseConnection._open), used with auto_connect=False.
    def _modify_connection_params(self) -> None:
        pass

    def establish_connection(self) -> None:
        pass

    def _try_session_preparation(self, force_data: bool = False) -> None:
        from netmiko.exceptions import ReadTimeout
        if getattr(self.s.device, "awaiting_login_answers", False):
            raise ReadTimeout("Pattern not detected: 'to accept|[#$]' in output.")
        # Like Netmiko's FortinetSSH: Enter is not pressed first, so the prompt the device
        # printed by itself must still be readable (bench, 2026-11-24).
        if self.kwargs.get("auto_connect") is False and not re.search(r"[#$]",
                                                                      self.read_channel()):
            raise ReadTimeout("Pattern not detected: 'to accept|[#$]' in output.")

    @property
    def base_prompt(self) -> str:
        if hasattr(self.s.device, "hostname"):
            return str(self.s.device.hostname)
        return self.s.prompt.rstrip("#> ")

    def set_base_prompt(self) -> str:
        return self.base_prompt

    def send_command(self, command: str, read_timeout: int = 0) -> str:
        self.s.calls.append(("send_command", command))
        if self.s.device is not None:
            return self.s.device.show(command)
        if command in ("show running-config", "show"):
            return self.s.running
        return self.s.outputs.get(command, "")

    def find_prompt(self) -> str:
        if hasattr(self.s.device, "prompt_text"):
            return self.s.device.prompt_text().strip()
        return self.s.prompt

    # Raw channel, used for commands that ask questions. Like Netmiko, text handed back
    # (``_read_buffer``) is returned before new output.
    _read_buffer = ""

    def clear_buffer(self) -> str:
        return self.read_channel()

    def write_channel(self, data: str) -> None:
        self.s.calls.append(("write_channel", data))
        self.s.device.write(data)

    def read_channel(self) -> str:
        out, self._read_buffer = self._read_buffer + self.s.device.read(), ""
        return out

    def send_config_set(self, lines, error_pattern: str = "", read_timeout: int = 0) -> str:
        self.s.calls.append(("send_config_set", list(lines)))
        applied = []
        for ln in lines:
            if ln.strip() in self.s.bad_lines:
                # Lines before the bad one are already applied, like on a real device.
                self.s.running += "".join(a + "\n" for a in applied)
                raise ConfigInvalidException(f"Invalid input detected at: {ln}")
            if ln.strip() not in self.s.hidden_lines:
                applied.append(ln)
        self.s.running += "".join(a + "\n" for a in applied)
        return "config output"

    def save_config(self) -> str:
        self.s.saved += 1
        return "[OK]"

    def disconnect(self) -> None:
        self.s.calls.append(("disconnect", None))


def factory_for(scenario: Scenario):
    def factory(**kwargs: object) -> FakeConnection:
        if scenario.connect_error is not None:
            raise scenario.connect_error
        if scenario.device is not None:
            if hasattr(scenario.device, "password"):  # checks the password it is given
                scenario.device.accept_connection(str(kwargs.get("password", "")))
            else:
                scenario.device.accept_connection()
        conn = FakeConnection(scenario, **kwargs)
        if kwargs.get("auto_connect", True):
            conn._try_session_preparation()
        return conn
    return factory

# ArubaOS-Switch (e.g. 2930F): two-column "show system" layout. SYNTHETIC.
AOS_SWITCH_SHOW_SYSTEM = """
 Status and Counters - General System Information

  System Name        : lab-2930f
  System Contact     :
  System Location    :

  Software revision  : WC.16.10.0012        Base MAC Addr      : 001122-334455
  ROM Version        : WC.17.02.0006        Serial Number      : CN00TEST01

  Up Time            : 6 days               Memory   - Total   : 330,059,264
"""
AOS_SWITCH_SHOW_MODULES = """
 Status and Counters - Module Information

  Chassis: 2930F-24G-4SFPP JL259A          Serial Number:   CN00TEST01
"""
AOS_SWITCH_RUNNING = """Running configuration:

; JL259A Configuration Editor; Created on release #WC.16.10.0012
hostname "lab-2930f"
vlan 1
   name "DEFAULT_VLAN"
   untagged 1-28
   ip address dhcp-bootp
   exit
"""
