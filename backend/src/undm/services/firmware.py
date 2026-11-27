"""Firmware repository: storage, integrity, approval, compatibility."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.db.models import DeploymentRecord, Device, FirmwareImage
from undm.domain.firmware import ImageRules, compatibility_issues
from undm.domain.operations import DeviceOperation
from undm.domain.validation import ValidationIssue
from undm.drivers.base import FirmwareImageRef
from undm.drivers.registry import DriverRegistry
from undm.services import audit
from undm.services.errors import ConflictError, NotFoundError, ServiceError

_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_HEX128 = re.compile(r"^[0-9a-fA-F]{128}$")


def vendor_checksum(value: str | None) -> tuple[str, str] | None:
    """('sha256' | 'sha512', lower-case hex) for a vendor-published checksum.

    MD5 (32 hex characters) is refused: it cannot show that a file is genuine."""
    text = "".join((value or "").split()).lower()
    if not text:
        return None
    if _HEX64.match(text):
        return "sha256", text
    if _HEX128.match(text):
        return "sha512", text
    if re.fullmatch(r"[0-9a-f]{32}", text):
        raise ServiceError("That looks like an MD5 checksum, which is not accepted. Use the "
                           "vendor's SHA-256 or SHA-512 (Fortinet: the SHA-512 under "
                           "'Checksum' on the download page).")
    raise ServiceError("Vendor checksum must be a SHA-256 (64 hexadecimal characters) or a "
                       "SHA-512 (128 hexadecimal characters)")


def _mismatch(algorithm: str, typed: str, actual: str, size: int, filename: str,
              then: str) -> str:
    """Both checksums side by side, so a person sees which one is off (bench 2026-11-27)."""
    name = algorithm.upper().replace("SHA", "SHA-")
    return (f"{name} mismatch. Typed: {typed}. The file UNDM received ({filename}, {size:,} "
            f"bytes): {actual}. {then} Check the file on this PC with: certutil -hashfile "
            f"\"{filename}\" {algorithm.upper()}. If certutil shows the file's value, the "
            "checksum typed belongs to another file; if it shows the typed one, the file "
            "changed on its way to UNDM. Type only the checksum the vendor publishes for this "
            "file; without one, leave it empty and approve the image with a written reason.")


def _file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
CHUNK = 1024 * 1024


class FirmwareRepository:
    def __init__(self, session: Session, data_dir: str, max_bytes: int) -> None:
        self.s = session
        self.root = Path(data_dir) / "firmware"
        self.max_bytes = max_bytes

    def get(self, image_id: str) -> FirmwareImage:
        img = self.s.get(FirmwareImage, image_id)
        if img is None:
            raise NotFoundError("Firmware image not found")
        return img

    def upload(
        self, stream: BinaryIO, filename: str, *, vendor: str, platform: str, version: str,
        compatible_models: list[str], min_from_version: str | None, vendor_sha256: str | None,
        release_notes: str, actor: str,
    ) -> FirmwareImage:
        published = vendor_checksum(vendor_sha256)  # the form field keeps its name
        if not version.strip():
            raise ServiceError("Version is required")
        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        digest512 = hashlib.sha512()
        size = 0
        fd, tmp_name = tempfile.mkstemp(dir=self.root, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ServiceError(
                            f"Image larger than the {self.max_bytes // 1024**2} MiB limit")
                    digest.update(chunk)
                    digest512.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise ServiceError("Uploaded file is empty")
            sha = digest.hexdigest()
            if published is not None:
                algorithm, expected = published
                actual = sha if algorithm == "sha256" else digest512.hexdigest()
                if expected != actual:
                    raise ServiceError(_mismatch(algorithm, expected, actual, size, filename,
                                                 "Nothing was stored."))
            if self.s.scalars(select(FirmwareImage).where(FirmwareImage.sha256 == sha)).first():
                raise ConflictError("This image file is already in the repository")
            final = self.root / f"{sha}_{_SAFE.sub('_', filename)[:120]}"
            shutil.move(tmp_name, final)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        img = FirmwareImage(
            vendor=vendor.strip(), platform=platform.strip(), version=version.strip(),
            filename=_SAFE.sub("_", filename)[:255], size_bytes=size, sha256=sha,
            vendor_sha256=published[1] if published and published[0] == "sha256" else None,
            vendor_sha512=published[1] if published and published[0] == "sha512" else None,
            integrity_verified=published is not None, storage_path=str(final),
            compatible_models=[m.strip() for m in compatible_models if m.strip()],
            min_from_version=(min_from_version or "").strip() or None,
            release_notes=release_notes, created_by=actor,
        )
        self.s.add(img)
        self.s.flush()
        audit.record(self.s, actor, "firmware.upload", "firmware_image", img.id, details={
            "filename": img.filename, "version": img.version, "platform": img.platform,
            "size": size, "sha256": sha, "integrity_verified": img.integrity_verified})
        return img

    def add_vendor_checksum(self, image_id: str, checksum: str, actor: str) -> FirmwareImage:
        """Verify an uploaded image against the vendor's checksum, without uploading again."""
        img = self.get(image_id)
        published = vendor_checksum(checksum)
        if published is None:
            raise ServiceError("Enter the vendor's checksum")
        path = Path(img.storage_path)
        if not path.is_file():
            raise ConflictError("Image file is missing from the repository storage")
        algorithm, expected = published
        actual = _file_digest(path, algorithm)
        if actual != expected:
            audit.record(self.s, actor, "firmware.verify", "firmware_image", img.id, "failed",
                         {"algorithm": algorithm, "file": actual})
            self.s.commit()  # keep the record of a failed integrity check
            raise ServiceError(_mismatch(algorithm, expected, actual, img.size_bytes, img.filename,
                                         "If the vendor's checksum is right, the stored file is "
                                         "corrupted or the wrong file: delete it."))
        if algorithm == "sha256":
            img.vendor_sha256 = expected
        else:
            img.vendor_sha512 = expected
        img.integrity_verified = True
        audit.record(self.s, actor, "firmware.verify", "firmware_image", img.id,
                     details={"algorithm": algorithm, "version": img.version})
        return img

    def approve(self, image_id: str, actor: str,
                unverified_reason: str | None = None) -> FirmwareImage:
        img = self.get(image_id)
        if img.status == "retired":
            raise ConflictError("Retired images cannot be approved")
        reason = " ".join((unverified_reason or "").split())
        if not img.integrity_verified:
            # Product owner decision (D-062): allowed only with a written reason, recorded
            # and shown wherever the image is used.
            if len(reason) < 10:
                raise ConflictError(
                    "Only images whose checksum matched the vendor's published SHA-256 or "
                    "SHA-512 can be approved, unless you give a reason for approving it "
                    "without one (at least 10 characters)")
            img.unverified_reason = reason[:500]
        if not Path(img.storage_path).is_file():
            raise ConflictError("Image file is missing from the repository storage")
        img.status, img.approved_by, img.approved_at = "approved", actor, datetime.now(UTC)
        audit.record(self.s, actor, "firmware.approve", "firmware_image", img.id,
                     details={"version": img.version,
                              "integrity_verified": img.integrity_verified,
                              "unverified_reason": None if img.integrity_verified
                              else img.unverified_reason})
        return img

    def retire(self, image_id: str, actor: str) -> FirmwareImage:
        img = self.get(image_id)
        img.status = "retired"
        audit.record(self.s, actor, "firmware.retire", "firmware_image", img.id)
        return img

    def delete(self, image_id: str, actor: str) -> None:
        img = self.get(image_id)
        used = self.s.scalars(select(DeploymentRecord.id).where(
            DeploymentRecord.firmware_image_id == img.id).limit(1)).first()
        if used:
            raise ConflictError("Image is referenced by a firmware deployment; retire it instead")
        Path(img.storage_path).unlink(missing_ok=True)
        self.s.delete(img)
        audit.record(self.s, actor, "firmware.delete", "firmware_image", image_id,
                     details={"filename": img.filename})

    @staticmethod
    def rules(img: FirmwareImage) -> ImageRules:
        return ImageRules(img.platform, img.version, tuple(img.compatible_models),
                          img.status == "approved", img.integrity_verified,
                          img.status == "retired",
                          None if img.integrity_verified else img.unverified_reason)

    @staticmethod
    def ref(img: FirmwareImage) -> FirmwareImageRef:
        return FirmwareImageRef(img.version, img.filename, img.sha256, img.size_bytes,
                                img.storage_path)


def device_compatibility(img: FirmwareImage, device: Device,
                         registry: DriverRegistry) -> list[ValidationIssue]:
    driver = registry.get(device.driver_id)
    observed_model = str((device.observed_facts or {}).get("model") or "")
    return compatibility_issues(
        FirmwareRepository.rules(img),
        device_models=(device.model, observed_model),
        driver_platform=driver.info.platform,
        driver_can_upgrade=not driver.missing_capabilities(DeviceOperation.INSTALL_FIRMWARE),
        driver_id=driver.info.driver_id,
    )


def issues_as_dicts(issues: list[ValidationIssue]) -> list[dict[str, str]]:
    return [{k: str(v) for k, v in asdict(i).items()} for i in issues]
