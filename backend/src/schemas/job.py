"""Job polling schema (GET /api/v1/jobs/{id})."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from ..models import JobStatus, JobType


class JobResponse(BaseModel):
    id: uuid.UUID
    type: JobType
    status: JobStatus
    progress: dict[str, Any]
    attempts: int
