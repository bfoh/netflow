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
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.configgen import zone as zr
from undm.db.models import ConfigTemplate, ConfigVersion, Device, Project
from undm.drivers.registry import DriverRegistry
from undm.security import credentials as creds
from undm.services import audit, pci_mapping
from undm.services.devices import MAX_IMPORT_BYTES, import_config
from undm.services.errors import ConflictError, NotFoundError, ServiceError

# Template roles: what each one is, in words.
ROLES: dict[str, str] = {
    "fortigate_base": "FortiGate base file (the same for every zone)",
    "fortigate_site": "FortiGate site script",
    "bhdmz": "BH-DMZ switch (Aruba 2930F, OOBM port 2)",
    "lte": "LTE switch (Aruba 2930F, OOBM port 3)",
    "tetra": "Tetra switch (Black Box LIG1014A)",
    "modem": "LTE modem (Nokia 7705 SAR-Hmc) configuration",
    "bbu_scf": "Flexi BBU site configuration file (SCF)",
}
NO_ZONE = {"fortigate_base"}  # kept as it is: nothing in it depends on the zone
# Files that also depend on the system (D-114), and which of its rules they use.
SYSTEM_ROLES: dict[str, dict[str, bool]] = {
    "modem": {"cells": False, "secrets": True},
    "bbu_scf": {"cells": True, "secrets": False},
}
# A file name that ends with the time it was made (the SCF: …_20260101-1200.xml).
_STAMP = re.compile(r"_\d{8}-\d{4}(\.[A-Za-z0-9]{1,5})$")
_PHYCELLID = re.compile(r'<p name="phyCellId">(\d+)</p>')

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
    # Lines of the second file the template does not give, kept by the person's decision.
    accepted: list[str] = field(default_factory=list)


def _system(role: str, given: str | None, *texts: str) -> zr.SystemRef | None:
    """The system of a file of a system role: given, or read from its name or text."""
    if role not in SYSTEM_ROLES:
        return None
    try:
        if given:
            return zr.parse_system(given)
    except zr.ZoneError as e:
        raise ServiceError(str(e)) from e
    for text in texts:
        found = zr.system_from_text(text)
        if found is not None:
            return found
    return None


def _name_pattern(role: str, name: str, ref: int | None, system: zr.SystemRef | None) -> str:
    if ref is None:
        return name
    pattern = zr.templatize(name, ref, system).text
    if role in SYSTEM_ROLES:
        # The team writes the modem file's zone tag without leading zeros (…z41.txt) and
        # stamps the SCF's name with the time it was made: a generated file gets its own.
        pattern = pattern.replace(zr.TAG, "z" + zr.ZONE)
        pattern = re.sub(rf"(?<!\d)z0*{ref}(?!\d)", "z" + zr.ZONE, pattern)
        pattern = _STAMP.sub(lambda m: "_" + zr.STAMP + m.group(1), pattern)
    return pattern


def _differences(result: zr.Comparison) -> list[str]:
    return [f"line {n}: UNDM '{a[:80]}' / file '{b[:80]}'" for n, a, b in result.differences]


