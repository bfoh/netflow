"""The team's PCI table: which physical cell IDs each system's cells get (D-114).

Read from the team's workbook (``.xlsx``) or the same table saved as CSV: a header row with
"System ID" and "Compact Sector 1", "Compact Sector 2", … columns, then one row per system
(``B7``). The product owner chose the Compact Sector columns (2026-11-26). Cells marked
"N/A" have no PCI. Pure functions: no database, no web framework.

The workbook is read with the standard library only (an .xlsx file is a zip of XML parts,
ECMA-376), so no new dependency reaches the technician's PC.
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET  # noqa: N817 - the usual short name
import zipfile

MAX_BYTES = 2 * 1024 * 1024
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_COLUMN = re.compile(r"(?i)^\s*compact\s+sector\s+(\d+)\s*$")
_SYSTEM = re.compile(r"(?i)^\s*system\s*id\s*$")


class PciTableError(ValueError):
    pass


def _cell_ref(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    if not letters:
        raise PciTableError("The workbook has a cell without a reference")
    n = 0
    for ch in letters.group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xml(data: bytes) -> ET.Element:
    # The technician's own workbook. Expat (2.4.1+) refuses entity expansion attacks and
    # ElementTree never fetches external resources; DOCTYPEs are refused outright.
    if b"<!DOCTYPE" in data[:2048].upper():
        raise PciTableError("The workbook contains a DOCTYPE, which UNDM does not read")
    return ET.fromstring(data)  # noqa: S314 - see above


def _xlsx_rows(data: bytes) -> list[list[str]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise PciTableError("This is not an .xlsx workbook") from e
    total = sum(i.file_size for i in z.infolist())
    if total > 20 * MAX_BYTES:
        raise PciTableError("The workbook is too large once unpacked")
    names = set(z.namelist())
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        root = _xml(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(_NS + "t"))
                  for si in root.iter(_NS + "si")]
    # The first sheet, as the workbook lists it.
    sheet = "xl/worksheets/sheet1.xml"
    if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
        wb = _xml(z.read("xl/workbook.xml"))
        first = next(wb.iter(_NS + "sheet"), None)
        rels = _xml(z.read("xl/_rels/workbook.xml.rels"))
        if first is not None:
            rid = first.get(_REL + "id")
            for rel in rels:
                if rel.get("Id") == rid and rel.get("Target"):
                    target = rel.get("Target", "").lstrip("/")
                    sheet = target if target.startswith("xl/") else "xl/" + target
    if sheet not in names:
        raise PciTableError("The workbook has no worksheet UNDM can read")
    rows: list[list[str]] = []
    for row in _xml(z.read(sheet)).iter(_NS + "row"):
        values: dict[int, str] = {}
        for c in row.iter(_NS + "c"):
            kind, v = c.get("t"), c.find(_NS + "v")
            if kind == "s" and v is not None and v.text is not None:
                text = shared[int(v.text)]
            elif kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(_NS + "t"))
            else:
                text = v.text if v is not None and v.text is not None else ""
            values[_cell_ref(c.get("r", "A1"))] = text
        if values:
            rows.append([values.get(i, "") for i in range(max(values) + 1)])
    return rows


def _csv_rows(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig", "replace")
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(
            text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel  # one column, or not a table at all: the header check says so
    return [row for row in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in row)]


def _number(text: str) -> int | None:
    text = text.strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        value = float(text)
    except ValueError as e:
        raise PciTableError(f"'{text}' is not a PCI") from e
    if value != int(value) or not 0 <= value <= 503:  # LTE has 504 PCIs (3GPP TS 36.211)
        raise PciTableError(f"{text} is not a valid PCI (0-503)")
    return int(value)


def parse(data: bytes, filename: str = "") -> dict[str, list[int | None]]:
    """System ID -> the PCI of cell 1, 2, … (Compact Sector columns)."""
    if len(data) > MAX_BYTES:
        raise PciTableError("The file is larger than 2 MiB")
    rows = _xlsx_rows(data) if data[:2] == b"PK" else _csv_rows(data)
    start, system_col, sectors = -1, None, {}
    for i, header in enumerate(rows):
        system_col = next((j for j, h in enumerate(header) if _SYSTEM.match(h)), None)
        sectors = {int(m.group(1)): j for j, h in enumerate(header) if (m := _COLUMN.match(h))}
        if system_col is not None and sectors:
            start = i
            break
    if start < 0 or system_col is None:
        raise PciTableError("No header row with 'System ID' and 'Compact Sector 1' columns "
                            f"in {filename or 'the file'}")
    order = [sectors[k] for k in sorted(sectors)]
    out: dict[str, list[int | None]] = {}
    for row in rows[start + 1:]:
        if system_col >= len(row) or not row[system_col].strip():
            continue
        key = re.sub(r"\s+", "", row[system_col]).upper()
        if not re.fullmatch(r"[A-Z]\d{1,3}", key):
            raise PciTableError(f"'{row[system_col]}' is not a system ID like B7")
        key = key[0] + str(int(key[1:]))
        if key in out:
            raise PciTableError(f"{key} is listed twice")
        out[key] = [_number(row[j]) if j < len(row) else None for j in order]
    if not out:
        raise PciTableError("The table lists no systems")
    return out
