"""Console bootstrap for ArubaOS-Switch (e.g. Aruba 2930F).

Gives a factory-default switch a management address on an out-of-band VLAN so it can
be reached over the network, using the commands the product owner's team types by
hand today:

    configure / vlan <id> / name "<name>" / untagged <port> / ip address <ip> <mask> / exit

followed by ``write memory``.

NOT YET VALIDATED ON HARDWARE. Prompt handling ("Press any key to continue", manager
prompt ``#``, operator prompt ``>``, ``(config)`` / ``(vlan-N)`` contexts) follows the
behaviour Netmiko's driver for this family relies on, and the error strings are
best-effort. The procedure therefore never trusts transmission: it stops at the first
error marker, and success is decided by reading the configuration back.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from ipaddress import IPv4Interface

from undm.drivers.base import Credentials
from undm.provisioning.console import ConsoleError, ConsoleSession

PROMPT = re.compile(
    r"(?:^|\n)[ \t]*(?P<name>[A-Za-z0-9_.-]{1,64})(?P<ctx>\([A-Za-z0-9_/ .-]*\))?(?P<mode>[#>]) ?$")
ANY_KEY = re.compile(r"any key to continue\s*$", re.I)
LOGIN = re.compile(r"(?:user ?name|login as|login)\s*:\s*$", re.I)
PASSWORD = re.compile(r"password\s*:\s*$", re.I)
ERROR = re.compile(r"Invalid input|Incomplete input|Ambiguous input|invalid port|"
                   r"not allowed|Error:|Unable to", re.I)

_VLAN_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_PORT = re.compile(r"^[A-Za-z0-9/]{1,8}$")
# Lines that indicate the switch already carries a site configuration.
_SITE_CONFIG = ("ip authorized-managers", "ip route", "logging ", "sntp server", "aaa ",
                "radius-server", "tacacs-server", "banner ", "timesync ")


class BootstrapStatus(StrEnum):
    BOOTSTRAPPED = "bootstrapped"
    ALREADY_CONFIGURED = "already_configured"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(frozen=True)
class BootstrapParams:
    vlan_id: int
    vlan_name: str
    untagged_port: str
    address: IPv4Interface

    def __post_init__(self) -> None:
        if not 2 <= self.vlan_id <= 4094:
            raise ValueError("VLAN ID must be 2-4094 (VLAN 1 is the default VLAN)")
        if not _VLAN_NAME.match(self.vlan_name):
            raise ValueError("VLAN name: 1-32 letters, digits, '_', '.', '-'")
        if not _PORT.match(self.untagged_port):
            raise ValueError("Port: letters, digits and '/' only (e.g. 2, 1/2, A1)")
        if self.address.network.prefixlen >= 31 or self.address.ip in (
                self.address.network.network_address, self.address.network.broadcast_address):
            raise ValueError("Address must be a host address in its subnet")

    @property
    def ip_line(self) -> str:
        return f"ip address {self.address.ip} {self.address.netmask}"

    def commands(self) -> list[str]:
        return ["configure", f"vlan {self.vlan_id}", f'name "{self.vlan_name}"',
                f"untagged {self.untagged_port}", self.ip_line, "exit", "write memory"]


@dataclass
class BootstrapResult:
    status: BootstrapStatus
    message: str
    commands_sent: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    verified: bool = False
    saved: bool = False
    transcript: str = ""


def _expand_ports(spec: str) -> set[str]:
    ports: set[str] = set()
    for part in spec.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            ports.update(str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1))
        elif part:
            ports.add(part)
    return ports


def parse_vlans(running_config: str) -> dict[int, list[str]]:
    """VLAN id -> stripped lines of its block."""
    vlans: dict[int, list[str]] = {}
    current: int | None = None
    for raw in running_config.splitlines():
        line = raw.strip()
        m = re.fullmatch(r"vlan (\d+)", line)
        if m and not raw.startswith((" ", "\t")):
            current = int(m.group(1))
            vlans[current] = []
        elif current is not None:
            if line == "exit":
                current = None
            elif line:
                vlans[current].append(line)
    return vlans


def is_configured(running_config: str, p: BootstrapParams) -> bool:
    block = parse_vlans(running_config).get(p.vlan_id)
    if block is None or p.ip_line not in block:
        return False
    return any(ln.startswith("untagged ") and p.untagged_port in _expand_ports(ln[9:])
               for ln in block)


def site_config_findings(running_config: str, p: BootstrapParams) -> list[str]:
    """Signs that the switch is not factory default (so a bootstrap could disturb it)."""
    findings: list[str] = []
    vlans = parse_vlans(running_config)
    others = sorted(v for v in vlans if v not in (1, p.vlan_id))
    if others:
        findings.append(f"VLANs other than 1 already exist: {', '.join(map(str, others))}")
    for vid, block in vlans.items():
        for ln in block:
            if ln.startswith("ip address ") and ln != "ip address dhcp-bootp" and not (
                    vid == p.vlan_id and ln == p.ip_line):
                findings.append(f"VLAN {vid} already has a static address")
    for raw in running_config.splitlines():
        line = raw.strip()
        if not raw.startswith((" ", "\t")) and line.startswith(_SITE_CONFIG):
            findings.append(f"site configuration present: '{line.split()[0]} "
                            f"{line.split()[1] if len(line.split()) > 1 else ''}…'")
    return sorted(set(findings))


class ArubaOSSwitchConsole:
    """Minimal console dialogue for ArubaOS-Switch."""

    def __init__(self, session: ConsoleSession, credentials: Credentials | None = None,
                 wake_delay: float = 0.5, login_timeout: float = 12.0) -> None:
        self.s = session
        self.credentials = credentials
        self.wake_delay = wake_delay
        self.login_timeout = login_timeout

    def _credential(self, what: str) -> str:
        if self.credentials is None:
            raise ConsoleError(
                f"The switch asks for a {what}: it is not in factory-default state (a "
                "password is set). Attach a credential to the device, or factory-reset it.")
        return self.credentials.username if what == "username" else self.credentials.password

    def login(self) -> str:
        """Reach the manager prompt (#) at top level. Returns the prompt's hostname."""
        self.s.write_line()  # the console auto-senses speed on the first key presses
        time.sleep(self.wake_delay)
        self.s.write_line()
        text = ""
        for _ in range(8):
            idx, text = self.s.read_until_any(
                [PROMPT, ANY_KEY, LOGIN, PASSWORD], timeout=self.login_timeout)
            if idx == 0:
                break
            if idx == 1:
                self.s.write_line()
            elif idx == 2:
                self.s.write_line(self._credential("username"))
            else:
                self.s.transcript.append("<<< (password sent)\n")
                self.s.transport.write((self._credential("password") + "\r").encode())
        else:
            raise ConsoleError("Could not reach a command prompt on the console")
        m = PROMPT.search(text)
        assert m is not None
        if m["mode"] == ">":  # operator level
            self.s.write_line("enable")
            for _ in range(4):
                idx, text = self.s.read_until_any(
                    [PROMPT, LOGIN, PASSWORD], timeout=self.login_timeout)
                if idx == 0:
                    break
                if idx == 1:
                    self.s.write_line(self._credential("username"))
                else:
                    self.s.transcript.append("<<< (password sent)\n")
                    self.s.transport.write((self._credential("password") + "\r").encode())
            m = PROMPT.search(text)
            if m is None or m["mode"] != "#":
                raise ConsoleError("Could not enter manager (enable) level")
        if m["ctx"]:  # left in a configuration context by an earlier session
            self.command("end")
        self.command("no page")  # session only
        return str(m["name"])

    def command(self, cmd: str, timeout: float | None = None) -> str:
        self.s.write_line(cmd)
        _, text = self.s.read_until_any([PROMPT], timeout=timeout)
        return text

    def running_config(self) -> str:
        return self.command("show running-config", timeout=30)


def bootstrap(console: ArubaOSSwitchConsole, params: BootstrapParams,
              *, allow_configured: bool = False) -> BootstrapResult:
    """Run the bootstrap. Never raises for device-side problems; returns a result."""
    s = console.s
    sent: list[str] = []

    def done(status: BootstrapStatus, message: str, **kw: object) -> BootstrapResult:
        return BootstrapResult(status, message, commands_sent=sent,
                               transcript=s.transcript_text, **kw)  # type: ignore[arg-type]

    try:
        console.login()
        before = console.running_config()
        if is_configured(before, params):
            return done(BootstrapStatus.ALREADY_CONFIGURED,
                        f"VLAN {params.vlan_id} already has {params.address} with port "
                        f"{params.untagged_port} untagged; nothing was changed", verified=True)
        findings = site_config_findings(before, params)
        if findings and not allow_configured:
            return done(BootstrapStatus.REFUSED,
                        "The switch does not look factory default; nothing was changed",
                        findings=findings)
        commands = params.commands()
        for cmd in commands[:-1]:
            sent.append(cmd)
            output = console.command(cmd)
            if ERROR.search(output):
                console.command("end")
                return done(
                    BootstrapStatus.FAILED,
                    f"The switch rejected '{cmd}'. Earlier commands changed the running "
                    "configuration but nothing was saved: reboot the switch without saving "
                    "to discard them.", findings=findings)
        console.command("end")
        after = console.running_config()
        if not is_configured(after, params):
            return done(BootstrapStatus.FAILED,
                        "Commands were accepted but the configuration read back does not "
                        "show the expected VLAN, port and address. Nothing was saved.",
                        findings=findings)
        sent.append(commands[-1])
        output = console.command(commands[-1], timeout=30)
        if ERROR.search(output):
            return done(BootstrapStatus.FAILED,
                        "Configuration is applied but 'write memory' reported an error; it "
                        "will be lost on reboot.", findings=findings, verified=True)
        return done(BootstrapStatus.BOOTSTRAPPED,
                    f"VLAN {params.vlan_id} ({params.vlan_name}) with port "
                    f"{params.untagged_port} untagged and address {params.address}, saved",
                    findings=findings, verified=True, saved=True)
    except ConsoleError as e:
        return done(BootstrapStatus.FAILED, str(e))
