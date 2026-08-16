"""Registry request/response schemas.

The stored PPTX key (source_pptx_uri) is deliberately absent from response
models — it never reaches a client.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..models import RegistryStatus, TemplateCatalogStatus, Tone, Verbosity


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
    # LD-3: the LLM cataloguing job's own lifecycle
    # (`models/registry.py::TemplateCatalogStatus`).
    catalog_status: TemplateCatalogStatus
    catalog_error: str | None
    # LD-4: whether an admin has reviewed (and possibly corrected) the
    # catalog since it was last produced. Also gates `status == approved`
    # (`TemplateService.review_catalog`).
    catalog_reviewed: bool
    created_at: datetime


class CatalogReviewRequest(BaseModel):
    """LD-4: submit a correction to the LLM's catalog, or an empty body to
    approve it unchanged. `designs`, when present, replaces the stored
    catalog wholesale -- see `TemplateService.review_catalog`."""

    designs: list[dict[str, Any]] | None = None


class ExtractedTokensResponse(BaseModel):
    status: str = "success"
    filename: str
    extracted_tokens: dict[str, Any]
    confidence_score: float = 0.95
    summary: str

