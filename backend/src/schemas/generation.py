"""Generation API schemas.

Engine ids/paths (presenton_presentation_id, pptx_uri/pdf_uri, params) are never
exposed; clients see status, the consistency report, provenance, and whether
artifacts exist (downloaded via a signed URL endpoint).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..models import GenerationStatus


class GenerationCreate(BaseModel):
    outline_id: uuid.UUID


class ArtifactAvailability(BaseModel):
    pptx: bool
    pdf: bool


class GenerationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    outline_id: uuid.UUID | None
    status: GenerationStatus
    profile_version: int
    template_version: int
    model: str | None
    provider: str | None
    # Sanitized provenance of what was sent to Presenton (engine template ref and
    # bulky generated content are stripped — only the governing knobs remain).
    params: dict[str, Any]
    source_ids: list[Any]
    consistency_report: dict[str, Any] | None
    artifacts: ArtifactAvailability
    error: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class DownloadResponse(BaseModel):
    format: str
    url: str
    expires_in: int
