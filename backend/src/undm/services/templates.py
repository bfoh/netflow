"""Team templates for all systems and the files generated from them by zone (D-111).

The team's own files are imported here on this PC; UNDM's code holds only the rules
(``configgen.zone``). A generated file is stored on its device like an imported file, so
every existing check applies to it unchanged (file recognition, secret settings, the HTTPS
certificate requirement, naming from the hostname).
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.configgen import zone as zr
from undm.db.models import ConfigTemplate, ConfigVersion, Device, Project
from undm.drivers.registry import DriverRegistry
from undm.services import audit
from undm.services.devices import MAX_IMPORT_BYTES, import_config
from undm.services.errors import ConflictError, NotFoundError, ServiceError

# Template roles: what each one is, in words.
ROLES: dict[str, str] = {
    "fortigate_base": "FortiGate base file (the same for every zone)",
    "fortigate_site": "FortiGate site script",
    "bhdmz": "BH-DMZ switch (Aruba 2930F, OOBM port 2)",
    "lte": "LTE switch (Aruba 2930F, OOBM port 3)",
    "tetra": "Tetra switch (Black Box LIG1014A)",
}
NO_ZONE = {"fortigate_base"}  # kept as it is: nothing in it depends on the zone

_VERSION = re.compile(r"(?i)(?<![a-z0-9])v\d+(?:\.\d+)*(?:-?d\d+)?(?![a-z0-9])")


def _clean(text: str) -> str:
    if len(text.encode()) > MAX_IMPORT_BYTES:
        raise ServiceError(f"The file is larger than {MAX_IMPORT_BYTES // 1024} KiB")
    if "\x00" in text:
        raise ServiceError("The file looks binary; import the team's plain-text file")
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ServiceError("The file is empty")
    return text if text.endswith("\n") else text + "\n"


def _role(role: str) -> str:
    if role not in ROLES:
        raise ServiceError(f"Unknown template role '{role}'")
    return role


def version_of(filename: str) -> str:
    """'z041-Fw-v14.2.cfg' -> 'v14.2' (the version in the team's file name, if any)."""
    stem = filename.rsplit(".", 1)[0] if re.search(r"\.[A-Za-z]{2,4}$", filename) else filename
    found = _VERSION.findall(stem)
    return found[-1] if found else ""


@dataclass
class Imported:
    template: ConfigTemplate
    to_check: list[tuple[int, str]] = field(default_factory=list)
    # With a second zone's file: whether the download is also that file byte for byte
    # (same line endings and final line break), not only line for line.
    verified_bytes: bool | None = None


def import_template(session: Session, actor: str, role: str, filename: str, text: str,
                    zone: int | None = None, verify: tuple[str, str, int | None] | None = None
                    ) -> Imported:
    """Make a team file into the current template of its role. ``verify`` (file name, text,
    zone) is the same file for another zone: the template must give it exactly."""
    _role(role)
    fmt = zr.file_format(text)  # before cleaning: the team file as supplied
    text = _clean(text)
    name = filename.strip()[:200] or f"{role}.txt"
    if role in NO_ZONE:
        templated, ref = zr.Templated(text=text), None
        if "${" in text:
            raise ServiceError("The file contains '${', which UNDM uses for its own markers")
    else:
        ref = zone if zone is not None else (zr.zone_from_text(name) or zr.zone_from_text(text))
        if ref is None:
            raise ServiceError("Say which zone this file is for (its name or text names none)")
        try:
            templated = zr.templatize(text, ref)
        except zr.ZoneError as e:
            raise ServiceError(str(e)) from e
        if zr.markers(templated.text) == 0:
            raise ServiceError(f"Nothing in this file depends on zone {ref}: is it the right "
                               "file and zone?")
    verified: int | None = None
    verified_bytes: bool | None = None
    if verify is not None:
        v_name, v_text, v_zone = verify
        other = v_zone if v_zone is not None else zr.zone_from_text(v_name)
        if role in NO_ZONE:
            raise ServiceError("The base file is the same for every zone: nothing to verify")
        if other is None or other == ref:
            raise ServiceError("The second file must be for another zone (say which)")
        try:
            result = zr.compare(zr.render(templated.text, other), _clean(v_text))
        except zr.ZoneError as e:
            raise ServiceError(str(e)) from e
        if not result.same:
            raise ConflictError(
                f"The template does not give the zone {other} file exactly: "
                f"{len(result.differences)} line(s) differ, first at line "
                f"{result.differences[0][0]}. Nothing was kept.",
                details=[f"line {n}: UNDM '{a[:80]}' / file '{b[:80]}'"
                         for n, a, b in result.differences])
        verified = other
        verified_bytes = (zr.as_file(zr.render(templated.text, other), fmt)
                          == v_text.lstrip("\ufeff").encode("utf-8"))
    file_pattern = zr.templatize(name, ref).text if ref is not None else name
    tpl = ConfigTemplate(role=role, version=version_of(name), filename=file_pattern,
                         reference_zone=ref, text=templated.text,
                         sha256=hashlib.sha256(text.encode()).hexdigest(),
                         counts=templated.counts if ref is not None else {},
                         verified_zone=verified, line_ending=fmt.line_ending,
                         final_newline=fmt.final_newline, created_by=actor)
    session.add(tpl)
    session.flush()
    audit.record(session, actor, "template.import", "template", tpl.id, details={
        "role": role, "version": tpl.version, "reference_zone": ref, "verified_zone": verified,
        "counts": tpl.counts, "sha256": tpl.sha256, "lines": text.count("\n"),
        "line_ending": fmt.line_ending, "final_newline": fmt.final_newline,
        "verified_bytes": verified_bytes, "to_check": len(templated.to_check)})
    return Imported(tpl, templated.to_check, verified_bytes)


def current(session: Session) -> dict[str, ConfigTemplate]:
    """The newest template of each role."""
    out: dict[str, ConfigTemplate] = {}
    for t in session.scalars(select(ConfigTemplate).order_by(ConfigTemplate.created_at.desc())):
        out.setdefault(t.role, t)
    return out


def older(session: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in session.scalars(select(ConfigTemplate)):
        counts[t.role] = counts.get(t.role, 0) + 1
    return {r: n - 1 for r, n in counts.items()}


def delete_template(session: Session, actor: str, template_id: str) -> None:
    tpl = session.get(ConfigTemplate, template_id)
    if tpl is None:
        raise NotFoundError("Template not found")
    session.delete(tpl)
    audit.record(session, actor, "template.delete", "template", template_id,
                 details={"role": tpl.role, "version": tpl.version})


def render_for(tpl: ConfigTemplate, zone: int | None) -> tuple[str, str]:
    """(file name, text) of a template for a zone."""
    if tpl.role in NO_ZONE:
        return tpl.filename, tpl.text
    if zone is None:
        raise ServiceError("This system has no zone yet: set it in Stage a system, step 1")
    try:
        return zr.render(tpl.filename, zone), zr.render(tpl.text, zone)
    except zr.ZoneError as e:
        raise ServiceError(str(e)) from e


def preview(session: Session, role: str, zone: int | None) -> tuple[str, str]:
    return render_for(_current(session, role), zone)


def _current(session: Session, role: str) -> ConfigTemplate:
    tpl = current(session).get(_role(role))
    if tpl is None:
        raise NotFoundError(f"No template for {ROLES[role]} yet")
    return tpl


def file_of(tpl: ConfigTemplate) -> zr.FileFormat:
    return zr.FileFormat(line_ending=tpl.line_ending, final_newline=tpl.final_newline)


def file_for(session: Session, role: str, zone: int | None) -> tuple[str, bytes]:
    """(file name, bytes) of a role's current template for a zone, written exactly as the
    team writes the file (line endings, final line break)."""
    tpl = _current(session, role)
    name, text = render_for(tpl, zone)
    return name, zr.as_file(text, file_of(tpl))


def files_zip(session: Session, actor: str, zone: int) -> tuple[bytes, list[str]]:
    """Every current template for a zone, in one zip with the team's file names. Read-only
    (nothing is stored); the export is audited without content."""
    templates = current(session)
    if not templates:
        raise NotFoundError("No templates yet: import them in Settings → For all systems")
    buf = io.BytesIO()
    names: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for role in ROLES:  # a fixed order
            tpl = templates.get(role)
            if tpl is None:
                continue
            name, text = render_for(tpl, zone)
            name = safe_name(name, role)
            if name in names:
                name = f"{role}-{name}"
            z.writestr(name, zr.as_file(text, file_of(tpl)))
            names.append(name)
    audit.record(session, actor, "template.files_export", "template", f"zone-{zone}", details={
        "zone": zone, "files": names})
    return buf.getvalue(), names


def safe_name(name: str, role: str) -> str:
    """A template's file name as a plain zip entry (no folders, no drive letters)."""
    base = re.split(r"[\\/]", name)[-1].strip()
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return base or f"{role}.txt"


@dataclass
class Generated:
    role: str
    device_id: str
    version: ConfigVersion
    template: ConfigTemplate


def generate_files(session: Session, registry: DriverRegistry, actor: str, project: Project,
                   assignments: dict[str, str]) -> list[Generated]:
    """The system's files from the current templates, for its zone: one per role and device."""
    if project.zone is None:
        raise ConflictError("This system has no zone yet: set it in Stage a system, step 1")
    templates = current(session)
    missing = [ROLES[_role(r)] for r in assignments if r not in templates]
    if missing:
        raise ConflictError("No template yet for: " + ", ".join(missing)
                            + ". Import it in Settings → For all systems.")
    made: list[Generated] = []
    for role, device_id in assignments.items():
        device = session.get(Device, device_id)
        if device is None or device.project_id != project.id:
            raise NotFoundError(f"Device {device_id} not found in this system")
        tpl = templates[role]
        filename, text = render_for(tpl, project.zone)
        version = import_config(session, device, registry, actor, filename, text)
        version.template_version = f"{tpl.version or role}"[:20]
        version.verification = "generated_from_team_template"
        made.append(Generated(role, device_id, version, tpl))
    audit.record(session, actor, "config.generate", "project", project.id, details={
        "zone": project.zone,
        "files": [{"role": g.role, "device": g.device_id, "template_version": g.template.version,
                   "verified_zone": g.template.verified_zone, "sha256": g.version.sha256}
                  for g in made]})
    return made


@dataclass
class Compared:
    role: str
    device_id: str
    generated_name: str
    file_name: str | None  # the device's current file, if it has one
    same: bool
    lines: int
    differences: list[tuple[int, str, str]]


def compare_files(session: Session, project: Project,
                  assignments: dict[str, str]) -> list[Compared]:
    """Each template rendered for the system's zone against the file already on its device
    (the newest one imported by a person, not one UNDM generated). Read-only."""
    if project.zone is None:
        raise ConflictError("This system has no zone yet: set it in Stage a system, step 1")
    templates = current(session)
    out: list[Compared] = []
    for role, device_id in assignments.items():
        tpl = templates.get(_role(role))
        if tpl is None:
            raise ConflictError(f"No template yet for {ROLES[role]}")
        device = session.get(Device, device_id)
        if device is None or device.project_id != project.id:
            raise NotFoundError(f"Device {device_id} not found in this system")
        name, text = render_for(tpl, project.zone)
        # A FortiGate holds two files (base and site): the device's file that matches best.
        candidates = list(session.scalars(
            select(ConfigVersion).where(
                ConfigVersion.device_id == device_id, ConfigVersion.kind == "imported",
                ConfigVersion.verification != "generated_from_team_template")
            .order_by(ConfigVersion.created_at.desc())))
        if not candidates:
            out.append(Compared(role, device_id, name, None, False, 0, []))
            continue
        results = [(zr.compare(text, c.text, limit=10_000), c) for c in candidates]
        best, theirs = min(results, key=lambda r: len(r[0].differences))
        out.append(Compared(role, device_id, name, theirs.reference, best.same, best.lines,
                            best.differences[:10]))
    return out

