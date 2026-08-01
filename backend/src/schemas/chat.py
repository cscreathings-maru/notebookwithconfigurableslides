"""Chat request + response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from ..models import ChatRole
from ..models.chat import TITLE_MAX_CHARS


class ChatAsk(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    # AI response language NAME (e.g. "Bahasa Indonesia"); None → server default.
    language: str | None = None
    # Which thread to answer in; None → the project's most recent session.
    session_id: uuid.UUID | None = None


class Citation(BaseModel):
    source_ref: str | None = None
    snippet: str


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: ChatRole
    content: str
    citations: list[Citation] = []
    created_at: datetime


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_MAX_CHARS)


class ChatSessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=TITLE_MAX_CHARS)


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    # Null until the first question names it. Clients render their own placeholder
    # rather than the server inventing one in a language it does not own.
    title: str | None = None
    created_at: datetime
    updated_at: datetime
