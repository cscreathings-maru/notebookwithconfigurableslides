"""Sources router — upload (file or URL), list per project, and read status.

Upload accepts a multipart file OR a `url` form field; the original is stored
under a tenant-prefixed key and an ingest job is enqueued. Status is exposed
accurately (queued/processing/ready/failed) so generation can be blocked until
sources are ready. Engine ids are never returned.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from ..auth.principal import Principal
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..ingestion.service import SourceService, source_display_name
from ..schemas.ingestion import SourceResponse
from ..tenancy.rbac import require_author, require_viewer
from .deps import get_project_repository, get_source_repository, get_source_service

router = APIRouter(tags=["sources"])


def _to_response(source) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        project_id=source.project_id,
        kind=source.kind,
        name=source_display_name(source),
        status=source.status,
        error=source.error,
        created_at=source.created_at,
    )


@router.post(
    "/projects/{project_id}/sources",
    response_model=SourceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_source(
    project_id: uuid.UUID,
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    _: Principal = Depends(require_author),
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    filename = file.filename if file is not None else None
    content = await file.read() if file is not None else None
    source = await service.create_source(
        project_id=project_id, filename=filename, content=content, url=url
    )
    return _to_response(source)


@router.get("/projects/{project_id}/sources", response_model=list[SourceResponse])
def list_sources(
    project_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    project_repo: ProjectRepository = Depends(get_project_repository),
    source_repo: SourceRepository = Depends(get_source_repository),
) -> list[SourceResponse]:
    project_repo.get(project_id)  # 404 across tenants / missing project
    return [_to_response(s) for s in source_repo.list_by_project(project_id)]


@router.get("/sources/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    source_repo: SourceRepository = Depends(get_source_repository),
) -> SourceResponse:
    return _to_response(source_repo.get(source_id))  # 404 across tenants
