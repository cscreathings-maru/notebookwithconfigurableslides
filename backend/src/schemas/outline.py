"""Outline API schemas. The content is the structure contract (no engine ids).

Governed path: `profile_id`. Freeform path (DG-1): `content_source` + the same
knobs freeform generation already exposes (tone/density/language), plus an optional
`n_slides_hint` -- a hint the model may not hit exactly, not a contract the way
`n_slides` is on the governed/freeform-generation payloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..models import Tone, Verbosity

ContentSource = Literal["summary", "notebook", "chat", "custom"]


class OutlineCreate(BaseModel):
    # Governed path.
    profile_id: uuid.UUID | None = None

    # Freeform path.
    content_source: ContentSource | None = None
    custom_markdown: str | None = None
    chat_message_id: uuid.UUID | None = None
    tone: Tone = Tone.default
    density: Verbosity = Verbosity.standard
    n_slides_hint: int | None = Field(default=None, ge=1, le=40)
    # AI output language NAME (e.g. "Bahasa Indonesia"); None -> server default.
    language: str | None = None


class OutlineUpdate(BaseModel):
    content: dict[str, Any]


class OutlineResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    # Null for a freeform outline (DG-1) -- there is no profile to pin.
    profile_id: uuid.UUID | None
    profile_version: int | None
    schema_version: str
    content: dict[str, Any]
    valid: bool
    created_at: datetime
