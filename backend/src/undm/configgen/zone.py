"""Zone templates (D-111): a team's configuration file for one zone, turned into a template
that gives the same file for any other zone.

The rules come from two zones' files supplied by the product owner (2026-11-26): applied to
one zone's files they give the other zone's files exactly. They are the team's numbering
convention, not vendor facts:

1. the zone tag ``z`` + three digits (``z041``) in names, banners and comments;
2. ``10.<127 + zone>.x.x``;
3. ``10.<zone>.x.x``;
4. ``10.0.<zone>.x``;
5. ``130.<zone>.x.x``.

Everything else is copied unchanged. A template also keeps the file's formatting (line
endings, final line break) so a download is the team's file byte for byte (``as_file``).
Pure functions: no database, no web framework.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ZONE_MIN, ZONE_MAX = 1, 128  # 127 + zone must stay a valid octet

# Markers in a stored template. "${" does not occur in the team's files; a file that has it
# is refused rather than guessed.
TAG, PLUS127, ZONE = "${zone_tag}", "${zone_127}", "${zone}"
MARKER = re.compile(r"\$\{zone(_tag|_127)?\}")

RULES = (
    ("zone_tag", "zone tag (z + 3 digits)"),
    ("ten_plus127", "10.(127+zone).x.x"),
    ("ten_zone", "10.zone.x.x"),
    ("ten_zero_zone", "10.0.zone.x"),
    ("onethirty_zone", "130.zone.x.x"),
)

_IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
_TAG = re.compile(r"\bz(\d{3})(?!\d)")


class ZoneError(ValueError):
    """A zone outside 1-128, or a file that cannot be made into a template."""


def check_zone(zone: int) -> int:
    if not isinstance(zone, int) or not ZONE_MIN <= zone <= ZONE_MAX:
        raise ZoneError(f"The zone must be a number from {ZONE_MIN} to {ZONE_MAX}")
    return zone


def zone_tag(zone: int) -> str:
    return f"z{check_zone(zone):03d}"


def zone_from_text(text: str) -> int | None:
    """A zone named in a file or system name (``z041-…``, ``B001z045``), if exactly one."""
    found = {int(m.group(1)) for m in re.finditer(r"(?i)z(\d{3})(?!\d)", text)}
    found = {z for z in found if ZONE_MIN <= z <= ZONE_MAX}
    return found.pop() if len(found) == 1 else None


@dataclass
class Templated:
    text: str
    counts: dict[str, int] = field(default_factory=lambda: {k: 0 for k, _ in RULES})
    # Lines that still hold the zone's numbers in another form: for a person to check.
    to_check: list[tuple[int, str]] = field(default_factory=list)


def templatize(text: str, zone: int) -> Templated:
    """Replace the reference zone's values by markers, following the five rules."""
    check_zone(zone)
    if "${" in text:
        raise ZoneError("The file contains '${', which UNDM uses for its own markers")
    out = Templated(text="")
    lines: list[str] = []
    for n, line in enumerate(text.split("\n"), 1):
        def tag_sub(m: re.Match[str]) -> str:
            if int(m.group(1)) != zone:
                return m.group(0)
            out.counts["zone_tag"] += 1
            return TAG

        line = _TAG.sub(tag_sub, line)

        def ip_sub(m: re.Match[str]) -> str:
            a, b, c, d = m.group(1), m.group(2), m.group(3), m.group(4)
            if a == "10" and int(b) == 127 + zone:
                out.counts["ten_plus127"] += 1
                return f"10.{PLUS127}.{c}.{d}"
            if a == "10" and int(b) == zone:
                out.counts["ten_zone"] += 1
                return f"10.{ZONE}.{c}.{d}"
            if a == "10" and b == "0" and int(c) == zone:
                out.counts["ten_zero_zone"] += 1
                return f"10.0.{ZONE}.{d}"
            if a == "130" and int(b) == zone:
                out.counts["onethirty_zone"] += 1
                return f"130.{ZONE}.{c}.{d}"
            return m.group(0)

        line = _IPV4.sub(ip_sub, line)
        # The zone's numbers left in another form (e.g. "92" or "219" on their own).
        rest = MARKER.sub("", line)
        if re.search(rf"(?<![\d.]){zone}(?![\d.])|(?<![\d.]){127 + zone}(?![\d.])", rest):
            out.to_check.append((n, line.strip()[:160]))
        lines.append(line)
    out.text = "\n".join(lines)
    return out


def render(template: str, zone: int) -> str:
    """The file for ``zone``."""
    check_zone(zone)
    values = {TAG: f"z{zone:03d}", PLUS127: str(127 + zone), ZONE: str(zone)}
    return MARKER.sub(lambda m: values[m.group(0)], template)


def markers(template: str) -> int:
    return len(MARKER.findall(template))


LINE_ENDINGS = ("lf", "crlf")


@dataclass(frozen=True)
class FileFormat:
    """How a team file is written: its line endings and whether its last line ends."""

    line_ending: str = "lf"  # "lf" | "crlf"
    final_newline: bool = True


def file_format(raw: str) -> FileFormat:
    """The formatting of a file as supplied (before UNDM normalises it to LF): the line
    ending most of its lines use, and whether it ends with a line break."""
    crlf = raw.count("\r\n")
    lf = raw.count("\n") - crlf
    return FileFormat(line_ending="crlf" if crlf > lf else "lf",
                      final_newline=raw.endswith(("\n", "\r")))


def as_file(text: str, fmt: FileFormat) -> bytes:
    """A normalised text (LF, ending with one line break) written in a file's formatting,
    byte for byte. Only the line ending of each line changes; nothing else is touched."""
    if fmt.line_ending not in LINE_ENDINGS:
        raise ZoneError(f"Unknown line ending '{fmt.line_ending}'")
    if not fmt.final_newline and text.endswith("\n"):
        text = text[:-1]
    if fmt.line_ending == "crlf":
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


@dataclass
class Comparison:
    same: bool
    lines: int
    differences: list[tuple[int, str, str]]  # (line, rendered, supplied), first few


def compare(rendered: str, supplied: str, limit: int = 10) -> Comparison:
    """Line by line, ignoring only line-ending style and a final newline."""
    a = rendered.replace("\r\n", "\n").rstrip("\n").split("\n")
    b = supplied.replace("\r\n", "\n").rstrip("\n").split("\n")
    diffs = [(i + 1, x, y) for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y]
    if len(a) != len(b):
        diffs.append((min(len(a), len(b)) + 1, f"{len(a)} lines", f"{len(b)} lines"))
    return Comparison(same=not diffs, lines=len(b), differences=diffs[:limit])
