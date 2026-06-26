"""Registry request/response schemas.

Engine refs (presenton_template_ref) and the stored PPTX key (source_pptx_uri) are
deliberately absent from response models — they never reach a client.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..models import RegistryStatus, Tone, Verbosity


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
    created_at: datetime
