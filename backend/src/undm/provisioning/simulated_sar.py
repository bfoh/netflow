"""Simulated Nokia 7705 SAR-Hmc console.

SYNTHETIC: written to exercise the first-access procedure and to demonstrate the workflow
without hardware. The texts of the normal path follow the product owner's console
recording (2026-11-26, identifiers replaced by made-up ones). Everything outside that
recording is an approximation and marked so: the password rule, the refusal wording at the
login, and what the unit does with unexpected answers.

The start follows the first bench run (2026-11-26): a long start-up text (here a short
SYNTHETIC stand-in), then the 3-second question printed again each second as it counts
down. How the real unit separates the countdown sentences is not known exactly (the
transcript is cleaned); ``question_tail`` and ``trickle`` reproduce the two forms that kept
UNDM v84 from answering.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

IMAGE = "cf3:/TiMOS-SR-20.5.R1"
BANNER = ("Total Memory: 1536MB  Chassis Type: 0x25\r\n"
          "TiMOS-{kind}-20.5.R1 {what}/sar Nokia 7705 SAR Copyright (c) 2000-2020 Nokia.\r\n"
          "All rights reserved. All use subject to applicable license agreements.\r\n"
          "SIMULATED CONSOLE (UNDM) - not a real device\r\n")
SECTIONS = ("System Configuration", "System Security Configuration", "Log Configuration",
            "Card Configuration", "Port Configuration", "Management Router Configuration",
            "Router (Network Side) Configuration", "Service Configuration",
            "Router (Service Side) Configuration")
RULE = "=" * 79
# A SYNTHETIC stand-in for the long start before the boot loader (U-Boot, Linux, the boot
# ROM): on the bench it took about 2.5 minutes and several thousand lines.
PREAMBLE = ("U-Boot (SIMULATED)\r\nAutoboot in 3 seconds\r\n"
            "[    0.000000] Booting Linux (SIMULATED)\r\n"
            "Starting OpenBSD Secure Shell server: sshd\r\ndone.\r\n"
            "Loading image /cf3/TiMOS-SR-20.5.R1/both.tim\r\n"
            "Looking for boot parameters.\r\n\r\nauto-booting...\r\n")


@dataclass
class SimulatedSarConsole:
    system_name: str = "NS00SIM0001"  # a factory unit is named after its serial number
    system_type: str = "7705 SAR-Hmc"
    factory: bool = True  # boot options with auto-discovery; its file has an unknown password
    key_ignored: bool = False  # the key comes too late: it starts normally
    extra_question: str = ""  # an unknown boot-menu question (SYNTHETIC)
    fail_on: set[str] = field(default_factory=set)  # commands answered with a MINOR line
    silent: bool = False  # never switched on
    min_password_length: int = 8  # SYNTHETIC rule; the real one is the unit's own
    no_paging_command: bool = True  # False: 'environment no more' is refused (SYNTHETIC)
    key_window: float = 1.0  # seconds it waits for a key (3 on the real unit)
    # Written after each countdown sentence, e.g. "\b\b\b" (cursor moved back). SYNTHETIC.
    question_tail: str = "   "
    # Sends a NUL on every read while it waits for the key (a busy line). SYNTHETIC.
    trickle: bool = False

    def __post_init__(self) -> None:
        self._out = bytearray()
        self._in = ""
        self._state = "off"
        self._asked_at = 0.0
        self._left = 3  # seconds left in the countdown, as last printed
        # The saved boot options file and configuration file.
        self.bof: dict[str, list[str]] = {
            "primary-image": [IMAGE], "primary-config": ["cf3:/config.cfg"], "wait": ["3"],
            "persist": ["off"], "console-speed": ["115200"]}
        if self.factory:
            self.bof["auto-discover"] = ["private.nokia.nsp.primary.nms",
                                         "private.nokia.nsp.secondary.nms"]
        self.file_password = "factory-unique-unknown" if self.factory else "admin"  # noqa: S105
        self.memory: dict[str, list[str]] = {}
        self.running_password = ""
        self.unsaved = False
        self.paging = True
        self.commands_received: list[str] = []
        self.bof_writes = 0
        self.keys: list[str] = []  # keys pressed at the 3-second question
        self.closed = False

    # -- transport -----------------------------------------------------------------
    def read(self, size: int = 1) -> bytes:
        if not self._out and self._state == "hit_key":
            elapsed = time.monotonic() - self._asked_at
            if elapsed >= self.key_window:
                # Nobody pressed a key in time: it starts with its saved boot options.
                self._boot(dict(self.bof))
            else:
                left = 3 - int(elapsed * 3 / self.key_window)
                if left < self._left:  # the countdown, as on the bench
                    self._left = left
                    self._emit("\r" + self._question(left))
                elif self.trickle:
                    self._emit("\x00")
        data = bytes(self._out[:size])
        del self._out[:size]
        return data

    def write(self, data: bytes) -> int:
        if self.silent or self._state == "off":
            return len(data)
        text = data.decode("ascii", "replace")
        if self._state in ("hit_key", "pager") and text:
            was, key, text = self._state, text[0], text[1:]
            if was == "hit_key":
                self.keys.append(key)
                self._key()
            else:
                self._emit("\r\n" + self._rest + "\r\n" + self._prompt())
                self._state = "cli"
        self._in += text
        while "\r" in self._in:
            line, self._in = self._in.split("\r", 1)
            self._handle(line.strip())
        return len(data)

    def close(self) -> None:
        self.closed = True

    def power_cycle(self) -> None:
        """Switched off and on: the boot loader lists its boot options and asks for a key."""
        self._out.clear()
        self._in, self._asked_at, self._left = "", time.monotonic(), 3
        if self.silent:
            return
        self._emit(PREAMBLE + "\r\n" + BANNER.format(kind="L", what="boot")
                   + "\r\nTiMOS BOOT LOADER\r\nLooking for cf3:/bof.cfg ... OK, reading\r\n\r\n"
                   "Contents of Boot Options File on cf3:\r\n" + self._bof_lines(self.bof)
                   + "\r\n" + self._question(3))
        self._state = "hit_key"

    def _question(self, left: int) -> str:
        unit = "second" if left == 1 else "seconds"
        return f"Hit a key within {left} {unit} to change boot parameters...{self.question_tail}"

    # -- behaviour -----------------------------------------------------------------
    def _emit(self, text: str) -> None:
        self._out += text.encode()

    @staticmethod
    def _bof_lines(bof: dict[str, list[str]]) -> str:
        return "".join(f"    {k:<16} {v}\r\n" for k, values in bof.items() for v in values)

    def _prompt(self) -> str:
        return f"{'*' if self.unsaved else ''}A:{self.system_name}# "

    def _key(self) -> None:
        if self.key_ignored:
            self._boot(dict(self.bof))
            return
        self._emit('\r\nType "sros" and hit ENTER within 25 seconds to begin changing '
                   "parameters: ")
        self._state = "type_sros"

    def _boot(self, bof: dict[str, list[str]]) -> None:
        """Start the image with these boot options (the session's, saved or not)."""
        self.memory = bof
        with_file = bool(bof.get("primary-config"))
        self.running_password = self.file_password if with_file else "admin"
        self.unsaved = not with_file
        self.paging = True
        self._emit(f"\r\nPrimary image location: {IMAGE}\r\nLoading image cf3:\\TiMOS-SR-20.5.R1"
                   "\\both.tim\r\n" + BANNER.format(kind="B", what="both")
                   + "\r\nRunning 32 bit architecture\r\n\r\nLogin: ")
        self._state = "login"

    def _handle(self, line: str) -> None:  # noqa: C901, PLR0912, PLR0915 - a console's states
        st = self._state
        if st == "type_sros":
            if line != "sros":
                self._boot(dict(self.bof))
                return
            self._session = {k: list(v) for k, v in self.bof.items()}
            self._emit('\r\n\r\nYou must supply some required Boot Options. At any prompt, you '
                       'can type:\r\n   "restart" - restart the query mode.\r\n   "reboot"  - '
                       'reboot.\r\n   "exit"    - boot with existing values.\r\n\r\n'
                       "Press ENTER to begin, or 'flash' to enter firmware update...")
            self._state = "press_enter"
        elif st == "press_enter":
            self._emit("\r\n\r\nSoftware Location\r\n-----------------\r\n   You must enter "
                       f"the location of the TiMOS software.\r\n\r\nThe existing Image URL is "
                       f"'{IMAGE}'\r\nPress ENTER to keep it.\r\nSoftware Image URL: ")
            self._state = "image_url"
        elif st == "image_url":
            if line:
                self._session["primary-image"] = [line]
            self._emit(f"\r\nUsing: '{self._session['primary-image'][0]}'\r\n\r\n\r\n"
                       "Configuration File Location\r\n---------------------------\r\n"
                       "   You must enter the location of the configuration\r\n   file to be "
                       "used by TiMOS.\r\n\r\nThe existing Config URL is 'cf3:/config.cfg'\r\n"
                       "Press ENTER to keep it, or the word 'none' for no Config URL.\r\n"
                       "Config File URL: ")
            self._state = "config_url"
        elif st == "config_url":
            if line == "none":
                self._session.pop("primary-config", None)
            elif line:
                self._session["primary-config"] = [line]
            self._emit(f"{line}\r\nThe existing fips-140-2 configuration is : 'no fips-140-2'"
                       "\r\nIf you would like to change it please enter 'fips-140-2' followed "
                       "by ENTER\r\nor press ENTER to keep existing fips configuration\r\n")
            self._state = "fips"
        elif st == "fips":
            if "auto-discover" in self._session:
                self._emit("\r\n\r\nAuto-Discovery\r\n--------------\r\n   This system is "
                           "equipped with TiMOS\r\n   Auto-Discovery.\r\n\r\n   [Auto-Discovery "
                           "is currently enabled]\r\nWould you like to keep auto-discovery "
                           "enabled? (yes/no) ")
                self._state = "auto_discovery"
            else:
                self._ask_overwrite()
        elif st == "auto_discovery":
            if line == "no":
                self._session.pop("auto-discover", None)
            if self.extra_question:
                self._emit(f"{line}\r\n\r\n{self.extra_question} ")
                self._state = "extra"
            else:
                self._emit(f"{line}\r\n")
                self._ask_overwrite()
        elif st == "extra":
            self._ask_overwrite()
        elif st == "overwrite":
            if line == "yes":
                self.bof = {k: list(v) for k, v in self._session.items()}
                self.bof_writes += 1
                self._emit("yes\r\nSuccessfully saved the new settings in cf3:/bof.cfg\r\n")
            else:
                self._emit(f"{line}\r\n")
            self._boot(self._session)
        elif st == "login":
            self._user = line
            self._emit(f"{line}\r\nPassword: ")
            self._state = "password"
        elif st == "password":
            if self._user == "admin" and line == self.running_password:
                self._emit("\r\n\r\n" + self._prompt())
                self._state = "cli"
            else:
                self._emit("\r\nLogin incorrect\r\n\r\nLogin: ")  # SYNTHETIC wording
                self._state = "login"
        elif st == "cli":
            self.commands_received.append(line)
            self._emit(line + "\r\n")  # the console echoes what is typed
            answer = self._run(line)
            if self._state == "cli":
                self._emit(answer + ("\r\n" if answer else "") + self._prompt())

    def _ask_overwrite(self) -> None:
        self._emit("\r\n\r\nNew Settings\r\n------------\r\n" + self._bof_lines(self._session)
                   + "\r\n\r\nDo you want to overwrite cf3:/bof.cfg with the new settings? "
                     "(yes/no): ")
        self._state = "overwrite"

    def _run(self, cmd: str) -> str:  # noqa: C901, PLR0911, PLR0912 - one branch per command
        if not cmd:
            return ""
        if cmd in self.fail_on or cmd.split(" password ")[0] in self.fail_on:
            return "MINOR: CLI Simulated refusal of this command."  # SYNTHETIC
        if cmd == "environment no more":
            if not self.no_paging_command:
                return "Error: Bad command."
            self.paging = False
            return ""
        if cmd.startswith("admin save"):
            target = cmd[len("admin save"):].strip()
            if not target and not self.memory.get("primary-config"):
                return "MINOR: CLI No primary configuration file is set."  # SYNTHETIC
            self.file_password = self.running_password
            if target:
                return ""  # the recording shows no answer when a file name is given
            self.unsaved = False
            return ("Writing configuration to cf3:\\config.cfg\r\nSaving configuration ... OK"
                    "\r\nCompleted.")
        if cmd == "exec cf3:/config.cfg":
            return ("\r\n".join(SECTIONS) + "\r\nExecuted 141 lines in 0.2 seconds from file "
                    "cf3:\\config.cfg")
        if cmd.startswith('configure system security user "admin" password '):
            new = cmd.split(" password ", 1)[1]
            if len(new) < self.min_password_length or new == "admin":
                return ("MINOR: SYSTEM #1372 The user password does not meet the system "
                        "requirement - is too simple")
            self.running_password, self.unsaved = new, True
            return ""
        if cmd.startswith("bof primary-config "):
            self.memory["primary-config"] = [cmd.split(" ", 2)[2]]
            return ""
        if cmd in ("bof persist on", "bof persist off"):
            self.memory["persist"] = [cmd.rsplit(" ", 1)[1]]
            return ""
        if cmd == "bof save":
            self.bof = {k: list(v) for k, v in self.memory.items()}
            self.bof_writes += 1
            return "Writing BOF to cf3:/bof.cfg ... OK\r\nCompleted."
        if cmd == "show bof":
            return (f"{RULE}\r\nBOF (Memory)\r\n{RULE}\r\n" + self._bof_lines(self.memory)
                    + RULE)
        if cmd == "show system information":
            rows = [("System Name", self.system_name), ("System Type", self.system_type),
                    ("Chassis Topology", "Standalone"), ("System Version", "B-20.5.R1"),
                    ("System Contact", ""), ("System Location", ""),
                    ("Configuration Mode Oper", "classic"), ("BOF Source", "cf3:"),
                    ("Image Source", "primary"),
                    ("Last Saved Config", "cf3:\\config.cfg"),
                    ("Changes Since Last Save", "Yes" if self.unsaved else "No"),
                    ("User Last Modified", "admin"), ("Management IP Addr", "0.0.0.0/0")]
            lines = ["", RULE, "System Information", RULE,
                     *[f"{k:<23}: {v}" for k, v in rows], RULE]
            if self.paging:
                self._rest = "\r\n".join(lines[8:])
                self._emit("\r\n".join(lines[:8]) + "\r\nPress any key to continue (Q to quit)")
                self._state = "pager"
                return ""
            return "\r\n".join(lines)
        if cmd == "logout":
            self._state = "login"
            self._emit("\r\nLogin: ")
            return ""
        return "Error: Bad command."
