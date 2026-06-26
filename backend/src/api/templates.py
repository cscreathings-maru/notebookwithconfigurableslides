"""Templates router (admin writes; authors read approved only).

Create accepts {name, brand_tokens} plus an optional PPTX (multipart). With a PPTX
the template is imported via Presenton (import-from-PPTX) under a tenant-namespaced
name; the engine ref and the stored PPTX key never reach the client.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from ..auth.dependencies import get_current_principal
from ..auth.principal import Principal
from ..core.errors import ValidationError
from ..models import Template, UserRole
from ..registry.service import TemplateService
from ..schemas.registry import TemplateResponse
from ..tenancy.rbac import require_admin, require_viewer
from .deps import get_template_service

router = APIRouter(prefix="/templates", tags=["templates"])


def _to_response(t: Template) -> TemplateResponse:
    return TemplateResponse(
        id=t.logical_id,
        version=t.version,
        name=t.name,
        brand_tokens=t.brand_tokens,
        status=t.status,
        has_pptx=t.source_pptx_uri is not None,
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
