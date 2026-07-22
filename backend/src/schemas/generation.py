"""Generation API schemas.

Engine ids/paths (presenton_presentation_id, pptx_uri/pdf_uri, params) are never
exposed; clients see status, the consistency report, provenance, and whether
artifacts exist (downloaded via a signed URL endpoint).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..models import GenerationStatus, Tone, Verbosity

ContentSource = Literal["summary", "notebook", "chat", "custom"]


class GenerationCreate(BaseModel):
    """Deck request.

    Governed path: provide `outline_id` (existing profile/outline pipeline).
    Freeform path (NotebookLM Studio): provide `content_source` + config below.
    """

    # Governed path.
    outline_id: uuid.UUID | None = None

    # Freeform path.
    content_source: ContentSource | None = None
    custom_markdown: str | None = None
    chat_message_id: uuid.UUID | None = None
    tone: Tone = Tone.default
    density: Verbosity = Verbosity.standard
    n_slides: int = Field(default=8, ge=1, le=40)
    template_id: uuid.UUID | None = None
    web_search: bool = False
    model: str | None = None
    export_as: Literal["pptx", "pdf"] = "pptx"


class ArtifactAvailability(BaseModel):
    pptx: bool
    pdf: bool


class GenerationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    outline_id: uuid.UUID | None
    status: GenerationStatus
    profile_version: int | None
    template_version: int | None
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
