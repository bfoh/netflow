"""The team's PCI table, imported once for all systems (D-114).

Kept in UNDM's database on this PC (``app_settings``), never in the code. A system's cells
get the PCIs of its row: cell 1 the "Compact Sector 1" column, cell 2 "Compact Sector 2",
and so on (product owner, 2026-11-26).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from undm.configgen import pci_table
from undm.configgen import zone as zr
from undm.services import app_settings, audit
from undm.services.errors import ConflictError, ServiceError

KEY = "pci_mapping"


def import_table(session: Session, actor: str, filename: str, data: bytes) -> dict[str, Any]:
    try:
        rows = pci_table.parse(data, filename)
    except pci_table.PciTableError as e:
        raise ServiceError(str(e)) from e
    value = {"filename": filename.strip()[:200], "sha256": hashlib.sha256(data).hexdigest(),
             "imported_at": datetime.now(UTC).isoformat(), "imported_by": actor, "rows": rows}
    app_settings.put(session, KEY, value)
    audit.record(session, actor, "settings.pci_mapping", "settings", KEY, details={
        "filename": value["filename"], "sha256": value["sha256"], "systems": len(rows)})
    return summary(session) or {}


def summary(session: Session) -> dict[str, Any] | None:
    value = app_settings.get(session, KEY)
    if not value:
        return None
    rows = value.get("rows") or {}
    return {"filename": value.get("filename", ""), "sha256": value.get("sha256", ""),
            "imported_at": value.get("imported_at"), "imported_by": value.get("imported_by", ""),
            "systems": len(rows), "cells": max((len(v) for v in rows.values()), default=0)}


def row(session: Session, system: zr.SystemRef) -> list[int | None] | None:
    value = app_settings.get(session, KEY) or {}
    found = (value.get("rows") or {}).get(system.table_key)
    return list(found) if isinstance(found, list) else None


def pcis_for(session: Session, system: zr.SystemRef, cells: int) -> tuple[int, ...]:
    """The PCIs of the system's first ``cells`` cells, from the team's table."""
    if app_settings.get(session, KEY) is None:
        raise ConflictError("No PCI table yet: import the team's PCI table in Settings → For "
                            "all systems")
    found = row(session, system)
    if found is None:
        raise ConflictError(f"System {system.tag} is not in the PCI table "
                            f"(no row {system.table_key})")
    values = found[:cells]
    if len(values) < cells or any(v is None for v in values):
        raise ConflictError(f"The PCI table has no PCI for every cell of {system.tag} "
                            f"({cells} cells needed)")
    return tuple(int(v) for v in values if v is not None)
