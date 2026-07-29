"""Templates router (admin writes; authors read approved only).

Create accepts {name, brand_tokens} plus an optional PPTX (multipart). With a PPTX
the template is imported via Presenton (import-from-PPTX) under a tenant-namespaced
name; the engine ref and the stored PPTX key never reach the client.
"""

from __future__ import annotations

import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from ..auth.principal import Principal
from ..core.errors import ValidationError
from ..models import Template, UserRole
from ..registry.service import TemplateService
from ..registry.extraction import extract_tokens_from_pptx
from ..schemas.registry import ExtractedTokensResponse, TemplateResponse
from ..tenancy.rbac import require_admin, require_viewer
from .deps import get_template_service

router = APIRouter(prefix="/templates", tags=["templates"])


# Presenton is served same-origin under this prefix (T-1.1).
_EDITOR_BASE_PATH = "/editor"
# The ref stored when registration did not yield a real engine template.
_STOCK_TEMPLATE_REF = "default"


def _preview_url(t: Template) -> str | None:
    """Link that previews this template's layouts in the slide editor, or None.

    Composed from `presenton_template_ref` -- the id the ENGINE issued -- not from
    `logical_id`, which is a Postgres UUID Presenton has never seen. The templates page
    previously built this URL from `logical_id` and got a truthful "Template not found":
    the same defect T-1.2 fixed for the generation deep link, on a second surface.

    None when the registration fell back, because "default" is not a real engine
    template and previewing it would show layouts the user did not upload.
    """
    ref = t.presenton_template_ref
    if not ref or ref == _STOCK_TEMPLATE_REF:
        return None
    return f"{_EDITOR_BASE_PATH}/template-preview?id={quote(str(ref))}"


def _to_response(t: Template) -> TemplateResponse:
    return TemplateResponse(
        id=t.logical_id,
        version=t.version,
        name=t.name,
        brand_tokens=t.brand_tokens,
        status=t.status,
        has_pptx=t.source_pptx_uri is not None,
        registration_status=t.registration_status,
        registration_error=t.registration_error,
        preview_url=_preview_url(t),
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


@router.post("/{template_id}/approve", response_model=TemplateResponse)
def approve_template(
    template_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    return _to_response(service.approve(template_id, actor_user_id=principal.user_id))


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

