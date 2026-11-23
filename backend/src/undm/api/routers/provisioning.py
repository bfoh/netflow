from typing import Any

from fastapi import APIRouter

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.routers.devices import get_device
from undm.api.schemas import (
    BootstrapPreviewIn,
    BootstrapPreviewOut,
    ConsoleBootstrapIn,
    ConsoleBootstrapOut,
    SerialPortOut,
)
from undm.services import provisioning as svc
from undm.services.policy import Policy

router = APIRouter(tags=["provisioning"])


@router.get("/api/provisioning/serial-ports", response_model=list[SerialPortOut])
def serial_ports() -> list[dict[str, str]]:
    """Serial (COM) ports of the machine running the backend, plus the simulated console."""
    return svc.serial_ports()


@router.post("/api/devices/{device_id}/provisioning/console-bootstrap/preview",
             response_model=BootstrapPreviewOut)
def preview(device_id: str, body: BootstrapPreviewIn, session: SessionDep,
            registry: RegistryDep, settings: SettingsDep) -> dict[str, Any]:
    """The exact commands a bootstrap would send. Contacts no device."""
    d = get_device(session, device_id)
    profile = body.profile.model_dump(mode="json") if body.profile else None
    return svc.preview(d, registry, Policy.from_settings(settings), profile)


@router.post("/api/devices/{device_id}/provisioning/console-bootstrap",
             response_model=ConsoleBootstrapOut)
def console_bootstrap(device_id: str, body: ConsoleBootstrapIn, session: SessionDep,
                      registry: RegistryDep, settings: SettingsDep,
                      actor: ActorDep) -> dict[str, Any]:
    d = get_device(session, device_id)
    return svc.run_console_bootstrap(
        session, d, registry, Policy.from_settings(settings), actor,
        serial_port=body.serial_port, baudrate=body.baudrate,
        profile=body.profile.model_dump(mode="json") if body.profile else None,
        confirm_device_name=body.confirm_device_name, allow_configured=body.allow_configured,
        erase_existing=body.erase_existing,
        current_credential_ref_id=body.current_credential_ref_id,
        confirm_hostname=body.confirm_hostname)
