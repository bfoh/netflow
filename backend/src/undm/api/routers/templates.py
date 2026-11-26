"""Team templates for all systems and generating a system's files by zone (D-111)."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from undm.api.deps import ActorDep, RegistryDep, SessionDep
from undm.api.routers.projects import get_project
from undm.api.schemas import (
    ComparedFileOut,
    GeneratedFileOut,
    GenerateFilesIn,
    TemplateImportIn,
    TemplateImportOut,
    TemplateOut,
    TemplatePreviewOut,
)
from undm.configgen import zone as zr
from undm.services import templates as svc

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
    verify = (body.verify.filename, body.verify.text, body.verify.zone) if body.verify else None
    done = svc.import_template(session, actor, body.role, body.filename, body.text, body.zone,
                               verify)
    return TemplateImportOut(template=TemplateOut.model_validate(done.template),
                             to_check=[f"line {n}: {text}" for n, text in done.to_check[:20]],
                             verified_bytes=done.verified_bytes)


@router.get("/api/templates/files.zip", responses={200: {"content": {"application/zip": {}}}})
def download_files(session: SessionDep, actor: ActorDep,
                   zone: Annotated[int, Query(ge=1, le=128)]) -> Response:
    """Every current template for a zone in one zip, each file byte for byte as the team
    writes it (its line endings and final line break). Nothing is stored."""
    data, _ = svc.files_zip(session, actor, zone)
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{zr.zone_tag(zone)}-files.zip"'})


@router.get("/api/templates/{role}/file",
            responses={200: {"content": {"application/octet-stream": {}}}})
def download_file(role: str, session: SessionDep,
                  zone: Annotated[int | None, Query(ge=1, le=128)] = None) -> Response:
    """One role's file for a zone, byte for byte as the team writes it."""
    name, data = svc.file_for(session, role, zone)
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{svc.safe_name(name, role)}"'})


@router.delete("/api/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, session: SessionDep, actor: ActorDep) -> None:
    svc.delete_template(session, actor, template_id)


@router.get("/api/templates/{role}/preview", response_model=TemplatePreviewOut)
def preview(role: str, session: SessionDep,
            zone: Annotated[int | None, Query(ge=1, le=128)] = None) -> TemplatePreviewOut:
    filename, text = svc.preview(session, role, zone)
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

