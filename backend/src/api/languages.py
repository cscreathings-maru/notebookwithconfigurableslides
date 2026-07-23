"""Languages router — the AI output language options for the Studio dropdown.

Presenton (and the guide/chat prompts) take a language NAME, not an ISO code.
Configured via DEFAULT_LANGUAGE + LANGUAGES; the default is listed first.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.principal import Principal
from ..core.config import get_settings
from ..tenancy.rbac import require_viewer

router = APIRouter(prefix="/languages", tags=["languages"])


class LanguageOption(BaseModel):
    id: str
    default: bool


@router.get("", response_model=list[LanguageOption])
def list_languages(_: Principal = Depends(require_viewer)) -> list[LanguageOption]:
    settings = get_settings()
    default = settings.default_language
    return [
        LanguageOption(id=name, default=(name == default))
        for name in settings.language_list
    ]
