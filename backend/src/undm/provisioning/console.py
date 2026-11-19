"""Serial console sessions with prompt detection.

Transport-agnostic: anything with ``read``/``write``/``close`` works, so the same
session logic drives a real COM port (pyserial) and the simulated console used in
tests and demos.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol

# CSI sequences (cursor moves, colours) and two-character escapes sent by switch consoles.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")


class Transport(Protocol):
    def read(self, size: int = 1) -> bytes: ...
    def write(self, data: bytes) -> int | None: ...
    def close(self) -> None: ...


class ConsoleError(Exception):
    """The console did not behave as expected."""


class ConsoleTimeoutError(ConsoleError):
    pass


# Codes that move to a new line become real line breaks, as Netmiko does for this switch
# family ("Aruba and ProCurve switches can use code_insert_line for <enter>").
_INSERT_LINES = re.compile(r"\x1b\[(\d*)L")
_NEXT_LINE = re.compile(r"\x1bE")
# A complete escape sequence starting at a given position (to spot one cut off by a read).
_COMPLETE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-Z\\-_])")


def clean(text: str) -> str:
    text = _INSERT_LINES.sub(lambda m: "\n" * int(m.group(1) or 1), text)
    text = _NEXT_LINE.sub("\n", text)
    return _ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "").replace("\x00", "")


@dataclass
class ConsoleSession:
    transport: Transport
    read_timeout: float = 8.0
    settle_time: float = 0.15  # wait this long after a match for trailing output
    transcript: list[str] = field(default_factory=list)
    _buffer: str = ""
    _carry: str = ""  # the start of an escape sequence cut off by the previous read

    def write_line(self, text: str = "") -> None:
        # "<<<" marks what UNDM typed; keep it visually apart from the device's output.
        gap = "" if not self.transcript or self.transcript[-1].endswith((" ", "\n")) else " "
        self.transcript.append(f"{gap}<<< {text or '(Enter)'}\n")
        self.transport.write((text + "\r").encode("ascii", "replace"))

    def _fill(self) -> bool:
        chunk = self.transport.read(256)
        if chunk:
            data = self._carry + chunk.decode("utf-8", "replace")
            self._carry = ""
            # A serial read can end in the middle of an escape sequence (seen on the bench:
            # "ESC" in one read, "[24;18H" in the next). Keep that start for the next read so
            # the whole sequence is removed; never hold back more than a short tail.
            esc = data.rfind("\x1b")
            if esc != -1 and len(data) - esc < 16 and not _COMPLETE.match(data, esc):
                data, self._carry = data[:esc], data[esc:]
            self._buffer += clean(data)
        return bool(chunk)

    def read_until_any(
        self, patterns: list[re.Pattern[str]], timeout: float | None = None
    ) -> tuple[int, str]:
        """Read until one pattern matches the end of the output; return (index, text)."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.read_timeout)
        while True:
            for idx, pattern in enumerate(patterns):
                if pattern.search(self._buffer):
                    # A prompt-like fragment can appear mid-output; make sure output stopped.
                    settle = time.monotonic() + self.settle_time
                    grew = False
                    while time.monotonic() < settle:
                        if self._fill():
                            grew = True
                            break
                    if grew:
                        break  # re-evaluate all patterns on the longer buffer
                    text, self._buffer = self._buffer, ""
                    self.transcript.append(text)
                    return idx, text
            else:
                if time.monotonic() > deadline:
                    text, self._buffer = self._buffer, ""
                    self.transcript.append(text)
                    raise ConsoleTimeoutError(
                        "No expected prompt from the console within "
                        f"{timeout or self.read_timeout:.0f}s. Last output: {text[-200:]!r}")
                self._fill()

    def close(self) -> None:
        self.transport.close()

    @property
    def transcript_text(self) -> str:
        return "".join(self.transcript)


def open_serial(port: str, baudrate: int = 9600, read_chunk_timeout: float = 0.2) -> Transport:
    """Open a COM port: 8 data bits, no parity, 1 stop bit, no hardware flow control."""
    import serial  # pyserial; imported lazily so the simulation needs no serial port

    try:
        return serial.Serial(
            port=port, baudrate=baudrate, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE, timeout=read_chunk_timeout, write_timeout=5,
        )
    except serial.SerialException as e:
        raise ConsoleError(
            f"Cannot open {port}: {e}. Close any terminal program (PuTTY, Tera Term) using "
            "this port and check the console cable.") from e


def list_serial_ports() -> list[dict[str, str]]:
    from serial.tools import list_ports

    return [{"port": p.device, "description": p.description or "", "hardware_id": p.hwid or ""}
            for p in sorted(list_ports.comports(), key=lambda p: p.device)]
