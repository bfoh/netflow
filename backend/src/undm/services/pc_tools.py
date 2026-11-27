"""Ping and traceroute from this PC: Windows' own programs (D-128).

UNDM runs on the bench PC, a Windows laptop. The commands and their options are Microsoft's
(Windows Commands reference, "ping" and "tracert", learn.microsoft.com):
- ``ping -n <count> -w <timeout ms> <address>``: count echo requests, timeout per reply;
- ``tracert -d -h <maximum hops> -w <timeout ms> <address>``: -d does not resolve names.
They are started from System32 by their full path, as a list of arguments (no shell),
without a window, with a time limit. Elsewhere (Linux test machines) they are refused, as
the SSH and console windows are (D-098, D-118).

Reading the answers: ping's exit code is 0 even when a router answers "Destination host
unreachable", so a reply is counted only from a line with "TTL=" (the same in every
language Windows is sold in that the team uses; Q-64). Hops are read from the tokens that
do not depend on the language: the hop number, "<1 ms" / "12 ms" / "*", and the address.
The raw output is always kept.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

from undm.domain.troubleshoot import Hop
from undm.services.errors import ConflictError

PING_TIMEOUT_MS = 1000
TRACE_MAX_HOPS = 20
NOT_HERE = "Ping and traceroute from this PC are available when UNDM runs on Windows (the " \
           "bench PC)."


def _program(name: str) -> str:
    return os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", name)


def ping_command(target: str, count: int) -> list[str]:
    return [_program("PING.EXE"), "-n", str(count), "-w", str(PING_TIMEOUT_MS), target]


def tracert_command(target: str) -> list[str]:
    return [_program("TRACERT.EXE"), "-d", "-h", str(TRACE_MAX_HOPS), "-w",
            str(PING_TIMEOUT_MS), target]


def _decode(data: bytes) -> str:
    """Console programs print in the OEM code page on Windows."""
    try:
        return data.decode("oem", "replace")
    except LookupError:  # not on Windows
        return data.decode("utf-8", "replace")


def _run(argv: list[str], timeout: float) -> str:
    """Start the program and return what it printed (Windows only)."""
    if os.name != "nt":
        raise ConflictError(NOT_HERE)
    try:
        done = subprocess.run(  # noqa: S603 - fixed programs, checked arguments, no shell
            argv, capture_output=True, timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as e:
        partial = e.stdout if isinstance(e.stdout, bytes) else b""
        return _decode(partial) + f"\n(UNDM stopped waiting after {timeout:.0f} s)"
    return _decode(done.stdout or b"")


# Replaced in tests; tests also forbid the real one (conftest).
runner: Callable[[list[str], float], str] = _run

_TTL = re.compile(r"TTL=\d+", re.IGNORECASE)
_RTT = re.compile(r"[=<]\s*(\d+)\s*ms", re.IGNORECASE)
_IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_HOP = re.compile(r"^\s*(\d{1,2})\s+((?:(?:<?\d+\s*ms|\*)\s+){3})(.*)$")
_PROBE = re.compile(r"<?(\d+)\s*ms|\*")


def parse_ping(text: str, target: str) -> tuple[int, tuple[float, ...]]:
    """(replies, round-trip times) from ping's output: a reply is a line from the target
    with "TTL="."""
    replies: list[float] = []
    for line in text.splitlines():
        if _TTL.search(line) and target in _IPV4.findall(line):
            m = _RTT.search(line)
            replies.append(float(m.group(1)) if m else 0.0)
    return len(replies), tuple(replies)


def parse_tracert(text: str) -> list[Hop]:
    hops: list[Hop] = []
    for line in text.splitlines():
        m = _HOP.match(line)
        if not m:
            continue
        rtts: list[float | None] = []
        for p in _PROBE.finditer(m.group(2)):
            rtts.append(float(p.group(1)) if p.group(1) else None)
        found = _IPV4.findall(m.group(3))
        address = found[0] if found else None
        hops.append(Hop(n=int(m.group(1)), address=address, rtt_ms=tuple(rtts),
                        timed_out=address is None or all(r is None for r in rtts)))
    return hops


def ping(target: str, count: int = 4) -> tuple[int, tuple[float, ...], str]:
    out = runner(ping_command(target, count), count * (PING_TIMEOUT_MS / 1000 + 1) + 5)
    received, rtts = parse_ping(out, target)
    return received, rtts, out


def traceroute(target: str) -> tuple[list[Hop], str]:
    out = runner(tracert_command(target), TRACE_MAX_HOPS * 3 * PING_TIMEOUT_MS / 1000 + 15)
    return parse_tracert(out), out
