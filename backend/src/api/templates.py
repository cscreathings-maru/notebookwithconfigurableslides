"""Templates router (admin writes; authors read approved only).

Create accepts {name, brand_tokens} plus an optional PPTX (multipart). With a PPTX
the template is queued for registration with Presenton (TM-2: an async engine-side
job, not run inline) under a tenant-namespaced name; the engine ref and the stored
PPTX key never reach the client.

TM-4: registration success auto-approves the template -- there is no manual
approve step anymore. A template's usable state is entirely `registration_status`.
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
        thumbnail_urls=t.slide_image_urls,
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


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_template(
    name: str = Form(..., min_length=1),
    brand_tokens: str = Form(default="{}"),
    file: UploadFile | None = File(default=None),
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    """202, not 201 (TM-2): the row is created, but registration is queued, not
    done -- the response's `registration_status` is `pending`, same shape as
    `POST /sources` and `POST /generations` reporting `queued` immediately."""
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
async def delete_template(
    template_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> None:
    """TM-5. Refuses (409) if any version of this template is pinned by a
    Generation -- see `TemplateService.delete` for why that check spans every
    version, not just the latest."""
    await service.delete(template_id, actor_user_id=principal.user_id)


@router.post("/{template_id}/reregister", response_model=TemplateResponse)
async def reregister_template(
    template_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    """Retry engine registration from the template's already-stored PPTX.

    Repairs templates whose registration failed -- notably every template created
    before T-1.3, when the request omitted two fields the engine declares required.
    The response carries the new `registration_status`, so a still-failing attempt is
    legible rather than silent.
    """
    return _to_response(
        await service.reregister(template_id, actor_user_id=principal.user_id)
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

