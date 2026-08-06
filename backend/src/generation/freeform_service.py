"""Freeform (NotebookLM Studio) deck generation.

Builds a deck directly from a chosen content source with per-deck Presenton config,
bypassing the governed profile/outline/consistency pipeline. Reuses the Generation
model, the generate job/worker, the object store and the download endpoint.

DG-2 adds a THIRD entry, `create_from_outline`: a confirmed freeform outline
(DG-1 -- no profile, `Outline.profile_id is None`) generates through this same
service rather than a new one. `docs/ARCHITECTURE.md` §3 names two-parallel-services
as this codebase's recurring failure mode; a profile-less outline has nowhere
governed to go, so it extends the freeform service instead of starting a third.
"""

from __future__ import annotations

import uuid

from ..chat.repository import ChatRepository
from ..content.resolver import resolve_freeform_content
from ..core.config import get_settings
from ..core.errors import NotFoundError, ValidationError
from ..core.logging import get_logger
from ..guide.repository import GuideRepository
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..jobs.service import JobService
from ..metering.alerts import AlertSink
from ..models import Generation, GenerationStatus, JobType, Outline, SourceStatus
from ..outline.schema import OutlineContent
from ..registry.repository import TemplateRepository
from ..schemas.generation import GenerationCreate
from ..tenancy.llm_config import TenantLlmConfigService
from .freeform_mapper import build_freeform_request
from .mapper import slides_markdown_from_outline
from .preflight import authorize_generation, meter_generation
from .repository import GenerationRepository

logger = get_logger("orchestrator.generation.freeform")


