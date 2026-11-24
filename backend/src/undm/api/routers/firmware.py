from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy import select

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.schemas import (
    ApproveImageIn,
    CompatibilityIn,
    CompatibilityOut,
    FirmwareImageOut,
    IssueOut,
    VendorChecksumIn,
)
from undm.db.models import Device, FirmwareImage
from undm.domain.validation import Severity
from undm.services.errors import NotFoundError
from undm.services.firmware import FirmwareRepository, device_compatibility

router = APIRouter(prefix="/api/firmware", tags=["firmware"])


def _repo(session: SessionDep, settings: SettingsDep) -> FirmwareRepository:
    return FirmwareRepository(session, settings.data_dir, settings.max_firmware_bytes)


@router.get("/images", response_model=list[FirmwareImageOut])
def list_images(session: SessionDep) -> list[FirmwareImage]:
    return list(session.scalars(
        select(FirmwareImage).order_by(FirmwareImage.platform, FirmwareImage.created_at.desc())))


@router.post("/images", response_model=FirmwareImageOut, status_code=status.HTTP_201_CREATED)
def upload_image(
    session: SessionDep, settings: SettingsDep, actor: ActorDep,
    file: Annotated[UploadFile, File(description="Vendor firmware image")],
    vendor: Annotated[str, Form()],
    platform: Annotated[str, Form(description="Driver platform key: aoscx, fortios, iosxe")],
    version: Annotated[str, Form()],
    compatible_models: Annotated[str, Form(description="Comma-separated model names")],
    vendor_sha256: Annotated[str | None, Form(
        description="Vendor-published SHA-256 or SHA-512")] = None,
    min_from_version: Annotated[str | None, Form()] = None,
    release_notes: Annotated[str, Form()] = "",
) -> FirmwareImage:
    return _repo(session, settings).upload(
        file.file, file.filename or "image.bin", vendor=vendor, platform=platform,
        version=version, compatible_models=compatible_models.split(","),
        min_from_version=min_from_version, vendor_sha256=vendor_sha256 or None,
        release_notes=release_notes, actor=actor)


@router.get("/images/{image_id}", response_model=FirmwareImageOut)
def read_image(image_id: str, session: SessionDep, settings: SettingsDep) -> FirmwareImage:
    return _repo(session, settings).get(image_id)


@router.post("/images/{image_id}/checksum", response_model=FirmwareImageOut)
def add_checksum(image_id: str, body: VendorChecksumIn, session: SessionDep,
                 settings: SettingsDep, actor: ActorDep) -> FirmwareImage:
    """Verify an uploaded image against the vendor's SHA-256 or SHA-512."""
    return _repo(session, settings).add_vendor_checksum(image_id, body.checksum, actor)


@router.post("/images/{image_id}/approve", response_model=FirmwareImageOut)
def approve_image(image_id: str, session: SessionDep, settings: SettingsDep,
                  actor: ActorDep, body: ApproveImageIn | None = None) -> FirmwareImage:
    return _repo(session, settings).approve(
        image_id, actor, unverified_reason=body.unverified_reason if body else None)


@router.post("/images/{image_id}/retire", response_model=FirmwareImageOut)
def retire_image(image_id: str, session: SessionDep, settings: SettingsDep,
                 actor: ActorDep) -> FirmwareImage:
    return _repo(session, settings).retire(image_id, actor)


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(image_id: str, session: SessionDep, settings: SettingsDep,
                 actor: ActorDep) -> None:
    _repo(session, settings).delete(image_id, actor)


@router.post("/images/{image_id}/compatibility", response_model=list[CompatibilityOut])
def check_compatibility(image_id: str, body: CompatibilityIn, session: SessionDep,
                        settings: SettingsDep, registry: RegistryDep) -> list[CompatibilityOut]:
    """Offline check: no device is contacted."""
    img = _repo(session, settings).get(image_id)
    out = []
    for did in body.device_ids:
        device = session.get(Device, did)
        if device is None:
            raise NotFoundError(f"Device {did} not found")
        issues = device_compatibility(img, device, registry)
        out.append(CompatibilityOut(
            device_id=did, device_name=device.name,
            compatible=not any(i.severity is Severity.ERROR for i in issues),
            issues=[IssueOut(severity=i.severity.value, code=i.code, message=i.message,
                             path=i.path) for i in issues]))
    return out