def import_template(session: Session, actor: str, role: str, filename: str, text: str,
                    zone: int | None = None,
                    verify: tuple[str, str, int | None, str | None] | None = None,
                    system: str | None = None, accept_differences: bool = False) -> Imported:
    """Make a team file into the current template of its role. ``verify`` (file name, text,
    zone, system) is the same file for another zone (and system): the template must give it
    exactly, unless the person accepts the differences shown."""
    _role(role)
    fmt = zr.file_format(text)  # before cleaning: the team file as supplied
    text = _clean(text)
    name = filename.strip()[:200] or f"{role}.txt"
    ref_system = _system(role, system, name, text)
    if role in SYSTEM_ROLES and ref_system is None:
        raise ServiceError("Say which system this file is for (e.g. B007): its name or text "
                           "names none")
    if role in NO_ZONE:
        templated, ref = zr.Templated(text=text), None
        if "${" in text:
            raise ServiceError("The file contains '${', which UNDM uses for its own markers")
    else:
        ref = zone if zone is not None else (zr.zone_from_text(name) or zr.zone_from_text(text))
        if ref is None:
            raise ServiceError("Say which zone this file is for (its name or text names none)")
        try:
            templated = zr.templatize(text, ref, ref_system, **SYSTEM_ROLES.get(role, {}))
        except zr.ZoneError as e:
            raise ServiceError(str(e)) from e
        if zr.markers(templated.text) == 0:
            raise ServiceError(f"Nothing in this file depends on zone {ref}: is it the right "
                               "file and zone?")
        if SYSTEM_ROLES.get(role, {}).get("cells") and templated.cells == 0:
            raise ServiceError("No cell's phyCellId was found (LNCEL): is it the BBU's SCF?")
    verified: int | None = None
    verified_system: zr.SystemRef | None = None
    verified_bytes: bool | None = None
    accepted: list[str] = []
    if verify is not None:
        v_name, v_text, v_zone, v_system = verify
        other = v_zone if v_zone is not None else (zr.zone_from_text(v_name)
                                                    or zr.zone_from_text(v_text))
        other_system = _system(role, v_system, v_name, v_text)
        if role in NO_ZONE:
            raise ServiceError("The base file is the same for every zone: nothing to verify")
        if other is None or other == ref:
            raise ServiceError("The second file must be for another zone (say which)")
        if role in SYSTEM_ROLES and other_system is None:
            raise ServiceError("Say which system the second file is for (e.g. B007)")
        supplied = _clean(v_text)
        # Its own cells' PCIs (generated files take them from the PCI table instead), and
        # its password slot as in the template: the check is about everything else.
        pcis = tuple(int(v) for v in _PHYCELLID.findall(supplied))
        supplied_masked, _ = zr.mask_secrets(supplied)
        try:
            rendered = zr.render(templated.text, other, other_system, pcis, keep_secret=True)
        except zr.ZoneError as e:
            raise ServiceError(str(e)) from e
        result = zr.compare(rendered, supplied_masked, limit=50)
        if not result.same and not accept_differences:
            where = f"zone {other}" + (f", system {other_system.tag}" if other_system else "")
            raise ConflictError(
                f"The template does not give the {where} file exactly: "
                f"{len(result.differences)} line(s) differ, first at line "
                f"{result.differences[0][0]}. Nothing was kept.",
                details=_differences(result))
        accepted = _differences(result)
        verified, verified_system = other, other_system
        verified_bytes = (not accepted and zr.as_file(rendered, fmt)
                          == zr.mask_secrets(v_text.lstrip("\ufeff"))[0].encode("utf-8"))
    counts = dict(templated.counts) if ref is not None else {}
    if accepted:
        counts["accepted_differences"] = len(accepted)
    tpl = ConfigTemplate(role=role, version=version_of(name),
                         filename=_name_pattern(role, name, ref, ref_system),
                         reference_zone=ref, text=templated.text,
                         reference_system=ref_system.tag if ref_system else None,
                         sha256=hashlib.sha256(text.encode()).hexdigest(), counts=counts,
                         verified_zone=verified,
                         verified_system=verified_system.tag if verified_system else None,
                         line_ending=fmt.line_ending, final_newline=fmt.final_newline,
                         created_by=actor)
    session.add(tpl)
    session.flush()
    audit.record(session, actor, "template.import", "template", tpl.id, details={
        "role": role, "version": tpl.version, "reference_zone": ref, "verified_zone": verified,
        "reference_system": tpl.reference_system, "verified_system": tpl.verified_system,
        "counts": tpl.counts, "sha256": tpl.sha256, "lines": text.count("\n"),
        "line_ending": fmt.line_ending, "final_newline": fmt.final_newline,
        "verified_bytes": verified_bytes, "to_check": len(templated.to_check),
        # Line numbers only: the lines themselves are the team's file content.
        "accepted_differences": [a.split(":", 1)[0] for a in accepted]})
    return Imported(tpl, templated.to_check, verified_bytes, accepted)


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


