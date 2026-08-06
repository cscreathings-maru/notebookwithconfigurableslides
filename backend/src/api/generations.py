"""Generations router — enqueue, poll status/report, list history, artifact download.

Engine ids/paths stay server-side. Deck bytes are streamed through this process rather
than presigned: MinIO is reachable only on the internal Docker network, so a presigned
URL names a host (`http://minio:9000`) that no browser can resolve. Streaming keeps the
artifact behind the existing tenant + RBAC guards and adds no new public surface.
"""

from __future__ import annotations

import io
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from ..auth.principal import Principal
from ..core.errors import NotFoundError, ValidationError
from ..generation.freeform_service import FreeformGenerationService
from ..generation.repository import GenerationRepository
from ..generation.service import GenerationService
from ..models import Generation, GenerationStatus
from ..models.base import utcnow
from ..outline.repository import OutlineRepository
from ..schemas.generation import (
    ArtifactAvailability,
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
    get_outline_repository,
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


# Presenton is served same-origin under this prefix (T-1.1). Kept here so the URL
# shape is defined in exactly one place.
_EDITOR_BASE_PATH = "/editor"

_ARTIFACT_MEDIA_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}


def _public_params(params: dict | None) -> dict:
    return {k: v for k, v in (params or {}).items() if k in _PUBLIC_PARAM_KEYS}


def _editor_url(g: Generation) -> str | None:
    """Same-origin link that opens this deck in Presenton, or None.

    The route is `/presentation` with the id as a **query parameter** — verified from
    `app-path-routes-manifest.json` in the published engine image, where
    `/(presentation-generator)/presentation/page` maps to a static `/presentation` with
    no dynamic segment. A path form like `/presentation/{id}` does not exist.

    The engine id itself never reaches the client: `_PUBLIC_PARAM_KEYS` strips it from
    `params`, and there is no field for it on the response. This composes the URL
    server-side so the invariant holds while the button still works.
    """
    if not g.presenton_presentation_id:
        return None
    return f"{_EDITOR_BASE_PATH}/presentation?id={quote(str(g.presenton_presentation_id))}"


def _artifacts(g: Generation) -> ArtifactAvailability:
    # DG-4: once the studio has been opened, the stored artifact can no longer be
    # trusted to match what the user sees there -- editing there updates only the
    # engine's own copy (TD-24). Reporting it as still downloadable would be
    # exactly the silent-wrong-answer shape this codebase has a standing rule
    # against, so it stops being offered rather than staying technically present
    # but stale.
    if g.studio_opened_at is not None:
        return ArtifactAvailability(pptx=False, pdf=False)
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
        editor_url=_editor_url(g),
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
    outline_repo: OutlineRepository = Depends(get_outline_repository),
) -> GenerationResponse:
    # Three branches on one endpoint -- kept in one place for the reason
    # docs/ARCHITECTURE.md §3 names this endpoint as the codebase's recurring
    # divergence point: content_source selects freeform outright; outline_id is
    # then split on whether the referenced Outline is governed (has a pinned
    # profile) or freeform (DG-1's ungoverned outline, profile_id is None) --
    # the latter generates through the freeform service too (DG-2), not a third.
    if payload.content_source is not None:
        generation = await freeform_service.create(
            project_id=project_id, payload=payload, created_by=principal.user_id
        )
    elif payload.outline_id is not None:
        outline = outline_repo.get(payload.outline_id)  # 404 across tenants
        if outline.profile_id is not None:
            generation = await service.create(
                project_id=project_id,
                outline_id=payload.outline_id,
                created_by=principal.user_id,
            )
        else:
            generation = await freeform_service.create_from_outline(
                project_id=project_id,
                outline=outline,
                payload=payload,
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


@router.post("/generations/{generation_id}/studio-opened", response_model=GenerationResponse)
def mark_studio_opened(
    generation_id: uuid.UUID,
    _: Principal = Depends(require_author),
    repo: GenerationRepository = Depends(get_generation_repository),
) -> GenerationResponse:
    """DG-4: the frontend calls this right before navigating to "Open in Studio".

    Idempotent -- a generation whose studio was already opened keeps its original
    timestamp rather than sliding forward on every subsequent open. `require_author`
    (not `require_viewer`, the bar `get_generation`/`download_generation` use): this
    has a real consequence for every viewer of this generation, not just the caller,
    so it takes the same authority level as creating the generation did.
    """
    generation = repo.get(generation_id)
    if generation.studio_opened_at is None:
        generation.studio_opened_at = utcnow()
        repo.db.add(generation)
        repo.db.flush()
    return _to_response(generation)


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
    if generation.studio_opened_at is not None:
        # DG-4 (Q6, Option C): enforced here too, not just by hiding the button --
        # a stale stored artifact behind a still-live endpoint is exactly the
        # silent-wrong-answer shape TD-24 described. The client-side hide is a
        # convenience; this is the guarantee.
        raise ValidationError(
            "This deck has been opened for editing in the studio; download it from "
            "there instead — the copy stored here may be out of date.",
            code="edited_in_studio",
        )

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
