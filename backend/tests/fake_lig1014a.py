"""A stand-in for a Black Box LIG1014A CLI over SSH (raw channel).

The LAYOUT of 'show version', 'show running-config' and the bare '#' prompt of a factory
unit is taken from the switch's own output (bench, v00.01.00, 2026-11-24); the VALUES are
placeholders (MAC address, times). The refusal text for unknown commands is SYNTHETIC.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import tftpy

SHOW_VERSION = """
MEMORY           : Total=88302 KBytes, Free=71456 KBytes, Max=70517 KBytes
FLASH            : 0x40000000-0x40ffffff, 256 x 0x10000 blocks
MAC Address      : {mac}
Previous Restart : Cold

Serial Number    :{serial}
System Contact   :
System Name      :{name}
System Location  :
System Time      : 2017-01-01T03:18:09+00:00
System Uptime    : 03:18:11

Active Image
------------
Image            : LIG1014A_{version}.dat (primary)
Version          : {version}
Date             : 2021-01-29T19:32:27+08:00

Alternate Image
---------------
Image            : LIG1014A_{alternate}.dat (backup)
Version          : {alternate}
Date             : 2021-01-29T19:32:27+08:00

------------------
SID : 1
------------------
Board Type       : LIG1014A
Port Count       : 14
Software Version : {version}
Build Date       : 2021-01-29T19:32:27+08:00
"""

FACTORY_CONFIG = """Building configuration...
username admin privilege 15 password none
!
vlan 1
!
spanning-tree mst name {mac} revision 0
!
interface GigabitEthernet 1/1
 description Port-1
!
interface GigabitEthernet 1/3
 description Port-3
!
interface vlan 1
 ip address 192.0.2.1 255.255.255.0
