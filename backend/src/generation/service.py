"""Generation service: create a generation (with provenance) and enqueue the job.

Blocks (409) if any source is not ready. Pins the exact profile/template versions
from the outline, builds the Presenton params up front (deterministic), stores full
provenance, and meters the action.
"""

from __future__ import annotations

import uuid

from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.logging import get_logger
from ..ingestion.repository import SourceRepository
from ..jobs.service import JobService
from ..metering.alerts import AlertSink
from ..metering.quota import QuotaService
from ..metering.service import MeteringService
from ..models import Generation, GenerationStatus, JobType, SourceStatus
from ..outline.repository import OutlineRepository
from ..outline.schema import OutlineContent
from ..registry.repository import ProfileRepository, TemplateRepository
from ..tenancy.llm_config import TenantLlmConfigService
from .mapper import build_presenton_request
from .repository import GenerationRepository

logger = get_logger("orchestrator.generation")


class SourcesNotReadyError(ConflictError):
    code = "sources_not_ready"


class NoReadySourcesError(ConflictError):
    code = "no_ready_sources"


class GenerationService:
    def __init__(
        self,
        *,
        gen_repo: GenerationRepository,
        outline_repo: OutlineRepository,
        source_repo: SourceRepository,
        profile_repo: ProfileRepository,
        template_repo: TemplateRepository,
        job_service: JobService,
        alert_sink: AlertSink,
    ):
        self.gen_repo = gen_repo
        self.outline_repo = outline_repo
        self.source_repo = source_repo
        self.profile_repo = profile_repo
        self.template_repo = template_repo
        self.job_service = job_service
        self.alert_sink = alert_sink

    async def create(
        self, *, project_id: uuid.UUID, outline_id: uuid.UUID, created_by: uuid.UUID
    ) -> Generation:
        outline = self.outline_repo.get(outline_id)
        if outline.project_id != project_id:
            raise NotFoundError("Outline not found for this project.")
        if not outline.valid:
            raise ValidationError("Outline is not valid; fix it before generating.")

        # Source readiness policy (spec FR-003 + edge case):
        #   - block while any source is still being analyzed (no partial deck),
        #   - proceed from the sources that are ready, skipping ones that FAILED to
        #     ingest, and surface a warning rather than blocking forever,
        #   - block if nothing is ready (there is nothing to build from).
        sources = self.source_repo.list_by_project(project_id)
        in_progress = [
            s
            for s in sources
            if s.status in (SourceStatus.queued, SourceStatus.processing)
        ]
        if in_progress:
            raise SourcesNotReadyError(
                f"{len(in_progress)} source(s) are still being analyzed; wait for analysis to finish."
            )
        ready_sources = [s for s in sources if s.status is SourceStatus.ready]
        if not ready_sources:
            raise NoReadySourcesError(
                "No sources are ready; upload a source and wait for analysis before generating."
            )
        skipped_failed = [s for s in sources if s.status is SourceStatus.failed]
        if skipped_failed:
            logger.warning(
                "generation_skips_failed_sources",
                extra={
                    "project_id": str(project_id),
                    "skipped_source_ids": [str(s.id) for s in skipped_failed],
                },
            )

        profile = self.profile_repo.get_version(outline.profile_id, outline.profile_version)
        if profile is None:
            raise NotFoundError("Pinned profile version not found.")
        template = self.template_repo.get_version(
            profile.template_id, profile.template_version
        )
        if template is None:
            raise NotFoundError("Pinned template version not found.")

        # Quota gate: block (or flag) when the monthly cap is reached. Runs before
        # any row is written so a blocked attempt doesn't consume quota.
        QuotaService(self.gen_repo.db, self.gen_repo.tenant_id).enforce(
            actor_user_id=created_by, alert_sink=self.alert_sink
        )

        provider_config = TenantLlmConfigService(
            self.gen_repo.db, self.gen_repo.tenant_id
        ).get_config()

        params = build_presenton_request(
            profile=profile, template=template, outline=OutlineContent(**outline.content)
        )

        generation = Generation(
            project_id=project_id,
            outline_id=outline.id,
            profile_id=outline.profile_id,
            profile_version=outline.profile_version,
            template_id=profile.template_id,
            template_version=profile.template_version,
            source_ids=[str(s.id) for s in ready_sources],
            model=provider_config.get("model"),
            provider=provider_config.get("provider"),
            params=params,
            status=GenerationStatus.queued,
            created_by=created_by,
        )
        self.gen_repo.add(generation)

        job, _ = self.job_service.create(
            job_type=JobType.generate,
            idempotency_key=f"generate:{generation.id}",
            ref_id=generation.id,
        )
        await self.job_service.dispatch(job)

        MeteringService(self.gen_repo.db, self.gen_repo.tenant_id).record(
            action="generation.created",
            resource={
                "generation_id": str(generation.id),
                "profile_version": outline.profile_version,
                "template_version": profile.template_version,
                "source_ids": [str(s.id) for s in ready_sources],
                "skipped_failed_source_ids": [str(s.id) for s in skipped_failed],
            },
            actor_user_id=created_by,
        )
        logger.info("generation_queued", extra={"generation_id": str(generation.id)})
        return generation
