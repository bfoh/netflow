"""Export and import of a whole system as one `.undm` file (D-087)."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from undm.api.deps import ActorDep, RegistryDep, SessionDep, SettingsDep
from undm.api.routers.projects import get_project
from undm.api.schemas import ProjectOut, SystemImportOut
from undm.services import system_package
from undm.services.firmware import FirmwareRepository

router = APIRouter(tags=["systems"])


@router.get("/api/projects/{project_id}/export",
            responses={200: {"content": {"application/zip": {}}}})
def export_system(project_id: str, session: SessionDep, actor: ActorDep,
                  include_firmware: Annotated[bool, Query()] = False) -> Response:
    """The system as one file: settings, devices, login names (no passwords), files,
    topology and, if asked, its approved firmware images. Handle it as confidential."""
    project = get_project(session, project_id)
    data = system_package.export_system(session, project, actor,
                                        include_firmware=include_firmware)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", project.name).strip("_") or "system"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.undm"'})


@router.post("/api/systems/import", response_model=SystemImportOut,
             status_code=status.HTTP_201_CREATED)
def import_system(file: Annotated[UploadFile, File(description="A .undm system package")],
                  session: SessionDep, registry: RegistryDep, settings: SettingsDep,
                  actor: ActorDep, name: Annotated[str | None, Form()] = None) -> dict[str, Any]:
    """Create a system from a package. Logins arrive without passwords; images unapproved."""
    repo = FirmwareRepository(session, settings.data_dir, settings.max_firmware_bytes)
    project, summary = system_package.import_system(session, file.file, actor, registry, repo,
                                                    name=name)
    return {"project": ProjectOut.model_validate(project), "summary": summary}
