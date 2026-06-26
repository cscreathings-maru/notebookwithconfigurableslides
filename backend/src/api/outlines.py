"""Outlines router — build (author), read, and re-validate edited outlines."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from ..auth.principal import Principal
from ..models import Outline
from ..outline.service import OutlineService
from ..schemas.outline import OutlineCreate, OutlineResponse, OutlineUpdate
from ..tenancy.rbac import require_author, require_viewer
from .deps import get_outline_service

router = APIRouter(tags=["outlines"])


def _to_response(o: Outline) -> OutlineResponse:
    return OutlineResponse(
        id=o.id,
        project_id=o.project_id,
        profile_id=o.profile_id,
        profile_version=o.profile_version,
        schema_version=o.schema_version,
        content=o.content,
        valid=o.valid,
        created_at=o.created_at,
    )


@router.post(
    "/projects/{project_id}/outline",
    response_model=OutlineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_outline(
    project_id: uuid.UUID,
    payload: OutlineCreate,
    principal: Principal = Depends(require_author),
    service: OutlineService = Depends(get_outline_service),
) -> OutlineResponse:
    outline = await service.build(
        project_id=project_id, profile_id=payload.profile_id, created_by=principal.user_id
    )
    return _to_response(outline)


@router.get("/outlines/{outline_id}", response_model=OutlineResponse)
def get_outline(
    outline_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    service: OutlineService = Depends(get_outline_service),
) -> OutlineResponse:
    return _to_response(service.get(outline_id))


@router.put("/outlines/{outline_id}", response_model=OutlineResponse)
def update_outline(
    outline_id: uuid.UUID,
    payload: OutlineUpdate,
    _: Principal = Depends(require_author),
    service: OutlineService = Depends(get_outline_service),
) -> OutlineResponse:
    return _to_response(service.update(outline_id, content=payload.content))