@dataclass
class Values:
    """What a system's files are made with, besides the template."""

    zone: int | None
    system: zr.SystemRef | None = None
    secret: str | None = None  # the modem's admin password, from its login
    keep_secret: bool = False  # leave the password slot (a file stored for a later load)


def render_for(tpl: ConfigTemplate, zone: int | None, session: Session | None = None,
               values: Values | None = None) -> tuple[str, str]:
    """(file name, text) of a template for a zone (and system: its cells' PCIs come from
    the PCI table)."""
    if tpl.role in NO_ZONE:
        return tpl.filename, tpl.text
    if zone is None:
        raise ServiceError("This system has no zone yet: set it in Stage a system, step 1")
    v = values or Values(zone)
    needs = zr.needs(tpl.text) | zr.needs(tpl.filename)
    if "system" in needs and v.system is None:
        raise ServiceError("This file depends on the system: set the system (e.g. B007) in "
                           "Stage a system, step 1")
    pcis: tuple[int, ...] = ()
    if "pci" in needs and v.system is not None:
        if session is None:
            raise ServiceError("The cells' PCIs come from the PCI table")
        pcis = pci_mapping.pcis_for(session, v.system, zr.cells_of(tpl.text))
    stamp = datetime.now().strftime("%Y%m%d-%H%M")  # this PC's time, as the team's names
    try:
        return (zr.render(tpl.filename, zone, v.system, stamp=stamp),
                zr.render(tpl.text, zone, v.system, pcis, v.secret, keep_secret=v.keep_secret))
    except zr.ZoneError as e:
        raise ServiceError(str(e)) from e


def preview(session: Session, role: str, zone: int | None,
            system: str | None = None) -> tuple[str, str]:
    tpl = _current(session, role)
    return render_for(tpl, zone, session, Values(zone, _parse(system), keep_secret=True))


def _parse(system: str | None) -> zr.SystemRef | None:
    if not system:
        return None
    try:
        return zr.parse_system(system)
    except zr.ZoneError as e:
        raise ServiceError(str(e)) from e


def _current(session: Session, role: str) -> ConfigTemplate:
    tpl = current(session).get(_role(role))
    if tpl is None:
        raise NotFoundError(f"No template for {ROLES[role]} yet")
    return tpl


def file_of(tpl: ConfigTemplate) -> zr.FileFormat:
    return zr.FileFormat(line_ending=tpl.line_ending, final_newline=tpl.final_newline)


_NEEDS_LOGIN = ("its admin password comes from the modem's login: download it from Stage a "
                "system, with the modem's login chosen")


def file_for(session: Session, role: str, zone: int | None,
             system: str | None = None) -> tuple[str, bytes]:
    """(file name, bytes) of a role's current template for a zone, written exactly as the
    team writes the file (line endings, final line break)."""
    tpl = _current(session, role)
    if "secret" in zr.needs(tpl.text):
        raise ConflictError(f"The {ROLES[role]}: {_NEEDS_LOGIN}.")
    name, text = render_for(tpl, zone, session, Values(zone, _parse(system)))
    return name, zr.as_file(text, file_of(tpl))


def _login_password(session: Session, device_id: str | None) -> str | None:
    device = session.get(Device, device_id) if device_id else None
    if device is None or device.credential_ref is None:
        return None
    try:
        password = creds.resolve(device.credential_ref.provider,
                                 device.credential_ref.locator).password
    except creds.CredentialResolutionError:
        return None
    return password or None


