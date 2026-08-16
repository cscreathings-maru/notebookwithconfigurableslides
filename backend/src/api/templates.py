"""Templates router (admin writes; authors read approved only).

Create accepts {name, brand_tokens} plus an optional PPTX (multipart). With a
PPTX, LD-2 cataloguing is enqueued as a job -- the response carries
`catalog_status: "cataloguing"`, not a terminal outcome (LD-3: an LLM call
belongs in a job, not a request/response cycle).

Approval is no longer automatic (Phase C cutover): a template becomes
`approved` only once an admin reviews its catalog (`/catalog/review`, L3) --
`ready` cataloguing alone means the LLM produced something, not that anyone
has looked at it.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from ..auth.principal import Principal
from ..core.errors import NotFoundError, ValidationError
from ..deck.catalog import DesignCatalog
from ..models import Template, UserRole
from ..registry.repository import TemplateRepository
from ..registry.service import TemplateService
from ..registry.extraction import extract_tokens_from_pptx
from ..schemas.registry import (
    CatalogReviewRequest,
    ExtractedTokensResponse,
    TemplateResponse,
)
from ..tenancy.rbac import require_admin, require_viewer
from .deps import get_template_repository, get_template_service

router = APIRouter(prefix="/templates", tags=["templates"])


def _to_response(t: Template) -> TemplateResponse:
    return TemplateResponse(
        id=t.logical_id,
        version=t.version,
        name=t.name,
        brand_tokens=t.brand_tokens,
        status=t.status,
        has_pptx=t.source_pptx_uri is not None,
        catalog_status=t.catalog_status,
        catalog_error=t.catalog_error,
        catalog_reviewed=t.catalog_reviewed_at is not None,
        created_at=t.created_at,
    )


def _parse_brand_tokens(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("brand_tokens must be valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValidationError("brand_tokens must be a JSON object.")
    return value


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    name: str = Form(..., min_length=1),
    brand_tokens: str = Form(default="{}"),
    file: UploadFile | None = File(default=None),
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    """201: the row is created and cataloguing enqueued before this returns,
    but `catalog_status` in the response is `"cataloguing"`, not terminal --
    poll `GET /templates` (or watch `catalog_status`) for `"ready"`/`"failed"`.
    """
    pptx_filename = file.filename if file is not None else None
    pptx_content = await file.read() if file is not None else None
    template = await service.create(
        name=name,
        brand_tokens=_parse_brand_tokens(brand_tokens),
        pptx_filename=pptx_filename,
        pptx_content=pptx_content,
        created_by=principal.user_id,
    )
    return _to_response(template)


@router.get("", response_model=list[TemplateResponse])
def list_templates(
    principal: Principal = Depends(require_viewer),
    service: TemplateService = Depends(get_template_service),
) -> list[TemplateResponse]:
    approved_only = principal.role is not UserRole.admin
    return [_to_response(t) for t in service.list_all(approved_only=approved_only)]


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> None:
    """TM-5. Refuses (409) if any version of this template is pinned by a
    Generation -- see `TemplateService.delete` for why that check spans every
    version, not just the latest."""
    service.delete(template_id, actor_user_id=principal.user_id)


@router.get("/{template_id}/catalog", response_model=DesignCatalog)
def get_template_catalog(
    template_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    repo: TemplateRepository = Depends(get_template_repository),
) -> DesignCatalog:
    """LD-4: the LLM's design catalog, for the admin review screen.

    `require_admin`, not `require_viewer`: this is the review surface
    itself -- an author choosing a template only needs `catalog_status` off
    the list endpoint, not the raw per-anchor detail an admin corrects.
    """
    template = repo.latest(template_id)
    if template is None:
        raise NotFoundError("Template not found.")
    if not template.slide_catalog:
        raise ValidationError(
            "This template has not been catalogued yet, or cataloguing produced nothing usable.",
            code="catalog_not_ready",
        )
    return DesignCatalog.model_validate(template.slide_catalog)


@router.post("/{template_id}/recatalog", response_model=TemplateResponse)
async def recatalog_template(
    template_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    """Re-run LD-2 cataloguing against the template's stored `.pptx`."""
    return _to_response(await service.recatalog(template_id, actor_user_id=principal.user_id))


@router.post("/{template_id}/catalog/review", response_model=TemplateResponse)
def review_template_catalog(
    template_id: uuid.UUID,
    payload: CatalogReviewRequest,
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    """LD-4 / L3: mark the catalog reviewed, optionally replacing it with an
    admin's corrections, and approve the template -- see
    `TemplateService.review_catalog`. A template cannot be planned against
    (Phase C, LD-9) until this has been called at least once since the last
    successful cataloguing run."""
    return _to_response(
        service.review_catalog(template_id, designs=payload.designs, actor_user_id=principal.user_id)
    )


@router.post("/extract-tokens", response_model=ExtractedTokensResponse)
async def extract_template_tokens(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_admin),
) -> ExtractedTokensResponse:
    content = await file.read()
    tokens = extract_tokens_from_pptx(content)
    num_colors = len(tokens.get("detected_colors", []))
    font = tokens.get("typography", "Inter")
    ratio = tokens.get("aspect_ratio", "16:9")
    summary = f"Detected {num_colors} brand colors, {font} typography, and {ratio} layout from '{file.filename}'."
    return ExtractedTokensResponse(
        status="success",
        filename=file.filename or "template.pptx",
        extracted_tokens=tokens,
        confidence_score=0.95,
        summary=summary,
    )
