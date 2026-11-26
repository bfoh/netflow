"""Export a system to one `.undm` file and import it on another copy of UNDM (D-087).

The package is a zip with ``manifest.json`` and the files it lists, each with its SHA-256.
It holds the system's settings, its devices (as entered: no retrieved facts, no history),
the names of its logins (never a user name, password or key), its imported and generated
configuration files, its topology and, on request, the firmware images its plans can use.

Configuration files can contain passwords as written by their authors (e.g. base64
"encrypted" passwords in Black Box files): a package must be handled as confidential.

Import checks the whole package before anything is created: format and version, every
file's checksum, file names (no paths outside the package), driver ids known here, sizes.
Logins are created by name without a password; the person stores the passwords on the
system's Logins tab. Firmware images arrive "uploaded", never approved: approval is a
decision of the copy that uses them.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm import __version__
from undm.configgen import zone as zone_rules
from undm.db.models import (
    ConfigVersion,
    CredentialRef,
    Device,
    FirmwareImage,
    Project,
    TopologyLink,
    TopologyPosition,
)
from undm.drivers.registry import DriverRegistry
from undm.services import app_settings, audit
from undm.services.devices import MAX_IMPORT_BYTES, import_config
from undm.services.errors import ConflictError, ServiceError
from undm.services.firmware import FirmwareRepository

FORMAT = "undm-system-package"
VERSION = 1
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 2000
_ENTRY = re.compile(r"^(files|firmware)/[A-Za-z0-9._-]{1,200}$")

DEVICE_FIELDS = (
    "name", "manufacturer", "product_family", "model", "hardware_revision", "category", "role",
    "os_family", "firmware_version", "management_address", "management_protocol",
    "management_port", "management_vrf", "site", "rack_location", "driver_id", "environment",
    "notes", "tags", "intent", "bootstrap_profile",
)


class PackageError(ServiceError):
    """The package cannot be imported; nothing was created."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_system(session: Session, project: Project, actor: str, *,
                  include_firmware: bool = False) -> bytes:
    devices = list(session.scalars(select(Device).where(Device.project_id == project.id)
                                   .order_by(Device.name)))
    keys = {d.id: f"d{i + 1}" for i, d in enumerate(devices)}
    refs = {r.id: r for r in project.credential_refs}
    # Logins for all systems that the devices use (D-105): listed by name, matched by name
    # with this PC's own logins for all systems on import.
    shared = {r.id: r for r in app_settings.shared_logins(session)
              if any(d.credential_ref_id == r.id for d in devices)}
    buf = io.BytesIO()
    manifest: dict[str, Any] = {
        "format": FORMAT, "version": VERSION, "undm_version": __version__,
        "created_at": datetime.now(UTC).isoformat(), "created_by": actor,
        "system": {"name": project.name, "description": project.description,
                   "site": project.site, "purpose": project.purpose,
                   "certificate_subject": project.certificate_subject,
                   "zone": project.zone, "system_id": project.system_id},
        "logins": sorted({r.name for r in refs.values()}),
        "shared_logins": sorted({r.name for r in shared.values()}),
        "devices": [], "files": [], "links": [], "firmware": [],
        "contains_passwords": "Configuration files are included as written; they may hold "
                              "passwords. Handle this package as confidential.",
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in devices:
            entry = {f: getattr(d, f) for f in DEVICE_FIELDS}
            entry["key"] = keys[d.id]
            ref = refs.get(d.credential_ref_id or "") or shared.get(d.credential_ref_id or "")
            entry["login"] = ref.name if ref else None
            entry["login_shared"] = bool(ref is not None and ref.project_id is None)
            pos = session.get(TopologyPosition, d.id)
            entry["position"] = {"x": pos.x, "y": pos.y} if pos else None
            manifest["devices"].append(entry)
            versions = session.scalars(
                select(ConfigVersion).where(ConfigVersion.device_id == d.id,
                                            ConfigVersion.kind.in_(("imported", "generated")))
                .order_by(ConfigVersion.created_at))
            for n, v in enumerate(versions, 1):
                data = v.text.encode()
                path = f"files/{keys[d.id]}-{n}.txt"
                z.writestr(path, data)
                manifest["files"].append({
                    "device": keys[d.id], "path": path, "sha256": _sha(data), "kind": v.kind,
                    "name": v.reference or f"{v.kind}.cfg",
                    "created_at": v.created_at.isoformat()})
        for link in session.scalars(select(TopologyLink).where(
                TopologyLink.project_id == project.id)):
            manifest["links"].append({
                "a": keys[link.a_device_id], "a_interface": link.a_interface,
                "b": keys[link.b_device_id], "b_interface": link.b_interface,
                "mode": link.mode, "vlans": list(link.vlans), "notes": link.notes})
        if include_firmware:
            models = {d.model for d in devices}
            for img in session.scalars(select(FirmwareImage).where(
                    FirmwareImage.status == "approved")):
                if img.compatible_models and not models & set(img.compatible_models):
                    continue
                path = f"firmware/{img.sha256}.bin"
                z.write(img.storage_path, path)
                manifest["firmware"].append({
                    "path": path, "sha256": img.sha256, "filename": img.filename,
                    "vendor": img.vendor, "platform": img.platform, "version": img.version,
                    "compatible_models": list(img.compatible_models),
                    "min_from_version": img.min_from_version,
                    "vendor_checksum": img.vendor_sha512 or img.vendor_sha256,
                    "release_notes": img.release_notes})
        z.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
    audit.record(session, actor, "system.export", "project", project.id, details={
        "devices": len(devices), "files": len(manifest["files"]),
        "firmware": len(manifest["firmware"]), "logins": len(manifest["logins"])})
    return buf.getvalue()


def _read_manifest(z: zipfile.ZipFile) -> dict[str, Any]:
    names = z.namelist()
    if len(names) > MAX_ENTRIES:
        raise PackageError("The package has too many files")
    if "manifest.json" not in names:
        raise PackageError("Not a UNDM system package (no manifest.json)")
    if z.getinfo("manifest.json").file_size > MAX_MANIFEST_BYTES:
        raise PackageError("The package's manifest is too large")
    try:
        manifest = json.loads(z.read("manifest.json"))
    except ValueError as e:
        raise PackageError(f"The package's manifest is not readable: {e}") from e
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise PackageError("Not a UNDM system package")
    if manifest.get("version") != VERSION:
        raise PackageError(f"Package format version {manifest.get('version')} is not supported "
                           f"by this copy of UNDM (it reads version {VERSION})")
    return manifest


def _entry(z: zipfile.ZipFile, item: dict[str, Any], limit: int) -> bytes:
    """One listed file, checked: a plain name inside the package, size, checksum."""
    path = str(item.get("path", ""))
    if not _ENTRY.fullmatch(path) or ".." in path:
        raise PackageError(f"The package lists an unsafe file name: {path!r}")
    try:
        info = z.getinfo(path)
    except KeyError as e:
        raise PackageError(f"The package lists {path} but does not contain it") from e
    if info.file_size > limit:
        raise PackageError(f"{path} is larger than allowed")
    data = z.read(path)
    if _sha(data) != item.get("sha256"):
        raise PackageError(f"{path} does not match its checksum: the package is damaged or "
                           "was changed after export")
    return data


def import_system(session: Session, package: BinaryIO, actor: str,
                  registry: DriverRegistry, repo: FirmwareRepository,
                  name: str | None = None) -> tuple[Project, dict[str, Any]]:
    try:
        z = zipfile.ZipFile(package)
    except zipfile.BadZipFile as e:
        raise PackageError("Not a UNDM system package (not a zip file)") from e
    with z:
        manifest = _read_manifest(z)
        system = manifest.get("system") or {}
        new_name = (name or str(system.get("name", ""))).strip()
        if not new_name:
            raise PackageError("The package has no system name; give one")
        if session.scalars(select(Project).where(Project.name == new_name)).first():
            raise ConflictError(f"A system named '{new_name}' exists already: give the imported "
                                "system another name")
        devices = list(manifest.get("devices") or [])
        keys = [str(d.get("key")) for d in devices]
        if len(set(keys)) != len(keys):
            raise PackageError("The package lists a device twice")
        for d in devices:
            if d.get("driver_id") not in registry:
                raise PackageError(f"Device {d.get('name')!r} uses '{d.get('driver_id')}', which "
                                   "this copy of UNDM does not have (update UNDM first)")
        files = [(f, _entry(z, f, MAX_IMPORT_BYTES)) for f in manifest.get("files") or []]
        for f, _ in files:
            if f.get("device") not in keys:
                raise PackageError(f"{f.get('path')} belongs to no device of the package")
        firmware = [(f, _entry(z, f, repo.max_bytes)) for f in manifest.get("firmware") or []]
        for link in manifest.get("links") or []:
            if link.get("a") not in keys or link.get("b") not in keys:
                raise PackageError("A topology link refers to a device not in the package")

        # Everything is checked: create the system.
        project = Project(name=new_name, description=str(system.get("description", "")),
                          site=str(system.get("site", "")), purpose=str(system.get("purpose", "")),
                          certificate_subject=system.get("certificate_subject"),
                          zone=system.get("zone") if isinstance(system.get("zone"), int)
                          and 1 <= system["zone"] <= 128 else None,
                          system_id=_system_id(system.get("system_id")))
        session.add(project)
        session.flush()
        logins: dict[str, CredentialRef] = {}
        here = {r.name: r for r in app_settings.shared_logins(session)}
        matched: list[str] = []

        def own_login(name: str) -> CredentialRef:
            ref = CredentialRef(project_id=project.id, name=name[:120], provider="keyring",
                                locator="pending")
            session.add(ref)
            session.flush()
            ref.locator = f"credential/{ref.id}"
            return ref

        for login in manifest.get("logins") or []:
            logins[str(login)[:120]] = own_login(str(login))
        shared_logins: dict[str, CredentialRef] = {}
        for login in manifest.get("shared_logins") or []:
            name = str(login)[:120]
            if name in here:
                shared_logins[name] = here[name]
                matched.append(name)
            else:  # not on this PC: a login of the new system, password to be stored
                shared_logins[name] = logins.get(name) or own_login(name)
                logins[name] = shared_logins[name]
        made: dict[str, Device] = {}
        for d in devices:
            fields = {f: d.get(f) for f in DEVICE_FIELDS if d.get(f) is not None}
            device = Device(project_id=project.id, **fields)
            name = str(d.get("login") or "")
            login = shared_logins.get(name) if d.get("login_shared") else logins.get(name)
            device.credential_ref_id = login.id if login else None
            session.add(device)
            session.flush()
            made[str(d["key"])] = device
            if isinstance(d.get("position"), dict):
                session.add(TopologyPosition(device_id=device.id, x=float(d["position"]["x"]),
                                             y=float(d["position"]["y"])))
        for f, data in files:
            import_config(session, made[str(f["device"])], registry, actor,
                          str(f.get("name") or "imported.cfg"), data.decode("utf-8", "replace"))
        for link in manifest.get("links") or []:
            session.add(TopologyLink(
                project_id=project.id, a_device_id=made[link["a"]].id,
                a_interface=str(link.get("a_interface", "")), b_device_id=made[link["b"]].id,
                b_interface=str(link.get("b_interface", "")), mode=str(link.get("mode", "routed")),
                vlans=list(link.get("vlans") or []), notes=str(link.get("notes", ""))))
        added, known = 0, 0
        for f, data in firmware:
            if session.scalars(select(FirmwareImage).where(
                    FirmwareImage.sha256 == f["sha256"])).first():
                known += 1
                continue
            repo.upload(io.BytesIO(data), str(f.get("filename") or "image.bin"),
                        vendor=str(f.get("vendor", "")), platform=str(f.get("platform", "")),
                        version=str(f.get("version", "")),
                        compatible_models=list(f.get("compatible_models") or []),
                        min_from_version=f.get("min_from_version"),
                        vendor_sha256=f.get("vendor_checksum"),
                        release_notes=str(f.get("release_notes", "")), actor=actor)
            added += 1
        summary = {"devices": len(made), "files": len(files), "logins": sorted(logins),
                   "shared_logins_used": sorted(matched),
                   "links": len(manifest.get("links") or []), "firmware_added": added,
                   "firmware_already_here": known, "exported_by": manifest.get("created_by"),
                   "exported_at": manifest.get("created_at")}
        audit.record(session, actor, "system.import", "project", project.id, details=summary)
        return project, summary


# -- a system's backups as files (D-097) --------------------------------------------------

_BACKUPS_README = """Backups of the devices of one system, taken by UNDM.

One folder per device. Each file is the device's configuration as UNDM read it:
  ...-before-...  just before a plan changed the device
  ...-after-...   read back after the change
Times are UTC. The name ends with the first characters of the plan's id, or of the
backup's own reference.

CONFIDENTIAL: these files are device configurations as read. They can hold password
hashes, SNMP community strings and site addressing. Handle them like the team's files.
"""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "device"


def export_backups(session: Session, project: Project, actor: str,
                   since: datetime | None = None) -> bytes:
    """Every backup of the system's devices as text files in one zip. Nothing is contacted."""
    devices = list(session.scalars(select(Device).where(Device.project_id == project.id)
                                   .order_by(Device.name)))
    out = io.BytesIO()
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", _BACKUPS_README)
        used: set[str] = set()
        for d in devices:
            folder = _safe(d.name)
            for v in session.scalars(select(ConfigVersion).where(
                    ConfigVersion.device_id == d.id, ConfigVersion.kind == "backup")
                    .order_by(ConfigVersion.created_at)):
                made = v.created_at if v.created_at.tzinfo else v.created_at.replace(tzinfo=UTC)
                if since is not None and made < since:
                    continue
                ref = v.reference or ""
                after = ref.startswith("after deployment ")
                tail = _safe(ref.rsplit(" ", 1)[-1].replace("undm-stored-", ""))[:12]
                name = (f"{folder}/{made.strftime('%Y%m%d-%H%M%S')}-"
                        f"{'after' if after else 'before'}-{tail}.txt")
                while name in used:  # two backups in one second with one reference
                    name = name[:-4] + "_.txt"
                used.add(name)
                z.writestr(name, v.text)
                count += 1
    audit.record(session, actor, "system.backups_export", "project", project.id,
                 details={"devices": len(devices), "backups": count,
                          "since": since.isoformat() if since else None})
    return out.getvalue()


def _system_id(value: object) -> str | None:
    """A system's number from a package, if it is one UNDM understands (D-114)."""
    if not isinstance(value, str):
        return None
    try:
        return zone_rules.parse_system(value).tag
    except zone_rules.ZoneError:
        return None
