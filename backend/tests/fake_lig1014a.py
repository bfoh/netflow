"""A stand-in for a Black Box LIG1014A CLI over SSH (raw channel).

The LAYOUT of 'show version', 'show running-config' and the bare '#' prompt of a factory
unit is taken from the switch's own output (bench, v00.01.00, 2026-11-24); the VALUES are
placeholders (MAC address, times). The refusal text for unknown commands is SYNTHETIC.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
Image            : LIG1014A_v00.01.00.dat (backup)
Version          : v00.01.00
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


@dataclass
class FakeLig1014A:
    password: str = ""
    hostname: str = ""
    mac: str = "00-11-22-33-44-55"
    serial: str = ""
    version: str = "v00.01.00"
    truncate_config: bool = False  # output stops before 'end' (e.g. a page break)
    commands: list[str] = field(default_factory=list)
    _out: str = ""

    def accept_connection(self, password: str | None = None) -> None:
        if password is not None and password != self.password:
            from netmiko.exceptions import NetmikoAuthenticationException
            raise NetmikoAuthenticationException("Authentication failed")
        self._out = self.prompt_text()

    def prompt_text(self) -> str:
        return f"{self.hostname}# "

    def show(self, command: str) -> str:  # Netmiko send_command is not used by the driver
        raise AssertionError(f"send_command used for {command!r}")

    def write(self, data: str) -> None:
        text = data.strip()
        self._out += data.rstrip("\n") + "\r\n"
        if text:
            self.commands.append(text)
        if text == "show version":
            self._out += SHOW_VERSION.format(
                mac=self.mac, version=self.version,
                serial=f" {self.serial}" if self.serial else "",
                name=f" {self.hostname}" if self.hostname else "").replace("\n", "\r\n")
        elif text == "show running-config":
            body = FACTORY_CONFIG.format(mac=self.mac)
            if self.truncate_config:
                body = body.rsplit("\n", 3)[0] + "\n -- more --, next page: Space, continue: g"
                self._out += body.replace("\n", "\r\n")
                return  # waits at the page break: no prompt
            self._out += body.replace("\n", "\r\n") + "\r\n"
        elif text:
            self._out += UNKNOWN + "\r\n"
        self._out += self.prompt_text()

    def read(self) -> str:
        out, self._out = self._out, ""
        return out
