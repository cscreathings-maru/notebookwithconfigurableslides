"""Chat request + response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from ..models import ChatRole


class ChatAsk(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    # AI response language NAME (e.g. "Bahasa Indonesia"); None → server default.
    language: str | None = None


class Citation(BaseModel):
    source_ref: str | None = None
    snippet: str


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: ChatRole
    content: str
    citations: list[Citation] = []
    created_at: datetime
