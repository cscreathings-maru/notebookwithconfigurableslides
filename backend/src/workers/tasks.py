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
from ..core.errors import NotFoundError, ValidationError
from ..core.logging import get_logger
from ..engines.open_notebook import OpenNotebookClient
from ..ingestion.repository import SourceRepository
from ..ingestion.service import ingest_source
from ..models import Job, JobStatus, SourceStatus
from ..storage.object_store import get_object_store
from ..tenancy.llm_config import TenantLlmConfigService

logger = get_logger("orchestrator.worker")


class JobRowMissing(RuntimeError):
    """A dispatched job's row is not visible to the worker.

    Raised rather than returned so Arq retries. Returning quietly is what let the
    enqueue-before-commit race strand generations at `queued` with no diagnostic.
    """


def _load_job(db, job_id: uuid.UUID, tenant_id: uuid.UUID) -> Job | None:
    """Quiet lookup, for paths where an absent row is not itself the failure."""
    job = db.get(Job, job_id)
    # Defense in depth: never touch a job outside the dispatched tenant.
    if job is None or job.tenant_id != tenant_id:
        logger.warning("worker_job_missing", extra={"job_id": str(job_id)})
        return None
    return job


def _require_job(db, job_id: uuid.UUID, tenant_id: uuid.UUID) -> Job:
    """Load the dispatched job, or fail loudly so Arq retries."""
    job = _load_job(db, job_id, tenant_id)
    if job is None:
        logger.error(
            "worker_job_row_absent",
            extra={"job_id": str(job_id), "tenant_id": str(tenant_id)},
        )
        raise JobRowMissing(f"Job {job_id} was dispatched but its row is not visible.")
    return job


async def run_ingest(ctx: dict[str, Any], job_id: str, tenant_id: str, *args: Any, **kwargs: Any) -> None:
    job_uuid = uuid.UUID(job_id)
    tenant_uuid = uuid.UUID(tenant_id)

    with SessionLocal() as db:
        job = _require_job(db, job_uuid, tenant_uuid)
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


async def run_catalog_template(
    ctx: dict[str, Any], job_id: str, tenant_id: str, *args: Any, **kwargs: Any
) -> None:
    """LD-3: `deck/dump.py` -> `deck/catalog.py::catalog_template` -> `Template.slide_catalog`.

    Mirrors `run_ingest`'s shape: the engine client (here `LlmClient`) is
    constructed directly, not via FastAPI DI, since Arq tasks run outside the
    request/response cycle. A malformed-content outcome (`ValidationError` --
    e.g. no usable design in the whole template) is TERMINAL and recorded on
    the row; anything else (a transient LLM/network failure) propagates so
    Arq retries, matching `run_ingest`'s own transient-vs-terminal split.
    """
    from ..deck.catalog import catalog_template
    from ..deck.dump import dump_presentation
    from ..engines.llm import LlmClient
    from ..registry.repository import TemplateRepository
    from ..registry.service import apply_catalog_result

    job_uuid = uuid.UUID(job_id)
    tenant_uuid = uuid.UUID(tenant_id)

    with SessionLocal() as db:
        job = _require_job(db, job_uuid, tenant_uuid)
        template_row_id = job.ref_id
        job.status = JobStatus.running
        job.attempts += 1
        job.progress = {"step": "cataloguing", "percent": 10}
        db.add(job)
        db.commit()

        if template_row_id is None:
            _finish_job(db, job_uuid, tenant_uuid, JobStatus.failed, "Job has no template ref.")
            return

        template = TemplateRepository(db, tenant_uuid).get_or_none(template_row_id)
        if template is None or not template.source_pptx_uri:
            _finish_job(
                db, job_uuid, tenant_uuid, JobStatus.failed, "Template row or its .pptx is missing."
            )
            return

        llm_config = TenantLlmConfigService(db, tenant_uuid)
        try:
            provider_config = llm_config.get_config()
        except NotFoundError:
            apply_catalog_result(template, catalog=None, error="No LLM provider configured for tenant.")
            db.add(template)
            db.commit()
            _finish_job(db, job_uuid, tenant_uuid, JobStatus.failed, "No LLM provider configured.")
            return

        pptx_bytes = get_object_store().get_bytes(key=template.source_pptx_uri)
        dumps = dump_presentation(pptx_bytes)

        try:
            catalog, usage = await catalog_template(
                dumps=dumps,
                llm=LlmClient(),
                provider_config=provider_config,
                model_override=llm_config.model_for("deck_catalog"),
            )
        except ValidationError as exc:
            apply_catalog_result(template, catalog=None, error=str(exc))
            db.add(template)
            db.commit()
            _finish_job(db, job_uuid, tenant_uuid, JobStatus.failed, str(exc))
            return
        except Exception as exc:  # transient engine/transport error -> let Arq retry
            db.rollback()
            logger.warning("catalog_template_retryable_error", extra={"job_id": job_id, "error": str(exc)})
            raise

        apply_catalog_result(template, catalog=catalog, error=None)
        db.add(template)
        db.commit()
        logger.info(
            "catalog_template_finished",
            extra={"template_id": str(template.logical_id), "tokens_in": usage.tokens_in, "tokens_out": usage.tokens_out},
        )
        _finish_job(db, job_uuid, tenant_uuid, JobStatus.succeeded, None)


async def run_generate(ctx: dict[str, Any], job_id: str, tenant_id: str, *args: Any, **kwargs: Any) -> None:
    from ..generation.worker import generate_presentation

    job_uuid = uuid.UUID(job_id)
    tenant_uuid = uuid.UUID(tenant_id)

    with SessionLocal() as db:
        job = _require_job(db, job_uuid, tenant_uuid)
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
                object_store=get_object_store(),
            )
            db.commit()
        except Exception as exc:  # transient storage/transport error -> let Arq retry
            db.rollback()
            logger.warning("generate_retryable_error", extra={"job_id": job_id, "error": str(exc)})
            raise

        _finish_job(db, job_uuid, tenant_uuid, JobStatus.succeeded, None)
