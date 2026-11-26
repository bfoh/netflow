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
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface

from undm.drivers.base import Credentials
from undm.provisioning.console import ConsoleError, ConsoleSession, ConsoleTimeoutError
from undm.provisioning.results import BootstrapResult, BootstrapStatus

__all__ = ["BootstrapResult", "BootstrapStatus"]  # re-exported for existing callers

PROMPT = re.compile(
    r"(?:^|\n)[ \t]*(?P<name>[A-Za-z0-9_.-]{1,64})(?P<ctx>\([A-Za-z0-9_/ .-]*\))?(?P<mode>[#>]) ?$")
ANY_KEY = re.compile(r"any key to continue\s*$", re.I)
LOGIN = re.compile(r"(?:user ?name|login as|login)\s*:\s*$", re.I)
PASSWORD = re.compile(r"password\s*:\s*$", re.I)
# Seen on a new 2930F console (product owner's screenshots, 2026-11-19), in this order:
#   "Configure the manager credentials :" / "Username:" / "Password:" /
#   "Re-enter the new password:"
FIRST_LOGIN = re.compile(r"Configure the manager credentials", re.I)
# Case-sensitive "Password:" anywhere at the end: the console may position the cursor with
# control codes instead of a new line, so the prompt can follow the echoed username on the
# same line once those codes are removed. "Re-enter the new password:" is checked first.
SETUP_PASSWORD = re.compile(r"Password\s*:\s*$")
SETUP_REENTER = re.compile(r"Re-enter the new password\s*:\s*$", re.I)
# The console was left at a login prompt and the wake-up key answered it (seen
# 2026-11-19: "Password cannot be empty. / Operation aborted. / Session Terminated,
# unable to login."). Nothing was set; the login simply starts again.
TERMINATED = re.compile(r"Session Terminated, unable to login\.?\s*$", re.I)
# A refused login, then the username prompt again (bench, WC.16.10.0025, 2026-11-25).
AUTH_FAILED = re.compile(r"Authentication failed|Invalid password", re.I)
# Setting the manager password on a switch that has none (bench, WC.16.10.0025, 2026-11-23):
# in configuration mode, 'password manager' asks these two questions and echoes '*'.
SET_PASSWORD_COMMAND = "password manager"  # noqa: S105 - a CLI command, not a password
NEW_MANAGER_PASSWORD = re.compile(r"New password for manager\s*:\s*$", re.I)
REENTER_MANAGER_PASSWORD = re.compile(r"Re-enter the new password for manager\s*:\s*$", re.I)
PASSWORD_LINE = re.compile(r"^password manager\b", re.M)

# Printed by a 2930F (WC.16.10.0025) after a restart, before anything else (bench,
# 2026-11-23): the console senses its speed from two Enter key presses.
SPEED_SENSE = re.compile(
    r"Waiting for Speed Sense\.\s*Press <Enter> twice to continue\.?\s*$", re.I)
# Seen on the bench (2026-11-25, WC.16.10.0025) when another VLAN already holds an address
# in the same network: "An interface with the same IP address or subnet or an overlapping
# network <a>/24 already exists."
OVERLAP = re.compile(r"same IP address or subnet|overlapping network", re.I)
ERROR = re.compile(r"Invalid input|Incomplete input|Ambiguous input|invalid port|"
                   r"not allowed|Error:|Unable to|" + OVERLAP.pattern, re.I)

# Erasing a preconfigured switch (product owner, 2026-11-23: BH-DMZ units arrive with a site
# configuration and a non-approved manager password). Command from the vendor's CLI
# documentation; its confirmation wording is NOT yet seen on the bench, so only a y/n
# question that asks to continue/proceed is answered "y", a save question "n", anything
# else stops the procedure with the switch's text.
ERASE_COMMAND = "erase startup-config"
ERASE_CONTINUE = re.compile(r"(?:continue|proceed)[^\n]*(?:\[y/n\]|\(y/n\))\s*\??\s*$", re.I)
SAVE_QUESTION = re.compile(r"save[^\n]*(?:\[y/n[^\]]*\]|\(y/n\))\s*\??\s*$", re.I)
ANY_QUESTION = re.compile(r"(?:\?|\[y/n[^\]]*\]|\(y/n\)|:)\s*$", re.I)

