"""Serial console sessions with prompt detection.

Transport-agnostic: anything with ``read``/``write``/``close`` works, so the same
session logic drives a real COM port (pyserial) and the simulated console used in
tests and demos.
"""

from __future__ import annotations

import re
import time
from collections import Counter
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


# Control characters that are not text: carriage returns on their own, backspaces, bells,
# NULs, a stray escape, DEL. A console can print them around a question (to redraw a
# countdown, for example); kept, they would hide the question from a pattern (bench
# 2026-11-26, D-112). Line feeds and tabs are text.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def control_name(ch: str) -> str:
    """A control character in words for diagnostics: \\r, \\b, \\x00 ..."""
    return {"\r": "\\r", "\b": "\\b", "\t": "\\t", "\n": "\\n", "\x1b": "\\e"}.get(
        ch, f"\\x{ord(ch):02x}")


def clean(text: str, dropped: Counter[str] | None = None) -> str:
    """Console output as text: escape sequences removed, CR LF made LF, and every other
    control character dropped (counted in ``dropped`` when given)."""
    text = _INSERT_LINES.sub(lambda m: "\n" * int(m.group(1) or 1), text)
    text = _NEXT_LINE.sub("\n", text)
    text = _ANSI.sub("", text).replace("\r\n", "\n")
    if dropped is not None:
        dropped.update(control_name(c) for c in _CONTROL.findall(text))
    return _CONTROL.sub("", text)


def visible(raw: str) -> str:
    """Raw console characters with every control character written out (``\\r``, ``\\b``,
    ``\\x00``), line feeds kept as line breaks: shows exactly what the device sent."""
    return "".join(c if c == "\n" or (c != "\t" and not _CONTROL.match(c))
                   else control_name(c) for c in raw)


@dataclass
class ConsoleSession:
    transport: Transport
    read_timeout: float = 8.0
    settle_time: float = 0.15  # wait this long after a match for trailing output
    transcript: list[str] = field(default_factory=list)
    # Values that must never reach the transcript or a message: a password typed on a
    # command line is echoed by the device, so both directions are masked.
    secrets: list[str] = field(default_factory=list)
    received: int = 0  # bytes read from the device
    # Control characters dropped from the text, by kind (diagnostics).
    ignored: Counter[str] = field(default_factory=Counter)
    raw_keep: int = 1200  # how many raw characters to keep for diagnostics
    _buffer: str = ""
    _carry: str = ""  # the start of an escape sequence cut off by the previous read
    _raw: str = ""  # the last raw characters received, before cleaning
    _last_line: str = ""  # the last visible line, for progress reports

    def mask(self, text: str) -> str:
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "********")
        return text

    def _typed(self, shown: str) -> None:
        # "<<<" marks what UNDM typed; keep it visually apart from the device's output.
        gap = "" if not self.transcript or self.transcript[-1].endswith((" ", "\n")) else " "
        self.transcript.append(f"{gap}<<< {shown}\n")

    def write_line(self, text: str = "") -> None:
        self._typed(self.mask(text) or "(Enter)")
        self.transport.write((text + "\r").encode("ascii", "replace"))

    def write_key(self, key: str = " ", shown: str = "(a key)") -> None:
        """One key without Enter after it (e.g. to interrupt a boot loader's countdown)."""
        self._typed(shown)
        self.transport.write(key.encode("ascii", "replace"))

    def type_slowly(self, text: str, gap: float = 0.15) -> None:
        """Type one character at a time, ``gap`` seconds apart, as a person does, without
        Enter. For line editors that redraw their whole line on every key (the 7705 SAR's
        boot menu, bench 2026-11-26). Output arriving meanwhile is read, not lost."""
        self._typed(self.mask(text))
        for i, ch in enumerate(text):
            if i and gap:
                end = time.monotonic() + gap
                while time.monotonic() < end:
                    self._fill()
            self.transport.write(ch.encode("ascii", "replace"))

    def write_secret(self, secret: str) -> None:
        """A password at a prompt that does not echo it: never in the transcript."""
        self._typed("(password: not shown)")
        self.transport.write((secret + "\r").encode("utf-8"))

    def _fill(self) -> bool:
        """Read once; True when visible text arrived (control characters alone do not
        count, so a device that keeps sending them never looks busy)."""
        chunk = self.transport.read(256)
        if not chunk:
            return False
        self.received += len(chunk)
        data = self._carry + chunk.decode("utf-8", "replace")
        self._raw = (self._raw + data[len(self._carry):])[-self.raw_keep:]
        self._carry = ""
        # A serial read can end in the middle of an escape sequence (seen on the bench:
        # "ESC" in one read, "[24;18H" in the next). Keep that start for the next read so
        # the whole sequence is removed; never hold back more than a short tail.
        esc = data.rfind("\x1b")
        if esc != -1 and len(data) - esc < 16 and not _COMPLETE.match(data, esc):
            data, self._carry = data[:esc], data[esc:]
        text = clean(data, self.ignored)
        self._buffer += text
        lines = [ln for ln in self._buffer[-400:].split("\n") if ln.strip()]
        if lines:
            self._last_line = lines[-1].strip()[-160:]
        return bool(text)

    def raw_tail(self, size: int = 400) -> str:
        """The last characters the device sent, control characters written out, masked."""
        return visible(self.mask(self._raw)[-size:])

    @property
    def last_line(self) -> str:
        return self.mask(self._last_line)

    def _take(self, end: int) -> str:
        text, self._buffer = self.mask(self._buffer[:end]), self._buffer[end:]
        self.transcript.append(text)
        return text

    def wait_for(
        self, patterns: list[re.Pattern[str]], timeout: float | None = None
    ) -> tuple[int, str]:
        """Read until one pattern is found anywhere in the unread output and return
        (index, text up to the end of the match) at once: no waiting for the output to
        pause. For questions with a time limit, whose full sentence does not appear in
        passing; output after the match stays unread. The earliest match wins."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.read_timeout)
        while True:
            found = [(m.start(), m.end(), idx) for idx, p in enumerate(patterns)
                     if (m := p.search(self._buffer))]
            if found:
                _, end, idx = min(found)
                return idx, self._take(end)
            if time.monotonic() > deadline:
                text = self._take(len(self._buffer))
                raise ConsoleTimeoutError(
                    "No expected question from the console within "
                    f"{timeout or self.read_timeout:.0f}s. Last output: {text[-200:]!r}")
            self._fill()

    def read_until_any(
        self, patterns: list[re.Pattern[str]], timeout: float | None = None
    ) -> tuple[int, str]:
        """Read until one pattern matches the end of the output; return (index, text)."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.read_timeout)
        while True:
            for idx, pattern in enumerate(patterns):
                if pattern.search(self._buffer):
                    # A prompt-like fragment can appear mid-output; make sure output stopped.
                    # Never past the deadline: a device that keeps sending would otherwise
                    # keep a matched prompt waiting for ever.
                    settle = min(time.monotonic() + self.settle_time, deadline)
                    grew = False
                    while time.monotonic() < settle:
                        if self._fill():
                            grew = True
                            break
                    if grew:
                        break  # re-evaluate all patterns on the longer buffer
                    text, self._buffer = self.mask(self._buffer), ""
                    self.transcript.append(text)
                    return idx, text
            else:
                if time.monotonic() > deadline:
                    text, self._buffer = self.mask(self._buffer), ""
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
