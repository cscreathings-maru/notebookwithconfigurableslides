"""Projects router — create/list/read projects (tenant-scoped).

Creating a project also provisions its Open Notebook notebook; the engine id is
stored server-side and never returned. Author role required for creation; any
authenticated tenant member may read.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from ..auth.principal import Principal
from ..ingestion.repository import ProjectRepository
from ..ingestion.service import ProjectService
from ..schemas.ingestion import ProjectCreate, ProjectResponse
from ..tenancy.rbac import require_author, require_viewer
from .deps import get_project_repository, get_project_service

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_response(project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    principal: Principal = Depends(require_author),
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    project = await service.create(name=payload.name, created_by=principal.user_id)
    return _to_response(project)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    _: Principal = Depends(require_viewer),
    repo: ProjectRepository = Depends(get_project_repository),
) -> list[ProjectResponse]:
    return [_to_response(p) for p in repo.list()]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    repo: ProjectRepository = Depends(get_project_repository),
) -> ProjectResponse:
    return _to_response(repo.get(project_id))  # 404 across tenants
