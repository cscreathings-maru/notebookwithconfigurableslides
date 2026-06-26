"""Project/Source request + response schemas.

Engine-internal ids (on_notebook_id, on_source_id) and the raw analysis_ref are
deliberately absent from every response model — they never reach a client.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from ..models import SourceKind, SourceStatus


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class SourceResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: SourceKind
    name: str
    status: SourceStatus
    error: str | None = None
    created_at: datetime
