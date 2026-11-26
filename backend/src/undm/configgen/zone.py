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

Files that also depend on the system (the modem's configuration and the Flexi BBU's site
configuration file, D-114) are made into templates with more rules, again the team's
convention as shown by two systems' files in two zones (2026-11-26; their files differ
in nothing else):

6. the zone as ``Z`` or ``Zone`` + three digits (``Z041``, ``Zone041``);
7. the zone in the SCF's ``tac`` parameter, without leading zeros;
8. the system number in ``MRBTS-<n>``, and as its letter + three digits, alone or after a
   site-type prefix and with or without a dash (``-B007-``, ``…B-007``, ``…B007``);
9. each cell's ``phyCellId`` (``LNCEL-<k>``), from the team's PCI table, not from the file;
10. the modem's ``password "…"`` line: a secret slot, filled from the modem's login when a
    file is handed out, never kept in the template.

Pure functions: no database, no web framework.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ZONE_MIN, ZONE_MAX = 1, 128  # 127 + zone must stay a valid octet

# Markers in a stored template. A team file that already holds one of these exact markers is
# refused rather than guessed; any other "${…}" is the file's own text and is kept as it is
# (FortiOS report layouts use ${hostname}, ${vdom} and the like).
TAG, PLUS127, ZONE = "${zone_tag}", "${zone_127}", "${zone}"
ZONE3, SYS, SYS3, SECRET, STAMP = "${zone3}", "${sys}", "${sys3}", "${admin_password}", "${stamp}"
MARKER = re.compile(r"\$\{(?:zone_tag|zone_127|zone3|zone|sys3|sys|pci_\d+|admin_password|stamp)\}")
SYSTEM_LETTERS = "B"  # B systems (two cells) only, for now (product owner, 2026-11-26)

