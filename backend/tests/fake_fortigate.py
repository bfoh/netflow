"""A stateful stand-in for a FortiGate CLI, for the FortiOS procedures.

SYNTHETIC. The prompts, questions, status lines and messages are written for these
tests in the general shape described in Fortinet's public documentation; they are
not captured from a FortiGate and do not prove that the real wording matches.
What IS real: the fake fetches files from UNDM's TFTP server with an independent
client (tftpy), so publishing, the per-device allowlist and transfer records are
exercised end to end. Taken from the bench (101F v7.2.6, 2026-11-24): after the image
question the unit prints "Please wait...", "Connect to tftp server <address> ..." and
then lines of '#' progress marks while it fetches (``progress_marks``).
"""

from __future__ import annotations

import io
import re
import threading
import time
from dataclasses import dataclass, field

import tftpy

IMAGE_HEADER = b"SYNTHETIC FORTIOS IMAGE "  # + version + newline
FAIL = "Command fail. Return code -61"  # synthetic error reply


def fake_image(version: str, size: int = 120_000) -> bytes:
    head = IMAGE_HEADER + version.encode() + b"\n"
    return head + b"\0" * (size - len(head))


@dataclass
class FakeFortiGate:
    tftp_port: object  # callable returning the TFTP server port when fetching
    hostname: str = "FortiGate-101F"
    model: str = "FortiGate-101F"
    version: str = "v7.2.7"
    build: str = "1577"
    serial: str = "FG101FTK00000001"
    vdoms: bool = False
    password: str = ""  # admin password the unit accepts
    # Behaviour switches for tests.
    image_rejected: bool = False
    restart_mode: str = "close"  # close | silent
    restore_sets_password: str | None = None
    bad_statements: set[str] = field(default_factory=set)
    info_replies: dict[str, str] = field(default_factory=dict)
    question_on: dict[str, str] = field(default_factory=dict)  # statement -> question text
    revisions_supported: bool = True
    down_for_connects: int = 1
    progress_marks: bool = False  # fetch in the background, printing '#' marks (bench)
    fetch_delay: float = 0.0      # seconds per received block, to slow the fetch down
    # Observations.
    commands: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    # Running configuration as statements (a factory unit is not empty).
    applied: list[str] = field(default_factory=lambda: [
        "config system global", 'set hostname "FortiGate-101F"', "end",
        "config system interface", 'edit "mgmt"', "set ip 192.168.1.99 255.255.255.0",
        "next", "end"])
    revisions: list[str] = field(default_factory=list)
    restarts: int = 0
    fetched: list[str] = field(default_factory=list)
    blocks_received: int = 0
    fetch_failed: bool = False
    fetch_done: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _out: str = ""
    _pending: str = ""
    _closing: bool = False
    _closed: bool = False
    _down: int = 0
    _stack: list[str] = field(default_factory=list)
    _host_pending: str | None = None
    _args: list[str] = field(default_factory=list)

    # -- SSH session ------------------------------------------------------------------
    def accept_connection(self, password: str | None = None) -> None:
        if self._down > 0:
            self._down -= 1
            raise OSError("connection timed out (unit restarting)")
        if password is not None and password != self.password:
            from netmiko.exceptions import NetmikoAuthenticationException
            raise NetmikoAuthenticationException("Authentication failed")
        self._closed, self._closing, self._out, self._pending = False, False, "", ""
        self._stack = []

    def prompt_text(self) -> str:
        ctx = f" ({self._stack[-1]})" if self._stack else ""
        return f"{self.hostname}{ctx} # "

    # -- commands run with Netmiko send_command ------------------------------------------
    def show(self, command: str) -> str:
        self.commands.append(command)
        if command == "get system status":
            return (f"Version: {self.model} {self.version},build{self.build},240131 (GA.M)\n"
                    f"Serial-Number: {self.serial}\n"
                    f"Hostname: {self.hostname}\n"
                    "Virtual domain configuration: "
                    f"{'multiple' if self.vdoms else 'disable'}\n")
        if command == "show":
            return "".join(ln + "\n" for ln in self._displayed())
        if command == "execute revision list config":
            return "ID  TIME  ADMIN  FIRMWARE VERSION  SIZE  COMMENT\n" + "".join(
                f"{i}  2026-11-19  admin  {self.version}  1  {c}\n"
                for i, c in enumerate(self.revisions, 1))
        return ""

    def _displayed(self) -> list[str]:
        shown = []
        for ln in self.applied:
            if re.match(r"set (psksecret|password)\b", ln):
                shown.append(ln.split()[0] + " " + ln.split()[1] + " ENC XXXXXXXX")
            else:
                shown.append(ln)
        return shown

    # -- raw channel (statements and questions) ---------------------------------------
    def write(self, data: str) -> None:
        if self._closed:
            raise OSError("Socket is closed")
        text = data.strip()
        if self._pending:
            self.keys.append(text)
            handler, self._pending = self._pending, ""
            getattr(self, f"_answer_{handler}")(text)
            return
        self._out += data.rstrip("\n") + "\r\n"  # echo
        self.commands.append(text)
        if text in self.question_on:
            self._pending = "unknown"
            self._out += self.question_on[text]
            return
        m = re.match(r"execute restore (image|config) tftp (\S+) (\S+)$", text)
        if m:
            self._args = [m.group(2), m.group(3)]
            if m.group(1) == "image":
                self._ask("image", "This operation will replace the current firmware version!"
                                   "\r\nDo you want to continue? (y/n)")
            else:
                self._ask("config", "This operation will overwrite the current setting and "
                                    "could possibly reboot the system!\r\nDo you want to "
                                    "continue? (y/n)")
            return
        m = re.match(r'execute backup config flash "([^"]*)"$', text)
        if m:
            if self.revisions_supported:
                self.revisions.append(m.group(1))
                self._reply("")
            else:
                self._reply(FAIL)
            return
        self._statement(text)

    def read(self) -> str:
        if self._closed:
            raise OSError("Socket is closed")
        with self._lock:
            out, self._out = self._out, ""
        if self._closing and not out:
            self._closed = True
            raise OSError("Socket is closed")
        return out

    def _reply(self, message: str) -> None:
        self._out += (message + "\r\n" if message else "") + self.prompt_text()

    def _ask(self, handler: str, question: str) -> None:
        self._pending, self._out = handler, self._out + question

    def _statement(self, text: str) -> None:
        if text in self.bad_statements:
            self._reply(FAIL)
            return
        verb, _, rest = text.partition(" ")
        if verb == "end":
            if not self._stack:
                self._reply(FAIL)  # a bare 'end' at the top
                return
            closing = self._stack.pop()
            while self._stack and self._stack[-1].startswith("edit:"):
                closing = self._stack.pop()
            if closing == "global" and self._host_pending:  # 'config system global'
                self.hostname, self._host_pending = self._host_pending, None
            self.applied.append(text)
            self._reply("")
            return
        if verb == "config":
            label = rest.split()[-1]
            if rest == "global" and not self.vdoms:
                self._reply(FAIL)
                return
            self._stack.append(label)
        elif verb == "edit":
            self._stack.append("edit:" + rest.strip('"'))
        elif verb == "next":
            if self._stack and self._stack[-1].startswith("edit:"):
                self._stack.pop()
        elif verb == "set" and self._stack and self._stack[-1] == "global":
            m = re.match(r'hostname\s+"?([^"]+?)"?$', rest)
            if m:
                self._host_pending = m.group(1)
        self.applied.append(text)
        self._reply(self.info_replies.get(text, ""))

    def prompt_context(self) -> str:
        return self._stack[-1] if self._stack else ""

    # -- files fetched from UNDM ------------------------------------------------------
    def _fetch(self, name: str, server: str) -> bytes:
        port = self.tftp_port() if callable(self.tftp_port) else self.tftp_port
        buf = io.BytesIO()

        def block(_packet: object) -> None:
            self.blocks_received += 1
            if self.progress_marks and self.blocks_received % 20 == 0:
                with self._lock:
                    self._out += "#"
            if self.fetch_delay:
                time.sleep(self.fetch_delay)

        tftpy.TftpClient(server, port, {}).download(name, buf, packethook=block, timeout=2)
        self.fetched.append(name)
        return buf.getvalue()

    def _restart(self) -> None:
        self.restarts += 1
        self._down = self.down_for_connects
        if self.restart_mode == "close":
            self._out += "\r\nPlease wait for system to restart.\r\n"
            self._closing = True

    def _answer_image(self, key: str) -> None:
        if key != "y":
            self._reply("")
            return
        if self.progress_marks:
            self._out += (f"\r\nPlease wait...\r\n\r\nConnect to tftp server {self._args[1]} "
                          "...\r\n")
            threading.Thread(target=self._image_fetch, daemon=True).start()
            return
        self._image_fetch()

    def _image_fetch(self) -> None:
        try:
            try:
                data = self._fetch(*self._args)
            except Exception:  # noqa: BLE001
                self.fetch_failed = True
                with self._lock:
                    self._reply("\r\nGet image from tftp server failed.")
                return
            with self._lock:
                if self.image_rejected or not data.startswith(IMAGE_HEADER):
                    self._reply("Image check failed.")
                    return
                self.version = "v" + data[len(IMAGE_HEADER):].split(b"\n", 1)[0].decode()
                self._out += "\r\nGet image from tftp server OK.\r\nCheck image OK.\r\n"
                self._restart()
        finally:
            self.fetch_done.set()

    def _answer_config(self, key: str) -> None:
        if key != "y":
            self._reply("")
            return
        data = self._fetch(*self._args).decode()
        if not data.startswith("#config-version="):
            self._reply("Invalid config file.")
            return
        self.vdoms = ":vdom=1" in data.splitlines()[0]
        m = re.search(r'set hostname "([^"]+)"', data)
        if m:
            self.hostname = m.group(1)
        self.applied = [ln.strip() for ln in data.splitlines()
                        if ln.strip() and not ln.startswith("#")]
        if self.restore_sets_password is not None:
            self.password = self.restore_sets_password
        self._out += "Get config file from tftp server OK.\r\nFile check OK.\r\n"
        self._restart()

    def _answer_unknown(self, key: str) -> None:
        self._reply("")
