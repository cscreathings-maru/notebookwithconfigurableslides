"""NotebookGuide response schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from ..models import GuideStatus


class GuideRegenerate(BaseModel):
    # AI output language NAME (e.g. "Bahasa Indonesia"); None → server default.
    language: str | None = None


class GuideResponse(BaseModel):
    project_id: uuid.UUID
    summary: str | None
    suggested_questions: list[str]
    status: GuideStatus
    error: str | None = None
    updated_at: datetime
