"""Async tasks: ingest (implemented) and generate (stub for Slice 3).

The ingest task wires real collaborators (Open Notebook client, object store, the
tenant's BYOK provider config) and delegates to the ingest_source pipeline. The DB
Job row is updated so the polling endpoint reflects movement. Transient engine
errors propagate so Arq retries (resumable); a terminal source failure is recorded
on the Source and the job completes.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core.db import SessionLocal
from ..core.errors import NotFoundError
from ..core.logging import get_logger
from ..engines.open_notebook import OpenNotebookClient
from ..ingestion.repository import SourceRepository
from ..ingestion.service import ingest_source
from ..models import Job, JobStatus, SourceStatus
from ..storage.object_store import get_object_store
from ..tenancy.llm_config import TenantLlmConfigService

logger = get_logger("orchestrator.worker")


def _load_job(db, job_id: uuid.UUID, tenant_id: uuid.UUID) -> Job | None:
    job = db.get(Job, job_id)
    # Defense in depth: never touch a job outside the dispatched tenant.
    if job is None or job.tenant_id != tenant_id:
        logger.warning("worker_job_missing", extra={"job_id": str(job_id)})
        return None
    return job


async def run_ingest(ctx: dict[str, Any], job_id: str, tenant_id: str) -> None:
    job_uuid = uuid.UUID(job_id)
    tenant_uuid = uuid.UUID(tenant_id)

    with SessionLocal() as db:
        job = _load_job(db, job_uuid, tenant_uuid)
        if job is None:
            return
        source_id = job.ref_id
        job.status = JobStatus.running
        job.attempts += 1
        job.progress = {"step": "ingesting", "percent": 10}
        db.add(job)
        db.commit()

        if source_id is None:
            _finish_job(db, job_uuid, tenant_uuid, JobStatus.failed, "Job has no source ref.")
            return

        # BYOK provider config is required for analysis; a missing config is a
        # terminal failure for this source (not a retry).
        try:
            provider_config = TenantLlmConfigService(db, tenant_uuid).get_config()
        except NotFoundError:
            _fail_source(db, source_id, tenant_uuid, "No LLM provider configured for tenant.")
            _finish_job(db, job_uuid, tenant_uuid, JobStatus.failed, "No LLM provider configured.")
            return

        try:
            await ingest_source(
                db=db,
                source_id=source_id,
                tenant_id=tenant_uuid,
                on_client=OpenNotebookClient(),
                object_store=get_object_store(),
                provider_config=provider_config,
            )
            db.commit()
        except Exception as exc:  # transient engine/transport error -> let Arq retry
            db.rollback()
            logger.warning("ingest_retryable_error", extra={"job_id": job_id, "error": str(exc)})
            raise

        _finish_job(db, job_uuid, tenant_uuid, JobStatus.succeeded, None)


def _fail_source(db, source_id: uuid.UUID, tenant_id: uuid.UUID, message: str) -> None:
    repo = SourceRepository(db, tenant_id)
    source = repo.get_or_none(source_id)
    if source is not None:
        source.status = SourceStatus.failed
        source.error = message
        db.add(source)
        db.commit()


def _finish_job(
    db, job_id: uuid.UUID, tenant_id: uuid.UUID, status: JobStatus, error: str | None
) -> None:
    job = _load_job(db, job_id, tenant_id)
    if job is None:
        return
    job.status = status
    job.error = error
    job.progress = {"step": status.value, "percent": 100}
    db.add(job)
    db.commit()


async def run_generate(ctx: dict[str, Any], job_id: str, tenant_id: str) -> None:
    from ..engines.presenton import PresentonClient
    from ..generation.worker import generate_presentation

    job_uuid = uuid.UUID(job_id)
    tenant_uuid = uuid.UUID(tenant_id)

    with SessionLocal() as db:
        job = _load_job(db, job_uuid, tenant_uuid)
        if job is None:
            return
        generation_id = job.ref_id
        job.status = JobStatus.running
        job.attempts += 1
        job.progress = {"step": "generating", "percent": 10}
        db.add(job)
        db.commit()

        if generation_id is None:
            _finish_job(db, job_uuid, tenant_uuid, JobStatus.failed, "Job has no generation ref.")
            return

        try:
            await generate_presentation(
                db=db,
                generation_id=generation_id,
                tenant_id=tenant_uuid,
                presenton=PresentonClient(),
                object_store=get_object_store(),
            )
            db.commit()
        except Exception as exc:  # transient engine/transport error -> let Arq retry
            db.rollback()
            logger.warning("generate_retryable_error", extra={"job_id": job_id, "error": str(exc)})
            raise

        _finish_job(db, job_uuid, tenant_uuid, JobStatus.succeeded, None)
