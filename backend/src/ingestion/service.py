"""Ingestion services: project creation, source upload, and the ingest pipeline.

- ProjectService.create provisions an Open Notebook notebook 1:1 with the project.
- SourceService.create_source stores the upload under a tenant-prefixed key and
  enqueues an idempotent ingest job.
- ingest_source drives one source through Open Notebook to `ready` (or `failed`).
  It is idempotent (a ready source is a no-op) and resumable (a source already
  added to the engine is not re-added; transient engine errors propagate so the
  job retries instead of corrupting state).
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import EngineError, NotFoundError, ValidationError
from ..core.logging import get_logger
from ..jobs.service import JobService
from ..metering.service import MeteringService
from ..models import (
    JobType,
    Project,
    Source,
    SourceKind,
    SourceStatus,
    Tenant,
)
from ..storage.object_store import ObjectStore
from .kinds import (
    content_type_for_filename,
    is_supported_upload,
    kind_for_filename,
    supported_extensions,
)
from .repository import ProjectRepository, SourceRepository

logger = get_logger("orchestrator.ingestion")

_READY = "ready"
_FAILED = "failed"


def source_display_name(source: Source) -> str:
    """Client-safe name: the URL for url sources, else the file's basename."""
    if source.kind is SourceKind.url:
        return source.original_uri
    return source.original_uri.rsplit("/", 1)[-1]


class ProjectService:
    def __init__(self, repo: ProjectRepository, on_client):
        self.repo = repo
        self.on_client = on_client

    async def create(self, *, name: str, created_by: uuid.UUID) -> Project:
        """Create the project AND its Open Notebook notebook (atomic intent).

        The notebook is created first; only on success do we persist the project,
        so a failed engine call never leaves an orphan project without a notebook.
        """
        tenant = self.repo.db.get(Tenant, self.repo.tenant_id)
        namespace = tenant.slug if tenant else self.repo.tenant_id.hex

        notebook_id = await self.on_client.create_notebook(name=name, namespace=namespace)

        project = Project(name=name, on_notebook_id=notebook_id, created_by=created_by)
        self.repo.add(project)
        MeteringService(self.repo.db, self.repo.tenant_id).audit(
            action="project.created",
            resource={"project_id": str(project.id), "name": name},
            actor_user_id=created_by,
        )
        logger.info("project_created", extra={"project_id": str(project.id)})
        return project


class SourceService:
    def __init__(
        self,
        *,
        source_repo: SourceRepository,
        project_repo: ProjectRepository,
        object_store: ObjectStore,
        job_service: JobService,
    ):
        self.source_repo = source_repo
        self.project_repo = project_repo
        self.object_store = object_store
        self.job_service = job_service

    async def create_source(
        self,
        *,
        project_id: uuid.UUID,
        filename: str | None,
        content: bytes | None,
        url: str | None,
    ) -> Source:
        """Store the upload (file or URL) and enqueue an ingest job."""
        # Tenant-scoped existence check -> 404 across tenants.
        project = self.project_repo.get(project_id)

        if url and (filename or content):
            raise ValidationError("Provide either a file or a url, not both.")

        source_id = uuid.uuid4()
        if url:
            source = Source(
                id=source_id,
                project_id=project.id,
                kind=SourceKind.url,
                original_uri=url,
                status=SourceStatus.queued,
            )
        elif filename is not None and content is not None:
            # Reject up front rather than enqueuing a job that fails in the engine.
            # A user learns immediately instead of watching "queued" indefinitely.
            if not is_supported_upload(filename):
                raise ValidationError(
                    f"The analysis engine cannot extract text from this file type. "
                    f"Supported: {', '.join(supported_extensions())}.",
                    code="unsupported_source_type",
                )

            key = self.object_store.tenant_key(
                tenant_id=self.source_repo.tenant_id.hex,
                project_id=project.id.hex,
                source_id=source_id.hex,
                filename=filename,
            )
            # The REAL content type, not octet-stream. The engine fetches this object by
            # presigned URL and routes on the Content-Type the store serves; a generic
            # octet-stream left it unable to pick an extractor for binary formats.
            self.object_store.put_bytes(
                key=key,
                data=content,
                content_type=content_type_for_filename(filename),
            )
            source = Source(
                id=source_id,
                project_id=project.id,
                kind=kind_for_filename(filename),
                original_uri=key,
                status=SourceStatus.queued,
            )
        else:
            raise ValidationError("A file upload or a url is required.")

        self.source_repo.add(source)

        job, _ = self.job_service.create(
            job_type=JobType.ingest,
            idempotency_key=f"ingest:{source.id}",
            ref_id=source.id,
        )
        await self.job_service.commit_and_dispatch(job)
        logger.info(
            "source_queued",
            extra={"source_id": str(source.id), "kind": source.kind.value},
        )
        return source


