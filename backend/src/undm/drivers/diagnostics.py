"""Reading the answers of ping and traceroute run on a device (D-128). Vendor-neutral and
deliberately tolerant: what is read is only what the text shows unambiguously; anything
else is left as None and the raw output is always kept for the person. The outputs of the
real devices have not been seen yet (Q-59): the tests replay SYNTHETIC text."""

from __future__ import annotations

import re
from typing import Any

_SUMMARY = re.compile(r"(\d+)\s+packets?\s+transmitted,\s+(\d+)\s+(?:packets?\s+)?received",
                      re.IGNORECASE)
_RTT = re.compile(r"time\s*[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)
_IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_HOP = re.compile(r"^\s*(\d{1,2})\s+(\S.*)$")
_PROBE = re.compile(r"([\d.]+)\s*ms|(?<!\S)\*(?!\S)")


def ping_answer(text: str, target: str, sent: int | None) -> dict[str, Any]:
    """Echo replies from a ping's output: its statistics line when it prints one (``N
    packets transmitted, M received``), else replies counted from lines from the target that
    show a time; None when neither is there."""
    summary = _SUMMARY.search(text)
    rtts = [float(m.group(1)) for line in text.splitlines()
            if target in _IPV4.findall(line) for m in [_RTT.search(line)] if m]
    if summary:
        return {"sent": int(summary.group(1)), "received": int(summary.group(2)),
                "rtt_ms": rtts, "raw": text}
    return {"sent": sent, "received": len(rtts) if rtts else None, "rtt_ms": rtts, "raw": text}


def trace_hops(text: str) -> list[dict[str, Any]]:
    """Hop lines: a hop number, then an address and probe times ("<n> ms" or "*")."""
    hops = []
    for line in text.splitlines():
        m = _HOP.match(line)
        if not m:
            continue
        rest = m.group(2)
        found = _IPV4.findall(rest)
        probes = [float(p.group(1)) if p.group(1) else None for p in _PROBE.finditer(rest)]
        if not found and not probes:
            continue
        hops.append({"n": int(m.group(1)), "address": found[0] if found else None,
                     "rtt_ms": probes})
    return hops