class FreeformGenerationService:
    def __init__(
        self,
        *,
        gen_repo: GenerationRepository,
        project_repo: ProjectRepository,
        source_repo: SourceRepository,
        guide_repo: GuideRepository,
        chat_repo: ChatRepository,
        template_repo: TemplateRepository,
        on_client,
        llm,
        job_service: JobService,
        alert_sink: AlertSink,
    ):
        self.alert_sink = alert_sink
        self.gen_repo = gen_repo
        self.project_repo = project_repo
        self.source_repo = source_repo
        self.guide_repo = guide_repo
        self.chat_repo = chat_repo
        self.template_repo = template_repo
        self.on_client = on_client
        self.llm = llm
        self.job_service = job_service

    async def create(
        self, *, project_id: uuid.UUID, payload: GenerationCreate, created_by: uuid.UUID
    ) -> Generation:
        project = self.project_repo.get(project_id)

        # Same gate as the governed path, before any row is written (T-2.2).
        authorize_generation(
            db=self.gen_repo.db,
            tenant_id=self.gen_repo.tenant_id,
            actor_user_id=created_by,
            alert_sink=self.alert_sink,
        )

        provider_config = TenantLlmConfigService(
            self.gen_repo.db, self.gen_repo.tenant_id
        ).get_config()
        model = payload.model or provider_config.get("model")
        language = payload.language or get_settings().default_language

        content = await self._resolve_content(
            project, payload, provider_config, model, language
        )

        ready_source_ids = [
            str(s.id)
            for s in self.source_repo.list_by_project(project_id)
            if s.status is SourceStatus.ready
        ]

        template_ref, template_logical_id, template_version = self._resolve_template(
            payload.template_id
        )

        params = build_freeform_request(
            content=content,
            content_source=payload.content_source or "custom",
            tone=payload.tone.value,
            density=payload.density.value,
            n_slides=payload.n_slides,
            template_ref=template_ref,
            web_search=payload.web_search,
            export_as=payload.export_as,
            language=language,
        )

        generation = Generation(
            project_id=project_id,
            outline_id=None,
            profile_id=None,
            profile_version=None,
            template_id=template_logical_id,
            template_version=template_version,
            source_ids=ready_source_ids,
            model=model,
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
        await self.job_service.commit_and_dispatch(job)

        meter_generation(
            db=self.gen_repo.db,
            tenant_id=self.gen_repo.tenant_id,
            actor_user_id=created_by,
            resource={
                "generation_id": str(generation.id),
                "path": "freeform",
                "content_source": payload.content_source or "custom",
                "template_version": template_version,
                "source_ids": ready_source_ids,
            },
        )
        logger.info(
            "freeform_generation_queued",
            extra={"generation_id": str(generation.id), "source": payload.content_source},
        )
        return generation

    async def _resolve_content(
        self,
        project,
        payload: GenerationCreate,
        provider_config: dict,
        model: str,
        language: str,
    ) -> str:
        return await resolve_freeform_content(
            project=project,
            content_source=payload.content_source or "custom",
            custom_markdown=payload.custom_markdown,
            chat_message_id=payload.chat_message_id,
            provider_config=provider_config,
            model=model,
            language=language,
            guide_repo=self.guide_repo,
            chat_repo=self.chat_repo,
            source_repo=SourceRepository(self.gen_repo.db, self.gen_repo.tenant_id),
            on_client=self.on_client,
            llm=self.llm,
        )

    def _resolve_template(
        self, template_id: uuid.UUID | None
    ) -> tuple[str | None, uuid.UUID | None, int | None]:
        """(engine ref, logical id, version) for a requested template, or all-None
        when none was requested. Shared by `create` and `create_from_outline` so
        template resolution doesn't drift between the two freeform entry points."""
        if template_id is None:
            return None, None, None
        tmpl = self.template_repo.latest_approved(template_id) or self.template_repo.latest(
            template_id
        )
        if tmpl is None:
            raise NotFoundError("Template not found.")
        return tmpl.presenton_template_ref, tmpl.logical_id, tmpl.version

    async def create_from_outline(
        self, *, project_id: uuid.UUID, outline: Outline, payload: GenerationCreate, created_by: uuid.UUID
    ) -> Generation:
        """DG-2: generate from a CONFIRMED freeform outline (`outline.profile_id is
        None` -- the governed branch handles the profile-pinned case before this is
        ever reached, see `api/generations.py`).

        Structure is already fixed by the outline: `slides_markdown` is derived from
        it with the SAME function the governed mapper uses
        (`slides_markdown_from_outline`), so Presenton renders the confirmed
        sections instead of re-inventing structure from an unstructured content
        blob the way the other freeform sources do. `payload.n_slides` is ignored
        here on purpose -- the outline's section count already IS the slide-count
        decision, made when it was reviewed and confirmed; a stale Advanced-panel
        default shouldn't silently override it.
        """
        self.project_repo.get(project_id)  # 404 across tenants
        if outline.project_id != project_id:
            raise NotFoundError("Outline not found for this project.")
        if not outline.valid:
            raise ValidationError("Outline is not valid; fix it before generating.")

        # Same gate as every other generation path, before any row is written.
        authorize_generation(
            db=self.gen_repo.db,
            tenant_id=self.gen_repo.tenant_id,
            actor_user_id=created_by,
            alert_sink=self.alert_sink,
        )

        provider_config = TenantLlmConfigService(
            self.gen_repo.db, self.gen_repo.tenant_id
        ).get_config()
        model = payload.model or provider_config.get("model")
        language = payload.language or get_settings().default_language

        outline_content = OutlineContent(**outline.content)
        slides_markdown = slides_markdown_from_outline(outline_content)
        titles = ", ".join(
            s.title for s in sorted(outline_content.sections, key=lambda s: s.order)
        )

        ready_source_ids = [
            str(s.id)
            for s in self.source_repo.list_by_project(project_id)
            if s.status is SourceStatus.ready
        ]

        template_ref, template_logical_id, template_version = self._resolve_template(
            payload.template_id
        )

        params = build_freeform_request(
            content=f"Presentation outline: {titles}." if titles else "Presentation",
            # Not "custom" -- slides_markdown is passed explicitly below and wins
            # outright either way; this only affects the branch build_freeform_request
            # would otherwise take when no explicit slides_markdown is given.
            content_source="notebook",
            tone=payload.tone.value,
            density=payload.density.value,
            n_slides=len(slides_markdown) + 1,
            template_ref=template_ref,
            web_search=payload.web_search,
            export_as=payload.export_as,
            language=language,
            slides_markdown=slides_markdown,
        )

        generation = Generation(
            project_id=project_id,
            outline_id=outline.id,
            profile_id=None,
            profile_version=None,
            template_id=template_logical_id,
            template_version=template_version,
            source_ids=ready_source_ids,
            model=model,
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
        await self.job_service.commit_and_dispatch(job)

        meter_generation(
            db=self.gen_repo.db,
            tenant_id=self.gen_repo.tenant_id,
            actor_user_id=created_by,
            resource={
                "generation_id": str(generation.id),
                "path": "freeform",
                "content_source": "outline",
                "outline_id": str(outline.id),
                "template_version": template_version,
                "source_ids": ready_source_ids,
            },
        )
        logger.info(
            "freeform_generation_from_outline_queued",
            extra={"generation_id": str(generation.id), "outline_id": str(outline.id)},
        )
        return generation