_VLAN_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_PORT = re.compile(r"^[A-Za-z0-9/]{1,8}$")
# Lines that indicate the switch already carries a site configuration.
_SITE_CONFIG = ("ip authorized-managers", "ip route", "logging ", "sntp server", "aaa ",
                "radius-server", "tacacs-server", "banner ", "timesync ")


class NewSwitchError(ConsoleError):
    """A read-only look met a new switch asking to set its manager credentials."""


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


@dataclass(frozen=True)
class EraseRequest:
    """Erase a preconfigured switch before bootstrapping it."""

    current: Credentials  # the switch's current (preconfigured) manager login
    confirm_hostname: str  # typed by the technician; must equal the console prompt's name
    restart_timeout: float = 420.0  # erase, restart and console banner
    down_delay: float = 20.0  # let the switch go down before pressing Enter
    poll: float = 10.0  # press Enter this often until the console answers


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
        # True once a new switch's mandatory first-login credentials were set by UNDM.
        self.credentials_set = False
        # True once the switch asked for a password at login or at enable.
        self.password_asked = False
        # The login the switch has now (factory or preconfigured), tried when ``credentials``
        # (the approved login) is refused (D-102). ``used_fallback``: it was.
        self.fallback: Credentials | None = None
        self.used_fallback = False

    def _first_login_setup(self) -> str:
        """Answer a new switch's "Configure the manager credentials" request.

        Sends the device's attached login and answers exactly the prompts seen on a new
        unit, in order: "Password:", then "Re-enter the new password:". Any other prompt,
        another order, or the username asked again stops with the switch's text.
        """
        if self.credentials is None or not self.credentials.password:
            raise ConsoleError(
                "This switch is new and requires its manager credentials to be set first "
                "('Configure the manager credentials'). Attach the approved login (user and "
                "a non-empty password) to the device, then run the bootstrap again. Nothing "
                "was sent.")
        self.s.write_line(self.credentials.username)
        expected = [SETUP_PASSWORD, SETUP_REENTER]
        for _ in range(6):
            idx, text = self.s.read_until_any(
                [PROMPT, LOGIN, SETUP_REENTER, SETUP_PASSWORD, PASSWORD, ANY_KEY],
                timeout=self.login_timeout)
            if idx == 0:
                if expected:
                    raise ConsoleError("The switch reached its prompt before the new password "
                                       "was confirmed; check it on the console.")
                self.credentials_set = True
                return text
            if idx == 1:
                raise ConsoleError(
                    "The switch asked for the username again after the new password: it may "
                    "not accept the password (its rules are in the transcript). Use another "
                    "password in the device's credential.")
            if idx == 5:
                self.s.write_line()
                continue
            asked = SETUP_REENTER if idx == 2 else SETUP_PASSWORD if idx == 3 else None
            if asked is None or not expected or asked is not expected[0]:
                question = text.strip().splitlines()[-1][-80:] if text.strip() else "?"
                raise ConsoleError(
                    f"The switch asked a password question UNDM did not expect at this point "
                    f"('{question}'); nothing was answered.")
            expected.pop(0)
            self.s.transcript.append("<<< (new password sent)\n")
            self.s.transport.write((self.credentials.password + "\r").encode())
        raise ConsoleError("Could not finish setting the manager credentials")

    def _credential(self, what: str) -> str:
        if self.credentials is None:
            raise ConsoleError(
                f"The switch asks for a {what}: it is not in factory-default state (a "
                "password is set). Attach a credential to the device, or factory-reset it.")
        return self.credentials.username if what == "username" else self.credentials.password

    def _wake(self) -> None:
        self.s.write_line()  # the console auto-senses speed on the first key presses
        time.sleep(self.wake_delay)
        self.s.write_line()

    LOGIN_STEPS = (PROMPT, ANY_KEY, LOGIN, PASSWORD, TERMINATED)
    # Set for a look at the switch that must change nothing (console identify, D-095): a new
    # switch's "configure the manager credentials" dialogue is then not answered.
    read_only = False

    def login(self, wake: bool = True, initial: tuple[int, str] | None = None) -> str:
        """Reach the manager prompt (#) at top level. Returns the prompt's hostname.

        ``initial`` is a match of LOGIN_STEPS already read (e.g. while waiting for a restart).
        """
        if wake and initial is None:
            self._wake()
        text = ""
        seen = ""
        restarts = 0
        for _ in range(10):
            if initial is not None:
                (idx, text), initial = initial, None
            else:
                idx, text = self.s.read_until_any(list(self.LOGIN_STEPS),
                                                  timeout=self.login_timeout)
            seen += text
            if idx == 4:  # a login left half-way was ended by the wake-up key: start over
                restarts += 1
                if restarts > 2:
                    raise ConsoleError("The switch keeps ending the console session "
                                       "('Session Terminated'); check it on the console.")
                seen = ""
                self._wake()
                continue
            if idx == 0:
                break
            if idx == 1:
                self.s.write_line()
            elif idx == 2 and AUTH_FAILED.search(text) and self._switch_to_fallback():
                self.s.write_line(self._credential("username"))
            elif idx == 2 and FIRST_LOGIN.search(seen) and not self.credentials_set:
                if self.read_only:
                    raise NewSwitchError(
                        "The switch is new: it asks to configure its manager credentials")
                text = self._first_login_setup()
                break
            elif idx == 2:
                self.s.write_line(self._credential("username"))
            else:
                self.password_asked = True
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
                    self.password_asked = True
                    self.s.transcript.append("<<< (password sent)\n")
                    self.s.transport.write((self._credential("password") + "\r").encode())
            m = PROMPT.search(text)
            if (m is not None and m["mode"] != "#" and re.search(r"Unable to verify", text)
                    and self._switch_to_fallback()):
                return self.login(wake=False, initial=(0, text))  # 'enable' again with it
            if m is None or m["mode"] != "#":
                raise ConsoleError(
                    "Could not enter manager (enable) level: the switch has a manager password "
                    "that the login used does not match. If it is a preconfigured unit, run the "
                    "bootstrap with 'erase its configuration first' and its current login")
        if m["ctx"]:  # left in a configuration context by an earlier session
            self.command("end")
        self.command("no page")  # session only
        return str(m["name"])

    def _switch_to_fallback(self) -> bool:
        """The approved login was refused: use the login the switch has now, once."""
        if self.fallback is None or self.used_fallback:
            return False
        self.credentials, self.used_fallback = self.fallback, True
        self.s.transcript.append("<<< (the approved login was refused: trying the login it "
                                 "has now)\n")
        return True

    def set_manager_password(self) -> None:
        """Give a switch without a manager password the attached login's password.

        Answers exactly the two questions seen on the bench, in order; anything else stops
        with the switch's text. The password never enters the transcript (the switch
        echoes '*'). Only for the user name 'manager' (the command sets that account).
        """
        assert self.credentials is not None and self.credentials.password
        self.command("configure")
        self.s.write_line(SET_PASSWORD_COMMAND)
        expected = [NEW_MANAGER_PASSWORD, REENTER_MANAGER_PASSWORD]
        while expected:
            # "Re-enter the new password for manager:" also ends like the first question,
            # so the longer one is checked first.
            idx, text = self.s.read_until_any(
                [REENTER_MANAGER_PASSWORD, NEW_MANAGER_PASSWORD, PROMPT],
                timeout=self.login_timeout)
            asked = (REENTER_MANAGER_PASSWORD, NEW_MANAGER_PASSWORD, None)[idx]
            if asked is not expected[0]:
                self.command("end")
                last = text.strip().splitlines()[-1][-100:] if text.strip() else "?"
                raise ConsoleError(f"Setting the manager password: the switch answered '{last}' "
                                   "where UNDM expected its next password question; nothing "
                                   "was saved.")
            expected.pop(0)
            self.s.transcript.append("<<< (new password sent)\n")
            self.s.transport.write((self.credentials.password + "\r").encode())
        _, text = self.s.read_until_any([PROMPT], timeout=self.login_timeout)
        self.command("end")
        if ERROR.search(text):
            raise ConsoleError("The switch did not accept the manager password (its message is "
                               "in the transcript); nothing was saved.")

    def command(self, cmd: str, timeout: float | None = None) -> str:
        self.s.write_line(cmd)
        _, text = self.s.read_until_any([PROMPT], timeout=timeout)
        return text

    def running_config(self) -> str:
        return self.command("show running-config", timeout=30)