RULES = (
    ("zone_tag", "zone tag (z + 3 digits)"),
    ("ten_plus127", "10.(127+zone).x.x"),
    ("ten_zone", "10.zone.x.x"),
    ("ten_zero_zone", "10.0.zone.x"),
    ("onethirty_zone", "130.zone.x.x"),
)
SYSTEM_RULES = (
    ("zone3", "Z / Zone + zone (3 digits)"),
    ("tac", "tac = zone"),
    ("system", "system number"),
    ("pci", "phyCellId of each cell"),
    ("secret", "admin password (from the login)"),
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


def _one_zone(pattern: str, text: str) -> int | None:
    found = {int(m.group(1)) for m in re.finditer(pattern, text)}
    found = {z for z in found if ZONE_MIN <= z <= ZONE_MAX}
    return found.pop() if len(found) == 1 else None


def zone_from_text(text: str) -> int | None:
    """A zone named in a file's text or a system name (``z041-…``, ``B001z045``,
    ``Zone041``), if exactly one. Three digits: in a file a shorter ``z1`` could be anything."""
    return _one_zone(r"(?i)z(?:one)?(\d{3})(?!\d)", text)


def zone_from_name(name: str) -> int | None:
    """A zone in a file's name, if exactly one: also without leading zeros, as the team names
    the modem's file (``…z41.txt``, ``…Z041_…``)."""
    return _one_zone(r"(?i)z(?:one)?(\d{1,3})(?!\d)", name)


def own_markers(text: str) -> list[str]:
    """UNDM's own markers already in a team file (it cannot be made into a template)."""
    return sorted(set(MARKER.findall(text)))


def check_no_markers(text: str) -> None:
    found = own_markers(text)
    if found:
        raise ZoneError(f"The file contains {', '.join(found)}, which UNDM uses as its own "
                        "marker: it cannot be kept as a template")


@dataclass(frozen=True)
class SystemRef:
    """A system's number with its letter, e.g. B007: letter B, number 7."""

    letter: str
    number: int

    @property
    def tag(self) -> str:
        return f"{self.letter}{self.number:03d}"  # B007

    @property
    def table_key(self) -> str:
        return f"{self.letter}{self.number}"  # B7, as the PCI table writes it


def parse_system(text: str) -> SystemRef:
    """'B007', 'B7' or 'b7' -> B007. Only the letters UNDM supports so far."""
    m = re.fullmatch(r"\s*([A-Za-z])-?0*(\d{1,3})\s*", text or "")
    if not m or not 1 <= int(m.group(2)) <= 999:
        raise ZoneError("The system is a letter and a number, e.g. B007")
    letter = m.group(1).upper()
    if letter not in SYSTEM_LETTERS:
        raise ZoneError(f"Only {', '.join(SYSTEM_LETTERS)} systems are supported so far")
    return SystemRef(letter, int(m.group(2)))


def system_from_text(text: str, *, name: bool = False) -> SystemRef | None:
    """A system named in a system or file name, or in a file: B007 (alone or after a site
    type, with or without a dash) or MRBTS-7; None unless exactly one. In a name (``name``)
    either case is accepted (``b007z041``)."""
    flags = re.IGNORECASE if name else 0
    found: set[int] = set()
    for letter in SYSTEM_LETTERS:
        found |= {int(m.group(1)) for m in re.finditer(
            rf"(?<!\d){letter}-?(\d{{3}})(?![0-9A-Fa-f])", text, flags)}
    found |= {int(m.group(1)) for m in re.finditer(r"MRBTS-(\d{1,3})(?!\d)", text, flags)}
    found = {n for n in found if 1 <= n <= 999}
    return SystemRef(SYSTEM_LETTERS[0], found.pop()) if len(found) == 1 else None


@dataclass
class Templated:
    text: str
    counts: dict[str, int] = field(default_factory=lambda: {k: 0 for k, _ in RULES})
    cells: int = 0  # cells found (phyCellId), for files that have them
    # Lines that still hold the zone's numbers in another form: for a person to check.
    to_check: list[tuple[int, str]] = field(default_factory=list)


_LNCEL = re.compile(r'(<managedObject\b[^>]*\bdistName="[^"]*/LNCEL-(\d+)"[^>]*>)(.*?)'
                    r"(</managedObject>)", re.S)
_PCI = re.compile(r'(<p name="phyCellId">)\d+(</p>)')
_PASSWORD = re.compile(r'(?m)^([ \t]*password[ \t]+)"[^"\r\n]*"')


def mask_secrets(text: str) -> tuple[str, int]:
    """The ``password "…"`` lines with the secret slot instead of the value."""
    return _PASSWORD.subn(lambda m: f'{m.group(1)}"{SECRET}"', text)


def _system_rules(text: str, zone: int, system: SystemRef, out: Templated,
                  cells: bool, secrets: bool) -> str:
    def count(kind: str, n: int = 1) -> None:
        out.counts[kind] = out.counts.get(kind, 0) + n

    def zone3(m: re.Match[str]) -> str:
        if int(m.group(2)) != zone:
            return m.group(0)
        count("zone3")
        return m.group(1) + ZONE3

    text = re.sub(r"(?<![A-Za-z0-9])(Z|Zone)(\d{3})(?!\d)", zone3, text)
    text, n = re.subn(rf'(<p name="tac">){zone}(</p>)', rf"\g<1>{ZONE}\g<2>", text)
    count("tac", n)
    text, n = re.subn(rf"MRBTS-{system.number}(?!\d)", f"MRBTS-{SYS}", text)
    count("system", n)
    # Not inside a number, and not followed by a hex digit (certificate and serial values).
    text, n = re.subn(rf"(?<!\d){system.letter}(-?){system.number:03d}(?![0-9A-Fa-f])",
                      rf"{system.letter}\g<1>{SYS3}", text)
    count("system", n)
    if cells:
        def cell(m: re.Match[str]) -> str:
            body, k = _PCI.subn(rf"\g<1>${{pci_{m.group(2)}}}\g<2>", m.group(3))
            if k:
                out.cells = max(out.cells, int(m.group(2)))
                count("pci", k)
            return m.group(1) + body + m.group(4)

        text = _LNCEL.sub(cell, text)
    if secrets:
        text, n = mask_secrets(text)
        count("secret", n)
    return text


def templatize(text: str, zone: int, system: SystemRef | None = None, *,
               cells: bool = False, secrets: bool = False) -> Templated:
    """Replace the reference zone's values by markers, following the five rules; with a
    system, also the system's rules (6 to 10, D-114)."""
    check_zone(zone)
    check_no_markers(text)
    out = Templated(text="")
    if system is not None:
        out.counts.update({k: 0 for k, _ in SYSTEM_RULES})
        text = _system_rules(text, zone, system, out, cells, secrets)
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
        other = (rf"|(?<![\d.]){system.number}(?![\d.])|{system.number:03d}"
                 if system is not None else "")
        if re.search(rf"(?<![\d.]){zone}(?![\d.])|(?<![\d.]){127 + zone}(?![\d.]){other}",
                     rest):
            out.to_check.append((n, line.strip()[:160]))
        lines.append(line)
    out.text = "\n".join(lines)
    return out


def render(template: str, zone: int, system: SystemRef | None = None,
           pcis: tuple[int, ...] = (), secret: str | None = None, stamp: str | None = None,
           keep_secret: bool = False) -> str:
    """The file for ``zone`` (and ``system``, its cells' PCIs, the modem's password and a
    time stamp, where the template has those markers). ``keep_secret`` leaves the password
    slot in place (files stored for a later load)."""
    check_zone(zone)
    values = {TAG: f"z{zone:03d}", PLUS127: str(127 + zone), ZONE: str(zone),
              ZONE3: f"{zone:03d}"}
    if system is not None:
        values |= {SYS: str(system.number), SYS3: f"{system.number:03d}"}
    values |= {f"${{pci_{k}}}": str(v) for k, v in enumerate(pcis, 1)}
    if secret is not None:
        values[SECRET] = secret
    if stamp is not None:
        values[STAMP] = stamp

    def fill(m: re.Match[str]) -> str:
        marker = m.group(0)
        if marker in values:
            return values[marker]
        if marker == SECRET and keep_secret:
            return marker
        raise ZoneError(_MISSING.get(marker.split("_")[0] if marker.startswith("${pci")
                                     else marker, f"This template needs {marker}"))
    return MARKER.sub(fill, template)


_MISSING = {
    SYS: "This template needs the system (e.g. B007): set it in Stage a system, step 1",
    SYS3: "This template needs the system (e.g. B007): set it in Stage a system, step 1",
    "${pci": "This template needs the cells' PCIs: import the PCI table in Settings → For "
             "all systems, with this system in it",
    SECRET: "This file sets the modem's admin password: choose the modem's login first",
    STAMP: "This template's file name needs a time stamp",
}


def needs(template: str) -> set[str]:
    """What a template needs besides the zone: 'system', 'pci', 'secret'."""
    found = set(MARKER.findall(template))
    out = set()
    if SYS in found or SYS3 in found:
        out.add("system")
    if any(m.startswith("${pci_") for m in found):
        out.add("pci")
    if SECRET in found:
        out.add("secret")
    return out


def cells_of(template: str) -> int:
    return max((int(k) for k in re.findall(r"\$\{pci_(\d+)\}", template)), default=0)


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
