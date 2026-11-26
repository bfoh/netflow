"""Guided staging (D-117): the steps a person does in a device's own portal, recorded."""

from urllib.parse import quote

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from undm.api.deps import ActorDep, RegistryDep, SessionDep
from undm.db.models import Device
from undm.services import guided as svc
from undm.services.errors import NotFoundError

router = APIRouter(prefix="/api/devices", tags=["guided"])


class GuidedStepIn(BaseModel):
    note: str = Field(default="", max_length=svc.NOTE_MAX)
    version_id: str | None = None  # "file" step: the file handed out
    image_id: str | None = None  # "software" step: the approved package


def _device(session: SessionDep, device_id: str) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise NotFoundError("Device not found")
    return device


@router.get("/{device_id}/guided")
def guided(device_id: str, session: SessionDep, registry: RegistryDep) -> dict[str, object]:
    return svc.as_dict(session, _device(session, device_id), registry)


@router.post("/{device_id}/guided/{step}")
def guided_done(device_id: str, step: str, body: GuidedStepIn, session: SessionDep,
                registry: RegistryDep, actor: ActorDep) -> dict[str, object]:
    """Record that a person did a step in the device's portal (nothing is sent to it; a
    "check" step checks, read-only, that the portal answers)."""
    device = _device(session, device_id)
    svc.mark_done(session, device, registry, actor, step, body.note, body.version_id,
                  body.image_id)
    return svc.as_dict(session, device, registry)


@router.delete("/{device_id}/guided/{step}")
def guided_undo(device_id: str, step: str, session: SessionDep, registry: RegistryDep,
                actor: ActorDep) -> dict[str, object]:
    device = _device(session, device_id)
    svc.undo(session, device, registry, actor, step)
    return svc.as_dict(session, device, registry)


@router.get("/{device_id}/guided-file/{version_id}")
def guided_file(device_id: str, version_id: str, session: SessionDep,
                registry: RegistryDep) -> Response:
    """The file a step hands out, byte for byte as the team writes it."""
    name, data = svc.handed_out(session, _device(session, device_id), registry, version_id)
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
