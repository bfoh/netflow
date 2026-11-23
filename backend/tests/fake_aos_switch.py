"""A stateful stand-in for an ArubaOS-Switch CLI, for firmware tests.

SYNTHETIC. The questions and messages below are written for these tests in the
general shape described in public write-ups; they are not captured from a
switch and do not prove that the real wording matches. What IS real here: the
fake fetches the image from UNDM's TFTP server with an independent client
(tftpy), so file publishing, the client allowlist and transfer records are
exercised end to end.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import tftpy
from fake_netmiko import AOS_SWITCH_RUNNING

IMAGE_HEADER = b"SYNTHETIC IMAGE "  # followed by the version and a newline


def fake_image(version: str, size: int = 150_000) -> bytes:
    head = IMAGE_HEADER + version.encode() + b"\n"
    return head + b"\0" * (size - len(head))


@dataclass
class FakeArubaSwitch:
    tftp_port: object  # callable returning the server port at fetch time
    running: str = "WC.16.10.0012"
    primary: str = "WC.16.10.0012"
    secondary: str = "WC.16.09.0004"
    serial: str = "SG00FAKE01"
    unsaved_changes: bool = False
    # Behaviour switches for failure tests.
    copy_question: str = "The Primary OS Image will be deleted, continue [y/n]?  "
    truncate_download: bool = False
    skip_flash_write: bool = False
    no_fetch_for: set[str] = field(default_factory=set)  # image slots it never fetches for
    reboot_mode: str = "close"  # close | silent | refuse
    down_for_connects: int = 1  # connection attempts that fail after a restart
    # Complete configuration files ('copy tftp startup-config').
    hostname: str = "lab-2930f"
    running_config: str = AOS_SWITCH_RUNNING
    startup_config: str | None = None
    config_load_mode: str = "reboot"  # reboot: asks, then restarts | prompt: back to prompt
    refuse_config: bool = False  # fetches the file, keeps its old startup configuration
    ask_save_before_load: bool = False  # asks to save first; "y" saves running over the file
    serial_after_restart: str | None = None  # another unit answering after the restart
    password: str = ""  # manager password the switch accepts (factory default: none)
    # Password a loaded file sets (the team's files carry the approved password).
    password_after_load: str | None = None
    # HTTPS certificate commands (questions as on a real unit's screen, 2026-11-19).
    certificates: set[str] = field(default_factory=set)
    subject: dict[str, str] = field(default_factory=dict)
    web_ssl: bool = False
    saves: int = 0
    reject: set[str] = field(default_factory=set)  # commands answered "Invalid input"
    _config: bool = False
    _subject_left: list[str] = field(default_factory=list)
    # Observations.
    commands: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    restarts: int = 0
    _out: str = ""
    _pending: str = ""
    _closed: bool = False
    _down: int = 0

    # -- what a new SSH session sees --------------------------------------------------
    def accept_connection(self, password: str | None = None) -> None:
        if self._down > 0:
            self._down -= 1
            raise OSError("connection timed out (switch restarting)")
        if password is not None and password != self.password:
            from netmiko.exceptions import NetmikoAuthenticationException
            raise NetmikoAuthenticationException("Authentication failed")
        self._closed, self._out, self._pending = False, "", ""

    def show(self, command: str) -> str:
        self.commands.append(command)
        if command == "show system":
            return (" Status and Counters - General System Information\n\n"
                    f"  System Name        : {self.hostname}\n\n"
                    f"  Software revision  : {self.running}        "
                    "Base MAC Addr      : 001122-334455\n"
                    f"  ROM Version        : WC.16.01.0010        Serial Number      : "
                    f"{self.serial}\n")
        if command == "show modules":
            return (" Status and Counters - Module Information\n\n"
                    f"  Chassis: 2930F-48G-4SFP JL260A          Serial Number:   {self.serial}\n")
        if command == "show flash":
            return ("Image           Size (bytes) Date     Version\n"
                    "--------------- ------------ -------- --------------\n"
                    f"Primary Image   :   30981312 01/02/24 {self.primary}\n"
                    f"Secondary Image :   29923840 01/02/23 {self.secondary}\n\n"
                    "Boot ROM Version   : WC.16.01.0010\n"
                    "Default Boot Image : Primary\n")
        if command == "show running-config":
            return self.running_config
        if command == "show config":  # the startup configuration
            return self.startup_config if self.startup_config is not None \
                else self.running_config
        return ""

    # -- raw channel ------------------------------------------------------------------
    def write(self, data: str) -> None:
        if self._closed:
            raise OSError("Socket is closed")
        text = data.strip()
        if self._pending:
            self.keys.append(text)
            handler, self._pending = self._pending, ""
            getattr(self, f"_answer_{handler}")(text)
            return
        if not text:
            self._out += self._prompt()
            return
        self.commands.append(text)
        self._out += text + "\r\n"
        if text in self.reject:
            self._out += "Invalid input: " + text + "\r\n" + self._prompt()
            return
        if text == "configure":
            self._config = True
            self._out += self._prompt()
            return
        if text == "end":
            self._config = False
            self._out += self._prompt()
            return
        if text == "write memory":
            self.saves += 1
            self.startup_config = self.running_config
            self._out += self._prompt()
            return
        if text == "web-management ssl" and self._config:
            self.web_ssl = True
            self._out += self._prompt()
            return
        m = re.match(r"crypto pki identity-profile (\S+) subject$", text)
        if m and self._config:
            self._subject_left = ["Common Name(CN)", "Org Unit(OU)", "Org Name(O)",
                                  "Locality(L)", "State(ST)", "Country(C)"]
            self.subject = {}
            self._ask("subject", f"Enter {self._subject_left[0]} : ")
            return
        m = re.match(r"crypto pki enroll-self-signed certificate-name (\S+)$", text)
        if m and self._config:
            if m.group(1) in self.certificates:
                self._out += f'Certificate "{m.group(1)}" already exists.\r\n'
            elif self.subject:
                self.certificates.add(m.group(1))
            else:
                self._out += "Identity profile not configured.\r\n"  # synthetic wording
            self._out += self._prompt()
            return
        if text.startswith("copy tftp flash "):
            self._copy_args = text.split()[3:]
            self._ask("copy", self.copy_question)
        elif text.startswith("copy tftp startup-config "):
            self._copy_args = text.split()[3:5]
            if self.ask_save_before_load:
                self._ask("loadsave", "Do you want to save current configuration [y/n/^C]? ")
            elif self.config_load_mode == "reboot":
                self._ask("config", "Device will be rebooted, do you want to continue [y/n]? ")
            else:
                self._fetch_startup(restart=False)
        elif text == "boot system flash primary":
            if self.unsaved_changes:
                self._ask("save", "Do you want to save current configuration [y/n/^C]? ")
            else:
                self._ask("boot", "This will reboot the system from the primary image. "
                                  "Continue (y/n)? ")
        else:
            self._out += "Invalid input: " + text + "\r\n" + self._prompt()

    def read(self) -> str:
        if self._closed:
            raise OSError("Socket is closed")
        out, self._out = self._out, ""
        if self._closing:
            self._closing, self._closed = False, True
        return out

    _closing: bool = False
    _copy_args: list[str] = field(default_factory=list)

    def _ask(self, handler: str, question: str) -> None:
        self._pending, self._out = handler, self._out + question

    def _answer_copy(self, key: str) -> None:
        if key != "y":
            self._out += "\r\n" + self._prompt()
            return
        server, name, bank = self._copy_args
        if bank in self.no_fetch_for:
            self._out += "\r\n" + self._prompt()
            return
        port = self.tftp_port() if callable(self.tftp_port) else self.tftp_port
        buf = io.BytesIO()
        try:
            client = tftpy.TftpClient(server, port, {})
            if self.truncate_download:
                # Ask for the file, then walk away after the first block.
                client.download(name, _StopAfter(buf, 1), timeout=2)
            else:
                client.download(name, buf, timeout=2)
        except Exception as e:  # noqa: BLE001 - shown like a switch would show a failure
            self._out += f"\r\nTFTP download failed: {type(e).__name__}\r\n" + self._prompt()
            return
        data = buf.getvalue()
        self._out += f"\r\n{len(data) // 1024:05d}K\r\n"
        if data.startswith(IMAGE_HEADER) and not self.skip_flash_write:
            version = data[len(IMAGE_HEADER):].split(b"\n", 1)[0].decode()
            if bank == "secondary":
                self.secondary = version
            else:
                self.primary = version
            self._out += "Validating and Writing System Software to the Filesystem ...\r\n"
        self._out += self._prompt()

    def _prompt(self) -> str:
        return f"{self.hostname}{'(config)' if self._config else ''}# "

    def _answer_subject(self, key: str) -> None:
        self.subject[self._subject_left.pop(0)] = key
        if self._subject_left:
            self._ask("subject", f"\r\nEnter {self._subject_left[0]} : ")
        else:
            self._out += "\r\n" + self._prompt()

    def _answer_loadsave(self, key: str) -> None:
        self._save_over_file = key == "y"
        if self.config_load_mode == "reboot":
            self._ask("config", "\r\nDevice will be rebooted, do you want to continue [y/n]? ")
        else:
            self._fetch_startup(restart=False)

    _save_over_file: bool = False

    def _answer_config(self, key: str) -> None:
        if key != "y":
            self._out += "\r\n" + self._prompt()
            return
        self._fetch_startup(restart=True)

    def _fetch_startup(self, restart: bool) -> None:
        server, name = self._copy_args
        port = self.tftp_port() if callable(self.tftp_port) else self.tftp_port
        buf = io.BytesIO()
        try:
            tftpy.TftpClient(server, port, {}).download(name, buf, timeout=2)
        except Exception as e:  # noqa: BLE001
            self._out += f"\r\nTFTP download failed: {type(e).__name__}\r\n" + self._prompt()
            return
        if self.refuse_config:
            self._out += "\r\nConfiguration file not accepted.\r\n"  # synthetic wording
        else:
            self.startup_config = buf.getvalue().decode()
        if self._save_over_file:  # the old running configuration replaces the file
            self.startup_config = self.running_config
        if restart:
            self._out += "\r\nRebooting the System...\r\n"
            self._restart_into_startup()
            self._closing = True
        else:
            self._out += "\r\nDownload complete.\r\n" + self._prompt()
            self.unsaved_changes = True  # the running configuration no longer matches

    def _restart_into_startup(self) -> None:
        self.restarts += 1
        self._down = self.down_for_connects
        if self.startup_config is not None:
            self.running_config = self.startup_config
            for line in self.startup_config.splitlines():
                if line.startswith("hostname "):
                    self.hostname = line.split(None, 1)[1].strip('"')
        if self.serial_after_restart:
            self.serial = self.serial_after_restart
        if (self.password_after_load is not None and self.startup_config
                and "password manager" in self.startup_config):
            self.password = self.password_after_load

    def _answer_save(self, key: str) -> None:
        self.saved_on_reboot = key == "y"
        if key == "y":  # saving copies the running configuration over the startup file
            self.startup_config = self.running_config
        self._ask("boot", "\r\nThis will reboot the system from the primary image. "
                          "Continue (y/n)? ")

    saved_on_reboot: bool | None = None

    def _answer_boot(self, key: str) -> None:
        if key != "y" or self.reboot_mode == "refuse":
            self._out += "\r\n" + self._prompt()
            return
        self.running = self.primary
        self._restart_into_startup()
        if self.reboot_mode == "close":
            self._out += "\r\nRebooting the System...\r\n"
            self._closing = True
        # "silent": the session simply stops answering.


class _StopAfter(io.RawIOBase):
    """A destination that fails after a number of writes (an interrupted download)."""

    def __init__(self, target: io.BytesIO, writes: int) -> None:
        self._target, self._left = target, writes

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # type: ignore[override]
        if self._left <= 0:
            raise OSError("link lost")
        self._left -= 1
        return self._target.write(data)
