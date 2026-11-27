"""Guided staging (D-117): a person stages the device in its own portal; UNDM checks,
read-only, that the portal answers, hands out the exact files and records each step.

Nothing here changes a device: the person does, in the device's portal. That is why the
steps are records, not plans (the lifecycle rule is about what UNDM sends to devices).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.configgen import zone as zr
from undm.db.models import ConfigVersion, Device, FirmwareImage, GuidedStepRecord
from undm.domain.guided import PROCEDURES, GuidedStep
from undm.drivers.base import Capability
from undm.drivers.registry import DriverRegistry
from undm.services import audit
from undm.services import devices as devsvc
from undm.services import templates as tplsvc
from undm.services.errors import ConflictError, NotFoundError
from undm.services.reach import require_bench

NOTE_MAX = 2000


@dataclass
class StepState:
    step: GuidedStep
    record: GuidedStepRecord | None


def procedure_of(device: Device,
                 registry: DriverRegistry) -> tuple[str, str, tuple[GuidedStep, ...]] | None:
    """(key, title, steps) of the device's guided procedure, if its driver has one."""
    if device.driver_id not in registry:
        return None
    cls = registry.get(device.driver_id)
    key = cls.guided_procedure
    if key is None or Capability.GUIDED_STAGING not in cls.info.capabilities:
        return None
    title, steps = PROCEDURES[key]
    return key, title, steps


def _need(device: Device, registry: DriverRegistry) -> tuple[str, str, tuple[GuidedStep, ...]]:
    found = procedure_of(device, registry)
    if found is None:
        raise NotFoundError(f"{device.name} is not staged with guided steps")
    return found


def states(session: Session, device: Device, registry: DriverRegistry) -> list[StepState]:
    _key, _title, steps = _need(device, registry)
    records = {r.step: r for r in session.scalars(
        select(GuidedStepRecord).where(GuidedStepRecord.device_id == device.id))}
    return [StepState(s, records.get(s.key)) for s in steps]


def all_done(session: Session, device: Device, registry: DriverRegistry) -> list[str]:
    """The titles of the steps not done yet (empty: staged)."""
    return [s.step.title for s in states(session, device, registry) if s.record is None]


def file_bytes(session: Session, version: ConfigVersion,
               template_role: str = "") -> tuple[str, bytes]:
    """(file name, bytes) of a configuration file as handed out: a file generated from the
    team's template is written as the team writes it (D-083); any other file as stored."""
    name = version.reference or f"{version.id[:8]}.txt"
    tpl = tplsvc.current(session).get(template_role) if template_role else None
    if tpl is not None and version.verification == "generated_from_team_template":
        return name, zr.as_file(version.text, tplsvc.file_of(tpl))
    return name, version.text.encode("utf-8")


def handed_out(session: Session, device: Device, registry: DriverRegistry,
               version_id: str) -> tuple[str, bytes]:
    """The file a "file" step hands out for this device."""
    _key, _title, steps = _need(device, registry)
    role = next((s.template_role for s in steps if s.kind == "file"), "")
    return file_bytes(session, _version(session, device, version_id), role)


def _version(session: Session, device: Device, version_id: str | None) -> ConfigVersion:
    version = session.get(ConfigVersion, version_id) if version_id else None
    if version is None or version.device_id != device.id or version.kind == "backup":
        raise ConflictError("Choose this device's file first (Stage a system, step 2)")
    return version


def _image(session: Session, device: Device, registry: DriverRegistry,
           image_id: str | None) -> FirmwareImage:
    image = session.get(FirmwareImage, image_id) if image_id else None
    if image is None:
        raise ConflictError("Choose the software package first (Stage a system, step 2)")
    if image.status != "approved":
        raise ConflictError(f"{image.filename} is not approved (Firmware page)")
    platform = registry.get(device.driver_id).info.platform
    if image.platform != platform or (image.compatible_models
                                      and device.model not in image.compatible_models):
        raise ConflictError(f"{image.filename} is not a package for {device.model}")
    return image


def mark_done(session: Session, device: Device, registry: DriverRegistry, actor: str,
              step_key: str, note: str = "", version_id: str | None = None,
              image_id: str | None = None) -> GuidedStepRecord:
    require_bench(device.project, "staging steps are recorded")
    key, _title, _steps = _need(device, registry)
    current = states(session, device, registry)
    found = next((s for s in current if s.step.key == step_key), None)
    if found is None:
        raise NotFoundError(f"No step '{step_key}'")
    before = current[:current.index(found)]
    missing = [s.step.title for s in before if s.record is None]
    if missing:
        raise ConflictError(f"Do '{missing[0]}' first")
    if found.record is not None:
        raise ConflictError(f"'{found.step.title}' is already recorded: undo it first")
    note = note.strip()[:NOTE_MAX]
    step = found.step
    file_name = file_sha = file_ref = None
    if step.kind == "check":
        result = devsvc.build_driver(device, registry, via="bench").connect()
        if not result.ok:
            raise ConflictError(result.message)
        note = note or result.message
    elif step.kind == "software":
        image = _image(session, device, registry, image_id)
        file_name, file_sha, file_ref = image.filename, image.sha256, image.id
    elif step.kind == "file":
        version = _version(session, device, version_id)
        file_name, data = file_bytes(session, version, step.template_role)
        file_sha, file_ref = hashlib.sha256(data).hexdigest(), version.id
    if step.note_label and len(note) < 3:
        raise ConflictError(f"Write what you saw: {step.note_label.lower()}")
    record = GuidedStepRecord(device_id=device.id, procedure=key, step=step.key,
                              done_by=actor, note=note, file_name=file_name,
                              file_sha256=file_sha, file_ref=file_ref)
    session.add(record)
    session.flush()
    audit.record(session, actor, "guided.step_done", "device", device.id, details={
        "procedure": key, "step": step.key, "note": note, "file": file_name,
        "file_sha256": file_sha})
    return record


def undo(session: Session, device: Device, registry: DriverRegistry, actor: str,
         step_key: str) -> list[str]:
    """Clear a step and every later one (they followed from it). Returns the steps cleared."""
    require_bench(device.project, "staging steps are recorded")
    current = states(session, device, registry)
    found = next((s for s in current if s.step.key == step_key), None)
    if found is None:
        raise NotFoundError(f"No step '{step_key}'")
    cleared = []
    for s in current[current.index(found):]:
        if s.record is not None:
            session.delete(s.record)
            cleared.append(s.step.key)
    session.flush()
    if cleared:
        audit.record(session, actor, "guided.step_undone", "device", device.id,
                     details={"steps": cleared})
    return cleared


def as_dict(session: Session, device: Device, registry: DriverRegistry) -> dict[str, Any]:
    key, title, _steps = _need(device, registry)

    def when(t: datetime | None) -> str | None:
        return t.isoformat() if t else None

    return {"procedure": key, "title": title, "steps": [{
        "key": s.step.key, "title": s.step.title, "detail": s.step.detail, "kind": s.step.kind,
        "note_label": s.step.note_label,
        "done_by": s.record.done_by if s.record else None,
        "done_at": when(s.record.done_at) if s.record else None,
        "note": s.record.note if s.record else "",
        "file_name": s.record.file_name if s.record else None,
        "file_sha256": s.record.file_sha256 if s.record else None,
    } for s in states(session, device, registry)]}