def files_zip(session: Session, actor: str, zone: int, system: str | None = None,
              project: Project | None = None,
              assignments: dict[str, str] | None = None) -> tuple[bytes, list[str], list[str]]:
    """Every current template for a zone (and system), in one zip with the team's file
    names: (zip, names, skipped with the reason). Read-only (nothing is stored); the export
    is audited without content. A modem file is included only for a system whose modem
    has its login chosen: its password comes from that login."""
    templates = current(session)
    if not templates:
        raise NotFoundError("No templates yet: import them in Settings → For all systems")
    sys_ref = _parse(system)
    buf = io.BytesIO()
    names: list[str] = []
    skipped: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for role in ROLES:  # a fixed order
            tpl = templates.get(role)
            if tpl is None:
                continue
            needs = zr.needs(tpl.text) | zr.needs(tpl.filename)
            secret = None
            if "secret" in needs:
                device_id = (assignments or {}).get(role)
                secret = _login_password(session, device_id) if project is not None else None
                if secret is None:
                    skipped.append(f"{ROLES[role]}: {_NEEDS_LOGIN}" if project is None else
                                   f"{ROLES[role]}: choose the modem's login first (step 1)")
                    continue
            if "system" in needs and sys_ref is None:
                skipped.append(f"{ROLES[role]}: needs the system (e.g. B007)")
                continue
            try:
                name, text = render_for(tpl, zone, session, Values(zone, sys_ref, secret))
            except (ServiceError, ConflictError) as e:
                skipped.append(f"{ROLES[role]}: {e}")
                continue
            name = safe_name(name, role)
            if name in names:
                name = f"{role}-{name}"
            z.writestr(name, zr.as_file(text, file_of(tpl)))
            names.append(name)
    target = project.id if project is not None else f"zone-{zone}"
    audit.record(session, actor, "template.files_export",
                 "project" if project is not None else "template", target, details={
                     "zone": zone, "system": sys_ref.tag if sys_ref else None, "files": names,
                     "skipped": skipped,
                     "modem_login_used": any(r in (assignments or {}) for r in SYSTEM_ROLES
                                                if SYSTEM_ROLES[r]["secrets"])})
    return buf.getvalue(), names, skipped


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
    sys_ref = _parse(project.system_id)
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
        # A stored file keeps the password slot: the load fills it from the device's login.
        filename, text = render_for(tpl, project.zone, session,
                                    Values(project.zone, sys_ref, keep_secret=True))
        version = import_config(session, device, registry, actor, filename, text)
        version.template_version = f"{tpl.version or role}"[:20]
        version.verification = "generated_from_team_template"
        made.append(Generated(role, device_id, version, tpl))
    audit.record(session, actor, "config.generate", "project", project.id, details={
        "zone": project.zone, "system": project.system_id,
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
    sys_ref = _parse(project.system_id)
    templates = current(session)
    out: list[Compared] = []
    for role, device_id in assignments.items():
        tpl = templates.get(_role(role))
        if tpl is None:
            raise ConflictError(f"No template yet for {ROLES[role]}")
        device = session.get(Device, device_id)
        if device is None or device.project_id != project.id:
            raise NotFoundError(f"Device {device_id} not found in this system")
        name, text = render_for(tpl, project.zone, session,
                                Values(project.zone, sys_ref, keep_secret=True))
        # A FortiGate holds two files (base and site): the device's file that matches best.
        candidates = list(session.scalars(
            select(ConfigVersion).where(
                ConfigVersion.device_id == device_id, ConfigVersion.kind == "imported",
                ConfigVersion.verification != "generated_from_team_template")
            .order_by(ConfigVersion.created_at.desc())))
        if not candidates:
            out.append(Compared(role, device_id, name, None, False, 0, []))
            continue
        # Passwords are compared as slots: the template keeps none.
        results = [(zr.compare(text, zr.mask_secrets(c.text)[0], limit=10_000), c)
                   for c in candidates]
        best, theirs = min(results, key=lambda r: len(r[0].differences))
        out.append(Compared(role, device_id, name, theirs.reference, best.same, best.lines,
                            best.differences[:10]))
    return out

