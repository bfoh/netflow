"""Simulated ArubaOS-Switch console.

SYNTHETIC: written to exercise the bootstrap logic and to demonstrate the workflow
without hardware. It is not a capture of a real switch console; banner text, default
hostname and error wording are approximations. Real console behaviour is validated
separately on bench equipment (docs/vendor-support/aruba-2930f-console-bootstrap.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BANNER = ("\r\nSIMULATED SWITCH CONSOLE (UNDM)\r\n"
          "Aruba 2930F simulation - not a real device\r\n\r\n")


@dataclass
class SimulatedArubaConsole:
    hostname: str = "Aruba-2930F-48G-4SFP"
    port_count: int = 52
    username: str | None = None  # set both to simulate a switch with a manager password
    password: str | None = None
    operator_level: bool = False  # lands on '>' and needs 'enable'
    silent: bool = False  # never answers (dead cable / wrong port)
    extra_config: list[str] = field(default_factory=list)  # top-level site config lines
    fail_on: set[str] = field(default_factory=set)  # commands answered with an error
    silently_ignore: set[str] = field(default_factory=set)  # accepted but without effect

    def __post_init__(self) -> None:
        self._out = bytearray()
        self._in = ""
        self._state = "asleep"
        self._enters = 0
        self._ctx: list[str] = []
        self._manager = not self.operator_level
        self.vlans: dict[int, dict[str, object]] = {
            1: {"name": "DEFAULT_VLAN", "untagged": set(map(str, range(1, self.port_count + 1))),
                "ip": "dhcp-bootp"}}
        self.saved_config: str | None = None
        self.commands_received: list[str] = []
        self.closed = False

    # -- transport -----------------------------------------------------------------
    def read(self, size: int = 1) -> bytes:
        data = bytes(self._out[:size])
        del self._out[:size]
        return data

    def write(self, data: bytes) -> int:
        self._in += data.decode("ascii", "replace")
        while "\r" in self._in:
            line, self._in = self._in.split("\r", 1)
            if not self.silent:
                self._handle(line)
        return len(data)

    def close(self) -> None:
        self.closed = True

    # -- behaviour -----------------------------------------------------------------
    def _emit(self, text: str) -> None:
        self._out += text.encode()

    def _prompt(self) -> str:
        ctx = f"({self._ctx[-1]})" if self._ctx else ""
        return f"{self.hostname}{ctx}{'#' if self._manager else '>'} "

    def _handle(self, line: str) -> None:
        if self._state == "asleep":
            self._enters += 1
            if self._enters >= 2:
                self._emit(BANNER + "Press any key to continue")
                self._state = "anykey"
            return
        if self._state == "anykey":
            if self.username is not None:
                self._emit("\r\nUsername: ")
                self._state = "username"
            else:
                self._state = "cli"
                self._emit("\r\n" + self._prompt())
            return
        if self._state == "username":
            self._typed_user = line
            self._emit("\r\nPassword: ")
            self._state = "password"
            return
        if self._state == "password":
            if line == self.password and self._typed_user == self.username:
                self._state = "cli"
                self._emit("\r\n" + self._prompt())
            else:
                self._emit("\r\nInvalid password\r\nUsername: ")
                self._state = "username"
            return
        cmd = line.strip()
        self._emit(line + "\r\n")  # echo
        if cmd:
            self.commands_received.append(cmd)
            self._emit(self._run(cmd))
        self._emit(self._prompt())

    def _run(self, cmd: str) -> str:
        if cmd in self.fail_on:
            return f"Invalid input: {cmd.split()[0]}\r\n"
        if cmd in self.silently_ignore:
            return ""
        if cmd == "enable":
            self._manager = True
            return ""
        if cmd == "no page":
            return ""
        if cmd == "end":
            self._ctx = []
            return ""
        if cmd == "exit":
            if self._ctx:
                self._ctx.pop()
            return ""
        if cmd == "show running-config":
            return self.render().replace("\n", "\r\n")
        if not self._manager:
            return f"Invalid input: {cmd.split()[0]}\r\n"
        if cmd in ("configure", "configure terminal", "config"):
            self._ctx = ["config"]
            return ""
        if cmd == "write memory":
            self.saved_config = self.render()
            return ""
        if self._ctx:
            m = re.fullmatch(r"vlan (\d+)", cmd)
            if m:
                vid = int(m.group(1))
                self.vlans.setdefault(vid, {"name": f"VLAN{vid}", "untagged": set(), "ip": None})
                self._ctx = ["config", f"vlan-{vid}"]
                return ""
            if self._ctx[-1].startswith("vlan-"):
                vlan = self.vlans[int(self._ctx[-1][5:])]
                if m := re.fullmatch(r'name "([^"]+)"', cmd):
                    vlan["name"] = m.group(1)
                    return ""
                if m := re.fullmatch(r"untagged (\S+)", cmd):
                    port = m.group(1)
                    if not port.isdigit() or not 1 <= int(port) <= self.port_count:
                        return f"Module not present for port or invalid port: {port}\r\n"
                    for other in self.vlans.values():
                        other["untagged"].discard(port)  # type: ignore[attr-defined]
                    vlan["untagged"].add(port)  # type: ignore[attr-defined]
                    return ""
                if m := re.fullmatch(r"ip address (\S+)(?: (\S+))?", cmd):
                    vlan["ip"] = cmd[len("ip address "):]
                    return ""
        return f"Invalid input: {cmd.split()[0]}\r\n"

    @staticmethod
    def _ranges(ports: set[str]) -> str:
        """{1,2,3,5} -> "1-3,5"."""
        nums = sorted(int(p) for p in ports)
        groups: list[list[int]] = []
        for n in nums:
            if groups and n == groups[-1][1] + 1:
                groups[-1][1] = n
            else:
                groups.append([n, n])
        return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in groups)

    def render(self) -> str:
        lines = ["", "Running configuration:", "",
                 "; SIMULATED Configuration Editor; Created on release #WC.16.10.0025",
                 f'hostname "{self.hostname}"', *self.extra_config,
                 'snmp-server community "public" unrestricted']
        for vid in sorted(self.vlans):
            v = self.vlans[vid]
            lines.append(f"vlan {vid}")
            lines.append(f'   name "{v["name"]}"')
            if v["untagged"]:
                lines.append(f"   untagged {self._ranges(v['untagged'])}")  # type: ignore[arg-type]
            if v["ip"]:
                lines.append(f"   ip address {v['ip']}")
            lines.append("   exit")
        return "\n".join(lines) + "\n"
