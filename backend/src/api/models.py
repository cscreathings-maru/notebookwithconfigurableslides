"""Models router — the curated OpenRouter model list for the Studio dropdown.

Lite mode uses a single OpenRouter key with many selectable models (not full
per-provider BYOK). The list is configured via OPENROUTER_MODELS.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.principal import Principal
from ..core.config import get_settings
from ..tenancy.rbac import require_viewer

router = APIRouter(prefix="/models", tags=["models"])


class ModelOption(BaseModel):
    id: str
    default: bool


@router.get("", response_model=list[ModelOption])
def list_models(_: Principal = Depends(require_viewer)) -> list[ModelOption]:
    settings = get_settings()
    default = settings.openrouter_model
    return [
        ModelOption(id=slug, default=(slug == default))
        for slug in settings.openrouter_model_list
    ]
