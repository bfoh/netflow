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
    # A new unit that demands its manager credentials at first login. Prompt texts as seen
    # on a real new 2930F (2026-11-19); the refusal message is a placeholder.
    first_login_setup: bool = False
    min_password_length: int = 1
    setup_password_prompt: str = "Password: "  # noqa: S105 - prompt text, not a password
    setup_confirm_prompt: str = "Re-enter the new password: "
    # Console left at a password prompt of an unfinished setup (as on 2026-11-19): the first
    # key ends that session with the switch's real messages.
    left_at_password_prompt: bool = False
    # Prompts preceded by VT100 cursor codes, as seen on the bench ("ESC[24;18HPassword:").
    cursor_codes: bool = False
    max_read: int = 0  # >0: return at most this many bytes per read (splits escape codes)
    # A preconfigured unit as on the bench (2026-11-23): the console opens at operator level
    # without a login, and 'enable' asks for the manager username and password.
    enable_login: bool = False
    # After 'erase startup-config' the unit starts as new (asks for manager credentials).
    # The erase confirmation text below is SYNTHETIC (not yet seen on a real unit).
    setup_after_erase: bool = True
    # After the restart, wording as on the bench (WC.16.10.0025, 2026-11-23).
    speed_sense_after_erase: bool = False
    # As on the bench (2026-11-25, WC.16.10.0025): 'erase startup-config' cleared the
    # configuration but the manager login survived, so the console asked for it again.
    keep_passwords_on_erase: bool = False

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
        if self.max_read:
            size = min(size, self.max_read)
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
        codes = "\x1b[24;1H\x1b[2K" if self.cursor_codes else ""
        return f"{codes}{self.hostname}{ctx}{'#' if self._manager else '>'} "

    def _handle(self, line: str) -> None:
        if self._state == "asleep" and self.left_at_password_prompt:
            self.left_at_password_prompt = False
            self._emit("\r\nPassword cannot be empty.\r\nOperation aborted.\r\n\r\n"
                       "Session Terminated, unable to login.\r\n")
            self._enters = 0
            return
        if self._state == "asleep":
            self._enters += 1
            if self._enters >= 2:
                self._emit(BANNER + "Press any key to continue")
                self._state = "anykey"
            return
        if self._state == "anykey" and self.enable_login:
            self._state = "cli"  # operator level, no console login
            self._emit("\r\n" + self._prompt())
            return
        if self._state == "enable_user":
            self._typed_user = line
            self._emit(line + "\r\nPassword: ")
            self._state = "enable_password"
            return
        if self._state == "enable_password":
            self._state = "cli"
            if line == self.password and self._typed_user == self.username:
                self._manager = True
                self._emit("\r\n" + self._prompt())
            else:
                self._emit("\r\nUnable to verify password\r\n" + self._prompt())
            return
        if self._state == "set_password":
            self._new_password = line
            self._emit("*" * len(line) + "\r\nRe-enter the new password for manager:  ")
            self._state = "set_password_confirm"
            return
        if self._state == "set_password_confirm":
            self._state = "cli"
            self._emit("*" * len(line) + "\r\n")
            if line == self._new_password and line:
                self.username, self.password = "manager", line
                # The five notices seen on the bench after setting the password.
                self._emit("\r\nDHCP-based image file download from a TFTP server is disabled "
                           "when an operator\r\n or manager password is set.\r\n\r\nThe TFTP "
                           "Server is disabled when an operator or manager password is set."
                           "\r\n\r\nAutorun is disabled when an operator or manager password is "
                           "set.\r\n\r\n")
            else:
                self._emit("[placeholder] Passwords do not match\r\n")
            self._emit(self._prompt())
            return
        if self._state == "erase_confirm":
            self._state = "cli"
            if line.strip().lower() == "y":
                self._factory_reset()
                # As on the bench: after the restart the console is silent until a key is
                # pressed; the first Enter brings the banner.
                self._emit(" y\r\nRebooting...\r\n")
                if self.speed_sense_after_erase:
                    self._emit("Initialization done\r\n\r\nWaiting for Speed Sense.  Press "
                               "<Enter> twice to continue.\r\n")
                    self._state, self._enters = "asleep", 0
                else:
                    self._state, self._enters = "asleep", 1
            else:
                self._emit("\r\n" + self._prompt())
            return
        if self._state == "anykey":
            if self.first_login_setup and self.username is None:
                self._emit("\r\nConfigure the manager credentials :\r\nUsername: ")
                self._state = "setup_user"
                return
            if self.username is not None:
                self._emit("\r\nUsername: ")
                self._state = "username"
            else:
                self._state = "cli"
                self._emit("\r\n" + self._prompt())
            return
        if self._state == "setup_user":
            self._typed_user = line
            self._emit(line)  # the switch echoes the typed username
            self._emit("\r\n" + ("\x1b[24;18H" if self.cursor_codes else "")
                       + self.setup_password_prompt)
            self._state = "setup_password"
            return
        if self._state == "setup_password":
            self._new_password = line
            self._emit("\r\n" + ("\x1b[24;18H" if self.cursor_codes else "")
                       + self.setup_confirm_prompt)
            self._state = "setup_confirm"
            return
        if self._state == "setup_confirm":
            if line == self._new_password and len(line) >= self.min_password_length:
                self.username, self.password = self._typed_user, line
                self._state = "cli"
                self._emit("\r\n" + self._prompt())
            else:
                self._emit("\r\n[placeholder] Password not accepted\r\n"
                           "Configure the manager credentials :\r\nUsername: ")
                self._state = "setup_user"
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
                # Wording seen on the bench (2026-11-25).
                self._emit("\r\nAuthentication failed. Please verify that the username and "
                           "password are correct.\r\nUsername: ")
                self._state = "username"
            return
        cmd = line.strip()
        self._emit(line + "\r\n")  # echo
        if cmd:
            self.commands_received.append(cmd)
            self._emit(self._run(cmd))
        if self._state == "cli":  # not while a question is pending
            self._emit(self._prompt())

    def _run(self, cmd: str) -> str:
        if cmd in self.fail_on:
            return f"Invalid input: {cmd.split()[0]}\r\n"
        if cmd in self.silently_ignore:
            return ""
        if cmd == "enable":
            if self.enable_login and self.username is not None and not self._manager:
                self._state = "enable_user"
                return "Username: "
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
        if cmd == "password manager" and self._ctx:
            self._state = "set_password"
            return "New password for manager:  "
        if cmd == "erase startup-config":
            self._state = "erase_confirm"
            return "Configuration will be deleted and device rebooted, continue [y/n]? "
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

    def _factory_reset(self) -> None:
        self.hostname = "Aruba-2930F-48G-4SFP"
        self.extra_config = []
        if not self.keep_passwords_on_erase:
            self.username = self.password = None
        self.enable_login = False
        self.operator_level = False
        self._manager = True
        self._ctx = []
        self.first_login_setup = self.setup_after_erase
        self.vlans = {1: {"name": "DEFAULT_VLAN",
                          "untagged": set(map(str, range(1, self.port_count + 1))),
                          "ip": "dhcp-bootp"}}
        self.saved_config = None
        self.erased = getattr(self, "erased", 0) + 1

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
        if self.password:
            lines.append("password manager")
        return "\n".join(lines) + "\n"
