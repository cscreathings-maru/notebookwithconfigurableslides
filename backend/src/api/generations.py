"""Generations router — enqueue, poll status/report, list history, signed download.

Engine ids/paths stay server-side: downloads return a short-lived signed object-store
URL, never the engine path or MinIO key.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from ..auth.principal import Principal
from ..core.config import get_settings
from ..core.errors import NotFoundError, ValidationError
from ..generation.freeform_service import FreeformGenerationService
from ..generation.repository import GenerationRepository
from ..generation.service import GenerationService
from ..models import Generation, GenerationStatus
from ..schemas.generation import (
    ArtifactAvailability,
    DownloadResponse,
    GenerationCreate,
    GenerationResponse,
)
from ..storage.object_store import ObjectStore
from ..tenancy.rbac import require_author, require_viewer
from .deps import (
    get_freeform_generation_service,
    get_generation_repository,
    get_generation_service,
    get_object_store,
)

router = APIRouter(tags=["generations"])

# Provenance knobs safe to expose. The engine template ref and the bulky generated
# content/markdown stay server-side.
_PUBLIC_PARAM_KEYS = frozenset(
    {
        "tone",
        "verbosity",
        "n_slides",
        "language",
        "include_title_slide",
        "include_table_of_contents",
        "export_as",
        "web_search",
    }
)


def _public_params(params: dict | None) -> dict:
    return {k: v for k, v in (params or {}).items() if k in _PUBLIC_PARAM_KEYS}


def _to_response(g: Generation) -> GenerationResponse:
    return GenerationResponse(
        id=g.id,
        project_id=g.project_id,
        outline_id=g.outline_id,
        status=g.status,
        profile_version=g.profile_version,
        template_version=g.template_version,
        model=g.model,
        provider=g.provider,
        params=_public_params(g.params),
        source_ids=g.source_ids or [],
        consistency_report=g.consistency_report,
        artifacts=ArtifactAvailability(pptx=bool(g.pptx_uri), pdf=bool(g.pdf_uri)),
        error=g.error,
        created_by=g.created_by,
        created_at=g.created_at,
    )


@router.post(
    "/projects/{project_id}/generations",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation(
    project_id: uuid.UUID,
    payload: GenerationCreate,
    principal: Principal = Depends(require_author),
    service: GenerationService = Depends(get_generation_service),
    freeform_service: FreeformGenerationService = Depends(get_freeform_generation_service),
) -> GenerationResponse:
    # Freeform (NotebookLM Studio) path when a content source is chosen; otherwise
    # the governed outline path.
    if payload.content_source is not None:
        generation = await freeform_service.create(
            project_id=project_id, payload=payload, created_by=principal.user_id
        )
    elif payload.outline_id is not None:
        generation = await service.create(
            project_id=project_id,
            outline_id=payload.outline_id,
            created_by=principal.user_id,
        )
    else:
        raise ValidationError("Provide either content_source (freeform) or outline_id.")
    return _to_response(generation)


@router.get("/projects/{project_id}/generations", response_model=list[GenerationResponse])
def list_generations(
    project_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    repo: GenerationRepository = Depends(get_generation_repository),
) -> list[GenerationResponse]:
    return [_to_response(g) for g in repo.list_by_project(project_id)]


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
def get_generation(
    generation_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    repo: GenerationRepository = Depends(get_generation_repository),
) -> GenerationResponse:
    return _to_response(repo.get(generation_id))


@router.get("/generations/{generation_id}/download", response_model=DownloadResponse)
def download_generation(
    generation_id: uuid.UUID,
    fmt: str = Query("pptx", alias="format", pattern="^(pptx|pdf)$"),
    _: Principal = Depends(require_viewer),
    repo: GenerationRepository = Depends(get_generation_repository),
    object_store: ObjectStore = Depends(get_object_store),
) -> DownloadResponse:
    generation = repo.get(generation_id)
    if generation.status is not GenerationStatus.ready:
        raise ValidationError("Generation is not ready for download.")

    key = generation.pptx_uri if fmt == "pptx" else generation.pdf_uri
    if not key:
        raise NotFoundError(f"No {fmt} artifact for this generation.")

    url = object_store.presigned_get(key=key)
    return DownloadResponse(
        format=fmt, url=url, expires_in=get_settings().ingest_presign_ttl_seconds
    )
