"""Mask identifying details in device output so it can be shared (e.g. as test fixtures).

Masking is pattern-based and therefore best effort: users must still review the text
before sharing it. Each distinct value gets a stable placeholder (``<ip-1>``,
``<mac-2>``, ``<serial-1>``) so the structure of the output stays readable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from undm.security.redaction import redact_text

_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\w.])")
_MAC = re.compile(
    r"(?<![\w:.-])(?:"
    r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"  # 00:11:22:33:44:55 / 00-11-22-33-44-55
    r"|[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}"  # 001122-334455 (HP / ArubaOS-Switch)
    r"|(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}"  # 0011.2233.4455 (Cisco)
    r")(?![\w:.-])"
)
# An SNMP engine ID: on the 7705 SAR-Hmc its tail is a MAC address of the unit (bench
# 2026-11-26, "SNMP Engine ID : 0000197f0000…").
_ENGINE_ID = re.compile(r"(Engine ID[ \t]*:[ \t]*)([0-9A-Fa-f]{10,64})(?![0-9A-Fa-f])", re.I)
# A flash volume or board UUID (seen in a modem's start-up text, 2026-11-26).
_UUID = re.compile(r"(?<![\w-])[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}(?![\w-])")
# Separators use [ \t] only: a label with an empty value must never swallow the next line.
_SERIAL_LABEL = re.compile(
    r"((?:Chassis )?Serial[- ]?(?:Number|Nbr|No\.?)|Processor board ID)([ \t]*:?[ \t]*)"
    r"(\S*[A-Za-z0-9]\S*)",  # a value has a letter or digit: never just a bracket
    re.I)
_NAME_LABEL = re.compile(
    r"((?:System )?(?:Name|Contact|Location)|Hostname)([ \t]*:[ \t]*)(\S[^\n]*?)"
    r"(?=[ \t]{2,}|\n|$)", re.I)


class _Mapper:
    def __init__(self) -> None:
        self.maps: dict[str, dict[str, str]] = {}

    def __call__(self, kind: str, value: str) -> str:
        m = self.maps.setdefault(kind, {})
        if value not in m:
            m[value] = f"<{kind}-{len(m) + 1}>"
        return m[value]


def _valid_ip(text: str) -> bool:
    return all(int(p) <= 255 for p in text.split("/")[0].split("."))


def sanitize(text: str, known_values: Iterable[tuple[str, str]] = (),
             mapper: _Mapper | None = None) -> str:
    """Mask IPs, MACs, serials, names/contacts/locations and secrets.

    ``known_values`` are (kind, value) pairs to mask wherever they appear, e.g.
    ("hostname", "lab-sw1") or ("serial", "CN00TEST01").
    """
    m = mapper or _Mapper()
    out = redact_text(text)
    for kind, value in sorted(known_values, key=lambda kv: -len(kv[1])):
        if value and len(value) >= 3:
            out = out.replace(value, m(kind, value))
    # Values already replaced by a placeholder (from known_values) are kept, so one value
    # always maps to one placeholder.
    out = _SERIAL_LABEL.sub(
        lambda x: x.group(1) + x.group(2)
        + (x.group(3) if x.group(3).startswith("<") else m("serial", x.group(3))), out)
    out = _NAME_LABEL.sub(
        lambda x: x.group(1) + x.group(2)
        + (x.group(3) if x.group(3).startswith("<") else m("name", x.group(3))), out)
    out = _ENGINE_ID.sub(lambda x: x.group(1) + m("engine", x.group(2).lower()), out)
    out = _UUID.sub(lambda x: m("uuid", x.group(0).lower()), out)
    out = _MAC.sub(lambda x: m("mac", x.group(0).lower()), out)
    out = _IPV4.sub(lambda x: m("ip", x.group(0)) if _valid_ip(x.group(0)) else x.group(0), out)
    return out


def new_mapper() -> _Mapper:
    return _Mapper()
