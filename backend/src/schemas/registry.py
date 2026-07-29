"""Registry request/response schemas.

Engine refs (presenton_template_ref) and the stored PPTX key (source_pptx_uri) are
deliberately absent from response models — they never reach a client.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..models import RegistrationStatus, RegistryStatus, Tone, Verbosity


class ProfileWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    audience: str = Field(..., min_length=1, max_length=1000)
    template_id: uuid.UUID
    tone: Tone
    verbosity: Verbosity
    slide_min: int = Field(..., ge=1, le=200)
    slide_max: int = Field(..., ge=1, le=200)
    language: str = Field(..., min_length=2, max_length=32)
    section_structure: list[Any] = Field(default_factory=list)
    prompt_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_slide_range(self) -> "ProfileWrite":
        if self.slide_min > self.slide_max:
            raise ValueError("slide_min must be <= slide_max")
        return self


class ProfileResponse(BaseModel):
    id: uuid.UUID
    version: int
    name: str
    audience: str
    template_id: uuid.UUID
    template_version: int
    tone: Tone
    verbosity: Verbosity
    slide_min: int
    slide_max: int
    language: str
    section_structure: list[Any]
    prompt_config: dict[str, Any]
    status: RegistryStatus
    created_at: datetime


class TemplateResponse(BaseModel):
    id: uuid.UUID
    version: int
    name: str
    brand_tokens: dict[str, Any]
    status: RegistryStatus
    has_pptx: bool
    # Whether the slide engine actually accepted this template. `fallback` means decks
    # will render with the stock theme, not the uploaded branding. The engine ref itself
    # stays server-side -- this exposes the outcome, not the handle.
    registration_status: RegistrationStatus
    registration_error: str | None
    # Same-origin link to preview this template's layouts in the slide editor, or None
    # when there is nothing to preview -- the engine never accepted it. A URL, not the
    # engine's template id, for the same reason as `Generation.editor_url` (T-1.2).
    preview_url: str | None
    created_at: datetime


class ExtractedTokensResponse(BaseModel):
    status: str = "success"
    filename: str
    extracted_tokens: dict[str, Any]
    confidence_score: float = 0.95
    summary: str