def erase_existing(console: ArubaOSSwitchConsole, request: EraseRequest,
                   params: BootstrapParams) -> str:
    """Log in with the switch's current login, confirm its identity, erase its startup
    configuration and wait until it has restarted. Returns the erased hostname, or "" if
    the switch was already factory default (nothing erased). Raises ConsoleError."""
    approved = console.credentials
    console.credentials = request.current
    try:
        name = console.login()
    except ConsoleError as e:
        raise ConsoleError(f"Could not log in with the switch's current login ({e}). Check the "
                           "credential chosen as its current login. Nothing was erased.") from e
    finally:
        console.credentials = approved
    # Identity check, not a secret: upper/lower case does not matter, every character does.
    if name.lower() != request.confirm_hostname.strip().lower():
        raise ConsoleError(f"The switch on this console is '{name}', not "
                           f"'{request.confirm_hostname.strip()}' as typed. Nothing was erased.")
    if not site_config_findings(console.running_config(), params):
        return ""  # already factory default: nothing to erase
    console.s.write_line(ERASE_COMMAND)
    answered_continue = False
    for _ in range(4):
        idx, text = console.s.read_until_any(
            [SAVE_QUESTION, ERASE_CONTINUE, PROMPT, ANY_QUESTION], timeout=console.login_timeout)
        if idx == 0:
            console.s.write_line("n")  # never save the configuration being erased
            continue
        if idx == 1:
            console.s.write_line("y")
            answered_continue = True
            break
        if idx == 2:
            raise ConsoleError("The switch returned to its prompt without erasing"
                               + (f" ({text.strip().splitlines()[0][:120]})" if text.strip()
                                  else "") + ". Nothing was erased.")
        question = text.strip().splitlines()[-1][-100:] if text.strip() else "?"
        raise ConsoleError(f"The switch asked something UNDM does not answer ('{question}'). "
                           "Nothing was answered; check it on the console.")
    if not answered_continue:
        raise ConsoleError("The switch did not ask to confirm the erase; nothing was answered.")
    console.credentials_set = False
    console.password_asked = False  # what counts is the login after the erase
    return name