!
end"""

UNKNOWN = "% Invalid word detected"  # synthetic
# The page prompt as the switch showed it (bench, 2026-11-24); how it is erased: synthetic.
MORE = "-- more --, next page: Space, continue: g, quit: ^C"
RELOAD = "% Cold reload in progress, please stand by."  # bench wording
IMAGE_HEADER = b"SYNTHETIC LIG1014A IMAGE "  # + version + newline


@dataclass
class FakeLig1014A:
    password: str = ""
    hostname: str = ""
    mac: str = "00-11-22-33-44-55"
    serial: str = ""
    version: str = "v00.01.00"
    page_after: int | None = None  # pause long output after this many lines (bench)
    tftp_port: object = 69  # callable returning UNDM's TFTP port, for 'copy tftp://'
    password_after_load: str | None = None  # admin password the loaded file sets
    copy_refusal: str = ""  # e.g. a synthetic '% ...' line: the file is refused
    reload_ignored: bool = False
    down_for_connects: int = 1
    startup: str | None = None  # file loaded into the startup configuration
    running_file: str | None = None  # file the switch runs after the restart
    restarts: int = 0
    alternate: str = "v00.01.00"
    # firmware upgrade behaviour (wording SYNTHETIC until seen on the bench):
    # restart | prompt_then_restart | prompt_only | refuse
    upgrade_mode: str = "restart"
    _close_after: int = 0
    fetched: list[str] = field(default_factory=list)
    _closing: bool = False
    _down: int = 0
    stall_config: bool = False  # 'show running-config' stops part-way, no prompt
    commands: list[str] = field(default_factory=list)
    _out: str = ""
    _rest: str | None = None
    keys: list[str] = field(default_factory=list)

    def accept_connection(self, password: str | None = None) -> None:
        if self._down > 0:
            self._down -= 1
            raise OSError("connection timed out (switch restarting)")
        self._closing = False
        if password is not None and password != self.password:
            from netmiko.exceptions import NetmikoAuthenticationException
            raise NetmikoAuthenticationException("Authentication failed")
        self._out = self.prompt_text()

    def prompt_text(self) -> str:
        return f"{self.hostname}# "

    def show(self, command: str) -> str:  # Netmiko send_command is not used by the driver
        raise AssertionError(f"send_command used for {command!r}")

    def _emit(self, text: str) -> None:
        """Command output, paused once at the page prompt if page_after is set."""
        lines = text.split("\n")
        if self.page_after is not None and len(lines) > self.page_after:
            self._out += "\r\n".join(lines[:self.page_after]) + "\r\n" + MORE
            self._rest = "\r\n".join(lines[self.page_after:]) + "\r\n"
            return
        self._out += "\r\n".join(lines) + "\r\n" + self.prompt_text()

    def write(self, data: str) -> None:
        if self._rest is not None:  # at the page prompt: one key, no Enter
            self.keys.append(data)
            if data == "g":
                self._out += "\r" + " " * len(MORE) + "\r" + self._rest + self.prompt_text()
                self._rest = None
            return
        text = data.strip()
        self._out += data.rstrip("\n") + "\r\n"
        if text:
            self.commands.append(text)
        if text == "show version":
            self._emit(SHOW_VERSION.format(
                mac=self.mac, version=self.version, alternate=self.alternate,
                serial=f" {self.serial}" if self.serial else "",
                name=f" {self.hostname}" if self.hostname else ""))
        elif m := re.fullmatch(r"copy tftp://([^/\s]+)/(\S+) startup-config", text):
            port = self.tftp_port() if callable(self.tftp_port) else self.tftp_port
            buf = io.BytesIO()
            tftpy.TftpClient(m.group(1), port, {}).download(m.group(2), buf, timeout=2)
            self.fetched.append(m.group(2))
            if self.copy_refusal:  # fetched, then refused: the startup config is unchanged
                self._out += self.copy_refusal + "\r\n" + self.prompt_text()
                return
            data = buf.getvalue()
            self.startup = data.decode()
            self._out += (f"% Loading /{m.group(2)} from TFTP server {m.group(1)}\r\n"
                          f"% Saving {len(data)} bytes to flash:startup-config\r\n"
                          "Import Done! Configuration will become active after reboot!\r\n"
                          + self.prompt_text())  # bench wording
        elif m := re.fullmatch(r"firmware upgrade tftp://([^/\s]+)/(\S+)", text):
            port = self.tftp_port() if callable(self.tftp_port) else self.tftp_port
            buf = io.BytesIO()
            tftpy.TftpClient(m.group(1), port, {}).download(m.group(2), buf, timeout=2)
            self.fetched.append(m.group(2))
            data = buf.getvalue()
            if self.upgrade_mode == "refuse" or not data.startswith(IMAGE_HEADER):
                self._out += "% Image check failed\r\n" + self.prompt_text()  # synthetic
                return
            new = data[len(IMAGE_HEADER):].split(b"\n", 1)[0].decode()
            self.alternate = new  # written to the alternate slot (synthetic behaviour)
            if self.upgrade_mode == "prompt_only":
                self._out += self.prompt_text()
                return
            self.alternate, self.version = self.version, new
            if self.upgrade_mode == "prompt_then_restart":
                self._out += self.prompt_text()
                self.restarts += 1
                self._down = self.down_for_connects
                self._close_after = 3
                return
            self.restarts += 1
            self._down = self.down_for_connects
            self._closing = True
        elif text == "reload cold":
            if self.reload_ignored:
                self._out += self.prompt_text()
                return
            self._out += RELOAD + "\r\n" + self.prompt_text()  # the prompt still appears
            self._restart()
        elif text == "show running-config" and self.running_file is not None:
            self._emit("Building configuration...\n" + self.running_file.strip("\n"))
        elif text == "show running-config":
            body = FACTORY_CONFIG.format(mac=self.mac)
            if self.stall_config:
                self._out += body.rsplit("\n", 3)[0].replace("\n", "\r\n")
                return  # stops part-way: no prompt
            self._emit(body)
        elif text:
            self._out += UNKNOWN + "\r\n" + self.prompt_text()
        else:
            self._out += self.prompt_text()

    def _restart(self) -> None:
        self.restarts += 1
        self._down = self.down_for_connects
        self._closing = True
        if self.startup is not None:
            self.running_file = self.startup
            m = re.search(r"^hostname (\S+)", self.startup, re.M)
            self.hostname = m.group(1) if m else ""
            if self.password_after_load is not None:
                self.password = self.password_after_load

    def read(self) -> str:
        if self._close_after:
            self._close_after -= 1
            self._closing = self._close_after == 0
        out, self._out = self._out, ""
        if self._closing and not out:
            raise OSError("Software caused connection abort")
        return out