async def ingest_source(
    *,
    db: Session,
    source_id: uuid.UUID,
    tenant_id: uuid.UUID,
    on_client,
    object_store: ObjectStore,
    provider_config: dict,
) -> None:
    """Push one source into Open Notebook and track status to ready/failed."""
    source_repo = SourceRepository(db, tenant_id)
    source = source_repo.get(source_id)  # NotFoundError (404) across tenants

    if source.status is SourceStatus.ready:
        logger.info("ingest_noop_already_ready", extra={"source_id": str(source_id)})
        return

    project_repo = ProjectRepository(db, tenant_id)
    project = project_repo.get(source.project_id)
    if not project.on_notebook_id:
        raise NotFoundError("Project has no Open Notebook notebook.")

    source.status = SourceStatus.processing
    source.error = None
    db.add(source)
    db.flush()

    # Resumable: only add the source to the engine if it isn't there yet.
    #
    # Files are UPLOADED, not linked. A presigned object-store URL sent as a "link"
    # hits the engine's web-page extractor, which rejects binaries before processing
    # starts; it also expires (short TTL), so the engine's own retry could never
    # recover a source. Uploading the bytes removes both problems.
    if not source.on_source_id:
        if source.kind is SourceKind.url:
            source.on_source_id = await on_client.add_source_link(
                notebook_id=project.on_notebook_id,
                url=source.original_uri,
            )
        else:
            filename = source.original_uri.rsplit("/", 1)[-1]
            source.on_source_id = await on_client.add_source_file(
                notebook_id=project.on_notebook_id,
                filename=filename,
                content=object_store.get_bytes(key=source.original_uri),
                content_type=content_type_for_filename(filename),
            )
        db.add(source)
        db.flush()

    progress = await _poll_until_terminal(on_client, source.on_source_id)

    if progress.state == _FAILED:
        # Record the ENGINE's reason. A generic string here is what made a failed
        # source undiagnosable: the user saw "failed" and had nothing to act on,
        # while the engine had already said why.
        _mark_failed(
            db,
            source,
            progress.detail or "The analysis engine reported a failure with no detail.",
        )
        logger.warning(
            "ingest_source_failed",
            extra={"source_id": str(source_id), "engine_detail": progress.detail},
        )
        return

    # Ready -> derive analysis and finalize.
    source.analysis_ref = await on_client.run_transformation(
        source_id=source.on_source_id, provider_config=provider_config
    )
    source.status = SourceStatus.ready
    source.error = None
    db.add(source)
    db.flush()
    logger.info("ingest_source_ready", extra={"source_id": str(source_id)})


async def _poll_until_terminal(on_client, on_source_id: str):
    """Poll until the engine reaches a terminal state, carrying its explanation along."""
    settings = get_settings()
    last_detail: str | None = None
    for _ in range(settings.ingest_poll_max_attempts):
        progress = await on_client.get_source_status(source_id=on_source_id)
        last_detail = progress.detail or last_detail
        if progress.state in (_READY, _FAILED):
            return progress
        await asyncio.sleep(settings.ingest_poll_interval_seconds)
    # Timed out: transient — let the job retry rather than corrupting state. Include the
    # last thing the engine said, so a timeout is not a dead end either.
    raise EngineError(
        "Open Notebook analysis timed out."
        + (f" Last engine status: {last_detail}" if last_detail else "")
    )


def _mark_failed(db: Session, source: Source, message: str) -> None:
    source.status = SourceStatus.failed
    source.error = message
    db.add(source)
    db.flush()