def wait_after_erase(console: ArubaOSSwitchConsole, request: EraseRequest) -> tuple[int, str]:
    """Wait until the erased switch has restarted and its console answers.

    After a restart the console stays silent until a key is pressed (it senses the speed
    again: "Connected at 9600 baud", bench 2026-11-23), so Enter is pressed every
    ``poll`` seconds, as a technician would, until the start of a login appears.
    """
    deadline = time.monotonic() + request.restart_timeout
    time.sleep(request.down_delay)
    steps = [*console.LOGIN_STEPS, SPEED_SENSE]
    while True:
        console.s.write_line()
        left = deadline - time.monotonic()
        try:
            idx, text = console.s.read_until_any(steps, timeout=max(0.1, min(request.poll, left)))
            if idx == len(steps) - 1:  # "Press <Enter> twice": the second press follows
                console.s.write_line()
                idx, text = console.s.read_until_any(list(console.LOGIN_STEPS),
                                                     timeout=max(0.1, min(request.poll, left)))
            return idx, text
        except ConsoleTimeoutError:
            if time.monotonic() >= deadline:
                raise ConsoleError(
                    f"The switch was erased but did not answer on the console within "
                    f"{request.restart_timeout / 60:.0f} minutes. Check it on the console; once "
                    "it shows its login, run the bootstrap again without erasing.") from None


