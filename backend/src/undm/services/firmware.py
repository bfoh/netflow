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
        if vendor_sha256 and not _HEX64.match(vendor_sha256.strip()):
            raise ServiceError("Vendor SHA-256 must be 64 hexadecimal characters")
        if not version.strip():
            raise ServiceError("Version is required")
        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
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
                    out.write(chunk)
            if size == 0:
                raise ServiceError("Uploaded file is empty")
            sha = digest.hexdigest()
            if vendor_sha256 and vendor_sha256.strip().lower() != sha:
                raise ServiceError(
                    "SHA-256 mismatch: the file does not match the checksum published by the "
                    f"vendor (file {sha}). The download may be corrupted or the wrong file.")
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
            vendor_sha256=vendor_sha256.strip().lower() if vendor_sha256 else None,
            integrity_verified=bool(vendor_sha256), storage_path=str(final),
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

    def approve(self, image_id: str, actor: str) -> FirmwareImage:
        img = self.get(image_id)
        if img.status == "retired":
            raise ConflictError("Retired images cannot be approved")
        if not img.integrity_verified:
            raise ConflictError("Only images whose checksum matched the vendor's SHA-256 "
                                "can be approved")
        if not Path(img.storage_path).is_file():
            raise ConflictError("Image file is missing from the repository storage")
        img.status, img.approved_by, img.approved_at = "approved", actor, datetime.now(UTC)
        audit.record(self.s, actor, "firmware.approve", "firmware_image", img.id,
                     details={"version": img.version})
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
                          img.status == "retired")

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
