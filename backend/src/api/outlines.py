"""Outlines router — build (author), read, and re-validate edited outlines."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from ..auth.principal import Principal
from ..core.errors import ValidationError
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
    # Polymorphic on the same shape as POST /generations (api/generations.py) --
    # profile_id selects governed, content_source selects freeform (DG-1). Kept as
    # one branch in one place for the same reason that endpoint documents: this
    # codebase's recurring failure mode is two paths drifting apart when they're
    # built as separate services with no shared gate (docs/ARCHITECTURE.md §3).
    if payload.profile_id is not None:
        outline = await service.build(
            project_id=project_id, profile_id=payload.profile_id, created_by=principal.user_id
        )
    elif payload.content_source is not None:
        outline = await service.build_freeform(
            project_id=project_id,
            content_source=payload.content_source,
            custom_markdown=payload.custom_markdown,
            chat_message_id=payload.chat_message_id,
            tone=payload.tone.value,
            density=payload.density.value,
            n_slides_hint=payload.n_slides_hint,
            language=payload.language,
            created_by=principal.user_id,
        )
    else:
        raise ValidationError("Provide either profile_id (governed) or content_source (freeform).")
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
