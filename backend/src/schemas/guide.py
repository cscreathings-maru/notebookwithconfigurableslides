"""NotebookGuide response schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from ..models import GuideStatus


class GuideResponse(BaseModel):
    project_id: uuid.UUID
    summary: str | None
    suggested_questions: list[str]
    status: GuideStatus
    error: str | None = None
    updated_at: datetime
