"""Outline API schemas. The content is the structure contract (no engine ids)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OutlineCreate(BaseModel):
    profile_id: uuid.UUID


class OutlineUpdate(BaseModel):
    content: dict[str, Any]


class OutlineResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    profile_id: uuid.UUID
    profile_version: int
    schema_version: str
    content: dict[str, Any]
    valid: bool
    created_at: datetime
