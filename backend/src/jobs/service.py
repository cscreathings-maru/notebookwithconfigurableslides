"""Job service: enqueue with idempotency, track attempts/progress.

Enqueue is idempotent per tenant: re-submitting the same idempotency_key returns the
existing job instead of creating a duplicate. The Arq task is dispatched via the
shared Redis pool; the DB row is the durable source of truth for polling.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core.logging import get_logger
from ..models import Job, JobStatus, JobType
from .repository import JobRepository

logger = get_logger("orchestrator.jobs")

# Arq function names dispatched by type. The worker registers matching coroutines.
_TASK_BY_TYPE: dict[JobType, str] = {
    JobType.ingest: "run_ingest",
    JobType.generate: "run_generate",
}


class JobService:
    def __init__(self, repo: JobRepository, enqueuer: Any | None = None):
        # `enqueuer` is an Arq redis pool (or any object exposing enqueue_job).
        self.repo = repo
        self.enqueuer = enqueuer

    def create(
        self,
        *,
        job_type: JobType,
        idempotency_key: str,
        ref_id: uuid.UUID | None = None,
    ) -> tuple[Job, bool]:
        """Create or return an existing job. Returns (job, created)."""
        existing = self.repo.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "job_enqueue_idempotent_hit",
                extra={"job_id": str(existing.id), "idempotency_key": idempotency_key},
            )
            return existing, False

        job = Job(
            type=job_type,
            ref_id=ref_id,
            status=JobStatus.queued,
            attempts=0,
            idempotency_key=idempotency_key,
            progress={"step": "queued", "percent": 0},
        )
        self.repo.add(job)
        logger.info(
            "job_enqueued",
            extra={"job_id": str(job.id), "type": job_type.value},
        )
        return job, True

    async def dispatch(self, job: Job) -> None:
        """Hand the job to the async worker tier (no-op if no enqueuer wired)."""
        if self.enqueuer is None:
            logger.warning("job_dispatch_skipped_no_enqueuer", extra={"job_id": str(job.id)})
            return
        task_name = _TASK_BY_TYPE[job.type]
        await self.enqueuer.enqueue_job(
            task_name,
            str(job.id),
            str(job.tenant_id),
            _job_unique_id=job.idempotency_key,
        )