_PROMPT_LINE = re.compile(r"\S+(\([^)]*\))?[#>]")


def config_ports(running_config: str) -> set[str]:
    """Ports the switch's own configuration lists in its VLANs (untagged or tagged)."""
    ports: set[str] = set()
    for block in parse_vlans(running_config).values():
        for ln in block:
            for word in ("untagged ", "tagged "):
                if ln.startswith(word):
                    ports |= _expand_ports(ln[len(word):])
    return ports


def _port_list(ports: set[str]) -> str:
    """{'1', ..., '52'} -> '1-52' (numbered ports); other names listed as they are."""
    nums = sorted(int(p) for p in ports if p.isdigit())
    groups: list[list[int]] = []
    for n in nums:
        if groups and n == groups[-1][1] + 1:
            groups[-1][1] = n
        else:
            groups.append([n, n])
    words = [str(a) if a == b else f"{a}-{b}" for a, b in groups]
    return ", ".join(words + sorted(p for p in ports if not p.isdigit()))


def _holders(console: ArubaOSSwitchConsole, params: BootstrapParams) -> str:
    """Which interface holds an address in the wanted network: the switch's own 'show ip'
    (read-only), lines that carry such an address. The full answer is in the transcript."""
    try:
        listing = console.command("show ip")
    except ConsoleError:
        return "(UNDM could not read 'show ip'.)"
    lines = []
    for raw in listing.splitlines():
        for word in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", raw):
            try:
                inside = IPv4Address(word) in params.address.network
            except ValueError:
                continue
            if inside:
                lines.append(" ".join(raw.split()))
                break
    fix = ("To fix: unplug every network cable from the switch, switch it off and on (this "
           "discards the unsaved changes), then run the console setup again; plug port "
           f"{params.untagged_port} into the bench switch only after the setup.")
    if not lines:
        return ("The switch's 'show ip' lists no address in that network (its answer is in "
                "the transcript): send the transcript.")
    shown = "The switch's 'show ip' shows: " + "; ".join(f'"{ln}"' for ln in lines[:4]) + "."
    if any(re.search(r"DHCP", ln, re.I) for ln in lines):
        return (shown + " That address came from a DHCP server: one of the switch's ports "
                "is cabled to a network that has one. " + fix)
    return shown + " " + fix


def _rejected(cmd: str, output: str, params: BootstrapParams) -> str:
    """The message for a command the switch rejected, with the switch's own words."""
    said = " ".join(ln.strip() for ln in output.splitlines()
                    if ln.strip() and ln.strip() != cmd
                    and not _PROMPT_LINE.fullmatch(ln.strip()))[:300]
    message = f"The switch rejected '{cmd}'" + (f": \"{said}\"" if said else "") + "."
    if OVERLAP.search(output):
        return message + (f" Another interface of the switch already has an address in "
                          f"{params.address.network}. Nothing was saved.")
    return message + (" Earlier commands changed the running configuration but nothing was "
                      "saved: reboot the switch without saving to discard them.")


