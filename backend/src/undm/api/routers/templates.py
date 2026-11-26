"""Team templates for all systems and generating a system's files by zone (D-111) and
system (D-114), with the team's PCI table."""

import json
import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from undm.api.deps import ActorDep, RegistryDep, SessionDep
from undm.api.routers.projects import get_project
from undm.api.schemas import (
    ComparedFileOut,
    FilesZipIn,
    GeneratedFileOut,
    GenerateFilesIn,
    PciMappingOut,
    PciRowOut,
    TemplateImportIn,
    TemplateImportOut,
    TemplateOut,
    TemplatePreviewOut,
)
from undm.configgen import pci_table as pci_table_mod
from undm.configgen import zone as zr
from undm.services import pci_mapping
from undm.services import templates as svc
from undm.services.errors import NotFoundError, ServiceError

router = APIRouter(tags=["templates"])


@router.get("/api/templates", response_model=list[TemplateOut])
def list_templates(session: SessionDep) -> list[TemplateOut]:
    """The current template of each role (metadata only)."""
    older = svc.older(session)
    return [TemplateOut.model_validate(t).model_copy(update={"older": older.get(t.role, 0)})
            for t in svc.current(session).values()]


@router.post("/api/templates", response_model=TemplateImportOut,
             status_code=status.HTTP_201_CREATED)
def import_template(body: TemplateImportIn, session: SessionDep,
                    actor: ActorDep) -> TemplateImportOut:
    verify = ((body.verify.filename, body.verify.text, body.verify.zone, body.verify.system)
              if body.verify else None)
    done = svc.import_template(session, actor, body.role, body.filename, body.text, body.zone,
                               verify, system=body.system,
                               accept_differences=body.accept_differences)
    return TemplateImportOut(template=TemplateOut.model_validate(done.template),
                             to_check=[f"line {n}: {text}" for n, text in done.to_check[:20]],
                             verified_bytes=done.verified_bytes, accepted=done.accepted)


def _zip_response(data: bytes, name: str, skipped: list[str]) -> Response:
    # What was left out and why (URL-encoded JSON: a header carries Latin-1 only).
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-UNDM-Skipped": quote(json.dumps(skipped)),
        "Access-Control-Expose-Headers": "X-UNDM-Skipped"})


@router.get("/api/templates/files.zip", responses={200: {"content": {"application/zip": {}}}})
def download_files(session: SessionDep, actor: ActorDep,
                   zone: Annotated[int, Query(ge=1, le=128)],
                   system: Annotated[str | None, Query(max_length=8)] = None) -> Response:
    """Every current template for a zone (and system) in one zip, each file byte for byte
    as the team writes it (its line endings and final line break). Nothing is stored. Files
    that set a password from a device's login come only from a system (below)."""
    data, _, skipped = svc.files_zip(session, actor, zone, system)
    prefix = f"{system.upper()}-" if system else ""
    return _zip_response(data, f"{prefix}{zr.zone_tag(zone)}-files.zip", skipped)


@router.post("/api/projects/{project_id}/files.zip",
             responses={200: {"content": {"application/zip": {}}}})
def download_system_files(project_id: str, body: FilesZipIn, session: SessionDep,
                          actor: ActorDep) -> Response:
    """The system's files for its zone and system in one zip, byte for byte as the team
    writes them. The modem's file gets its password from the modem's login (named in
    ``assignments``). Nothing is stored."""
    project = get_project(session, project_id)
    if project.zone is None:
        raise ServiceError("This system has no zone yet: set it in Stage a system, step 1")
    data, _, skipped = svc.files_zip(session, actor, project.zone, project.system_id, project,
                                     {str(k): v for k, v in body.assignments.items()})
    label = re.sub(r"[^A-Za-z0-9._-]+", "_", project.name).strip("_") or "system"
    return _zip_response(data, f"{label}-files.zip", skipped)


@router.get("/api/templates/{role}/file",
            responses={200: {"content": {"application/octet-stream": {}}}})
def download_file(role: str, session: SessionDep,
                  zone: Annotated[int | None, Query(ge=1, le=128)] = None,
                  system: Annotated[str | None, Query(max_length=8)] = None) -> Response:
    """One role's file for a zone (and system), byte for byte as the team writes it."""
    name, data = svc.file_for(session, role, zone, system)
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{svc.safe_name(name, role)}"'})


@router.delete("/api/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, session: SessionDep, actor: ActorDep) -> None:
    svc.delete_template(session, actor, template_id)


@router.get("/api/templates/{role}/preview", response_model=TemplatePreviewOut)
def preview(role: str, session: SessionDep,
            zone: Annotated[int | None, Query(ge=1, le=128)] = None,
            system: Annotated[str | None, Query(max_length=8)] = None) -> TemplatePreviewOut:
    filename, text = svc.preview(session, role, zone, system)
    return TemplatePreviewOut(filename=filename, text=text)


@router.post("/api/projects/{project_id}/generate-files", response_model=list[GeneratedFileOut],
             status_code=status.HTTP_201_CREATED)
def generate_files(project_id: str, body: GenerateFilesIn, session: SessionDep,
                   registry: RegistryDep, actor: ActorDep) -> list[GeneratedFileOut]:
    project = get_project(session, project_id)
    made = svc.generate_files(session, registry, actor, project,
                              {str(k): v for k, v in body.assignments.items()})
    return [GeneratedFileOut(role=g.role, device_id=g.device_id, version_id=g.version.id,
                             filename=g.version.reference, template_version=g.template.version,
                             verified_zone=g.template.verified_zone) for g in made]


@router.post("/api/projects/{project_id}/compare-files", response_model=list[ComparedFileOut])
def compare_files(project_id: str, body: GenerateFilesIn,
                  session: SessionDep) -> list[ComparedFileOut]:
    """Read-only: each template for the system's zone against the file on its device."""
    project = get_project(session, project_id)
    return [ComparedFileOut(role=c.role, device_id=c.device_id, generated_name=c.generated_name,
                            file_name=c.file_name, same=c.same, lines=c.lines,
                            differences=c.differences)
            for c in svc.compare_files(session, project,
                                       {str(k): v for k, v in body.assignments.items()})]



# -- the team's PCI table (D-114) ------------------------------------------------------
@router.get("/api/settings/pci-mapping", response_model=PciMappingOut | None)
def pci_table(session: SessionDep) -> dict[str, object] | None:
    """What PCI table is in use (not its rows)."""
    return pci_mapping.summary(session)


@router.post("/api/settings/pci-mapping", response_model=PciMappingOut,
             status_code=status.HTTP_201_CREATED)
def import_pci_table(file: Annotated[UploadFile, File(description="The team's PCI table")],
                     session: SessionDep, actor: ActorDep) -> dict[str, object]:
    """Import the team's PCI table (.xlsx, or the same table as CSV); it replaces the last."""
    data = file.file.read(pci_table_mod.MAX_BYTES + 1)
    return pci_mapping.import_table(session, actor, file.filename or "pci.xlsx", data)


@router.get("/api/settings/pci-mapping/{system}", response_model=PciRowOut)
def pci_row(system: str, session: SessionDep) -> PciRowOut:
    """One system's PCIs (cell 1, 2, …)."""
    ref = svc._parse(system)  # noqa: SLF001 - the same parsing as everywhere
    found = pci_mapping.row(session, ref) if ref is not None else None
    if ref is None or found is None:
        raise NotFoundError(f"{system} is not in the PCI table")
    return PciRowOut(system=ref.tag, pcis=found)
