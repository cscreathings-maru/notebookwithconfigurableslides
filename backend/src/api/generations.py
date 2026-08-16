"""Generations router — enqueue, poll status/report, list history, artifact download.

Deck bytes are streamed through this process rather than presigned: MinIO is
reachable only on the internal Docker network, so a presigned URL names a
host (`http://minio:9000`) that no browser can resolve. Streaming keeps the
artifact behind the existing tenant + RBAC guards and adds no new public
surface.

RM-11 collapsed the governed/freeform split into one `GenerationService` --
this router no longer branches on `content_source` vs `outline_id` itself,
the service does (`docs/ARCHITECTURE.md` §3 named that branching, done
twice, as the actual recurring divergence).

LD-9: the per-generation plan review endpoints (`/plan`, `/plan/approve`,
D5/RM-9) are retired -- the review gate moved to the template's catalog
(`/templates/{id}/catalog/review`, L3), reviewed once before any deck plans
against it, rather than sampled per-generation by a confidence heuristic
that no longer exists (`generation/service.py`'s module docstring).
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from ..auth.principal import Principal
from ..core.errors import NotFoundError, ValidationError
from ..generation.repository import GenerationRepository
from ..generation.service import GenerationService
from ..models import Generation, GenerationStatus
from ..schemas.generation import (
    ArtifactAvailability,
    GenerationCreate,
    GenerationResponse,
)
from ..storage.object_store import ObjectStore
from ..tenancy.rbac import require_author, require_viewer
from .deps import (
    get_generation_repository,
    get_generation_service,
    get_object_store,
)

router = APIRouter(tags=["generations"])

# Provenance knobs safe to expose. The bulky generated content stays server-side.
_PUBLIC_PARAM_KEYS = frozenset({"tone", "verbosity", "n_slides", "language", "export_as"})

_ARTIFACT_MEDIA_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}


def _public_params(params: dict | None) -> dict:
    return {k: v for k, v in (params or {}).items() if k in _PUBLIC_PARAM_KEYS}


def _artifacts(g: Generation) -> ArtifactAvailability:
    return ArtifactAvailability(pptx=bool(g.pptx_uri), pdf=bool(g.pdf_uri))


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
        artifacts=_artifacts(g),
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
) -> GenerationResponse:
    generation = await service.create(
        project_id=project_id, payload=payload, created_by=principal.user_id
    )
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


@router.get("/generations/{generation_id}/download")
def download_generation(
    generation_id: uuid.UUID,
    fmt: str = Query("pptx", alias="format", pattern="^(pptx|pdf)$"),
    _: Principal = Depends(require_viewer),
    repo: GenerationRepository = Depends(get_generation_repository),
    object_store: ObjectStore = Depends(get_object_store),
) -> StreamingResponse:
    """Stream the rendered deck to the browser.

    Read fully into memory before streaming: decks are single-digit MB and the store's
    Protocol exposes `get_bytes`, not a chunked reader. Revisit if deck sizes grow.
    """
    generation = repo.get(generation_id)
    if generation.status is not GenerationStatus.ready:
        raise ValidationError("Generation is not ready for download.")

    key = generation.pptx_uri if fmt == "pptx" else generation.pdf_uri
    if not key:
        raise NotFoundError(f"No {fmt} artifact for this generation.")

    data = object_store.get_bytes(key=key)
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_ARTIFACT_MEDIA_TYPES[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="deck-{generation.id}.{fmt}"',
            "Content-Length": str(len(data)),
        },
    )