def bootstrap(console: ArubaOSSwitchConsole, params: BootstrapParams,
              *, allow_configured: bool = False,
              erase: EraseRequest | None = None,
              current: Credentials | None = None) -> BootstrapResult:
    """Run the bootstrap. Never raises for device-side problems; returns a result."""
    s = console.s
    sent: list[str] = []

    erased = ""
    password_set = False

    def needs_password() -> bool:
        """The switch asked for no password, and the attached login can be given to it."""
        c = console.credentials
        return (not console.credentials_set and not console.password_asked and c is not None
                and bool(c.password) and c.username == "manager")

    def give_password() -> None:
        """Set and save the manager password; confirm it from the configuration."""
        nonlocal password_set
        console.set_manager_password()
        sent.append(SET_PASSWORD_COMMAND)
        out = console.command("write memory", timeout=30)
        if ERROR.search(out):
            raise ConsoleError("The manager password was set but 'write memory' reported an "
                               "error; it will be lost on reboot.")
        if not PASSWORD_LINE.search(console.running_config()):
            raise ConsoleError("The manager password was entered, but the configuration does "
                               "not show it; check the switch on the console.")
        password_set = True

    def done(status: BootstrapStatus, message: str, **kw: object) -> BootstrapResult:
        result = _done(status, message, **kw)
        if result.message.endswith(".."):
            result.message = result.message[:-1]
        result.message = result.message.replace(".. ", ". ")
        return result

    def _done(status: BootstrapStatus, message: str, **kw: object) -> BootstrapResult:
        if erased:
            message = f"Erased the configuration of '{erased}' first. {message}"
        if console.credentials_set:
            message += (". The switch was new: its manager credentials were set to the "
                        "device's attached login")
        no_password = (status in (BootstrapStatus.BOOTSTRAPPED,
                                  BootstrapStatus.ALREADY_CONFIGURED)
                       and not console.credentials_set and not console.password_asked
                       and not password_set)
        if password_set:
            message += (". The switch had no manager password: it was set to the device's "
                        "attached login and saved")
        if console.used_fallback and status in (BootstrapStatus.BOOTSTRAPPED,
                                                BootstrapStatus.ALREADY_CONFIGURED):
            message += (". The switch kept the password of the login it had (the approved "
                        "login was refused), so that login is now its login in UNDM. Choose "
                        "the approved login as 'Login after loading' for its team file: the "
                        "file sets the approved password")
        if no_password:
            message += (". Note: the switch asked for no password, so it has no manager "
                        "password and SSH with the device's login will fail. Either set the "
                        "approved password on the console, or attach a login with an empty "
                        "password to the device and choose the approved login as 'Login after "
                        "loading' when the file is loaded")
        return BootstrapResult(status, message, commands_sent=sent,
                               transcript=s.transcript_text,
                               credentials_set=console.credentials_set, erased=erased,
                               kept_current_login=console.used_fallback,
                               no_password=no_password, password_set=password_set,
                               **kw)  # type: ignore[arg-type]

    console.fallback = current  # the login the switch has now, if the person gave it
    try:
        if erase is not None:
            console.fallback = erase.current
            erased = erase_existing(console, erase, params)
        if erased:
            assert erase is not None
            sent.append(ERASE_COMMAND)
            console.login(initial=wait_after_erase(console, erase))
        else:
            console.login()
        before = console.running_config()
        if is_configured(before, params):
            if needs_password():
                give_password()
            return done(BootstrapStatus.ALREADY_CONFIGURED,
                        f"VLAN {params.vlan_id} already has {params.address} with port "
                        f"{params.untagged_port} untagged"
                        + ("" if password_set else "; nothing was changed"), verified=True)
        ports = config_ports(before)
        if ports and params.untagged_port not in ports:
            return done(BootstrapStatus.REFUSED,
                        f"This switch has no port {params.untagged_port} (its configuration "
                        f"lists ports {_port_list(ports)}). Correct the port in 'Management "
                        "settings' and run again. Nothing was changed")
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
                message = _rejected(cmd, output, params)
                if OVERLAP.search(output):
                    message += " " + _holders(console, params)
                return done(BootstrapStatus.FAILED, message, findings=findings)
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
        if needs_password():
            try:
                give_password()
            except ConsoleError as e:
                return done(BootstrapStatus.FAILED,
                            f"VLAN {params.vlan_id} and the address are saved, but: {e}",
                            findings=findings, verified=True, saved=True)
        return done(BootstrapStatus.BOOTSTRAPPED,
                    f"VLAN {params.vlan_id} ({params.vlan_name}) with port "
                    f"{params.untagged_port} untagged and address {params.address}, saved",
                    findings=findings, verified=True, saved=True)
    except ConsoleError as e:
        return done(BootstrapStatus.FAILED, str(e))
