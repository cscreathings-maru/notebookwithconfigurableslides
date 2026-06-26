"""Jobs router — GET /api/v1/jobs/{id} for polling ingest/generate work.

Tenant-scoped: a job belonging to another tenant is not found -> 404 (no leak).
Any authenticated role may poll a job in its own tenant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ..jobs.repository import JobRepository
from ..schemas.job import JobResponse
from ..tenancy.rbac import require_viewer
from .deps import get_job_repository

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_viewer)])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: uuid.UUID,
    repo: JobRepository = Depends(get_job_repository),
) -> JobResponse:
    job = repo.get(job_id)  # raises NotFoundError (404) across tenants
    return JobResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        attempts=job.attempts,
    )
