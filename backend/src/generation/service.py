"""Generation service -- one entry point for governed and freeform decks.

`docs/ARCHITECTURE.md` §3 names divergence between the governed and freeform
paths as this codebase's recurring failure mode: the freeform path shipped
without quota or metering once, because it was a second implementation of
the same gate. RM-11 collapses `GenerationService` and
`FreeformGenerationService` into this one class -- governed and freeform
differ only in where content and structure come from, not in what happens
once a `DeckPlan` exists.

Three shapes reach `create()`, distinguished by `payload.outline_id` /
`payload.content_source` (`api/generations.py` still dispatches nothing --
the branching lives here now, in one place):

- **governed**: `outline_id` names an outline with a pinned profile.
  Structure is fixed (`deck/from_outline.py`, no LLM); a consistency gate
  validates the rendered deck against the profile's contract
  (`generation/worker.py`).
- **freeform-from-outline** (DG-2): `outline_id` names a confirmed outline
  with NO profile. Same deterministic structure, no consistency gate.
- **freeform**: `content_source` selects one of summary/notebook/chat/custom
  (`content/resolver.py`); structure AND design selection come from
  `deck/plan.py`'s single LLM call (LD-6).

Planning runs here, synchronously, before the row is written and the job
enqueued -- matches how the old governed path already built its full engine
request synchronously in `create()`; only rendering (deterministic, no LLM)
happens in the worker (`generation/worker.py`).

**LD-9 cutover note:** the per-generation review gate (D5/RM-9,
`GenerationStatus.awaiting_review`) is retired. The old layout matcher
(`deck/matcher.py`, deleted) produced a per-slide confidence score to gate
on; the new pipeline has none, because rendering a validated `DeckPlan` is
fully deterministic (L5) -- there is nothing left to be LOW confidence
ABOUT. The review gate moved from per-deck to per-template instead (L3,
`TemplateService.review_catalog`), which is a stronger guarantee: a
template's design vocabulary is reviewed once, by a human, before ANY deck
plans against it -- not sampled after the fact by a heuristic. Every
generation now queues directly.
"""

from __future__ import annotations

import uuid

from ..chat.repository import ChatRepository
from ..content.resolver import resolve_freeform_content
from ..core.config import get_settings
from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.logging import get_logger
from ..deck.catalog import DesignCatalog
from ..deck.from_outline import deck_plan_from_outline
from ..deck.plan import plan_deck
from ..guide.repository import GuideRepository
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..jobs.service import JobService
from ..metering.alerts import AlertSink
from ..models import Generation, GenerationStatus, JobType, Outline, SourceStatus, Template
from ..outline.repository import OutlineRepository
from ..outline.schema import OutlineContent
from ..registry.repository import ProfileRepository, TemplateRepository
from ..schemas.generation import GenerationCreate
from ..tenancy.llm_config import TenantLlmConfigService
from .preflight import authorize_generation, meter_generation
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
        project_repo: ProjectRepository,
        guide_repo: GuideRepository,
        chat_repo: ChatRepository,
        on_client,
        llm,
        job_service: JobService,
        alert_sink: AlertSink,
    ):
        self.gen_repo = gen_repo
        self.outline_repo = outline_repo
        self.source_repo = source_repo
        self.profile_repo = profile_repo
        self.template_repo = template_repo
        self.project_repo = project_repo
        self.guide_repo = guide_repo
        self.chat_repo = chat_repo
        self.on_client = on_client
        self.llm = llm
        self.job_service = job_service
        self.alert_sink = alert_sink

    def _resolve_template(self, template_id: uuid.UUID | None) -> Template | None:
        if template_id is None:
            return None
        template = self.template_repo.latest_approved(template_id) or self.template_repo.latest(
            template_id
        )
        if template is None:
            raise NotFoundError("Template not found.")
        return template

    def _ready_source_ids(self, project_id: uuid.UUID) -> list[str]:
        return [
            str(s.id)
            for s in self.source_repo.list_by_project(project_id)
            if s.status is SourceStatus.ready
        ]

    async def create(
        self, *, project_id: uuid.UUID, payload: GenerationCreate, created_by: uuid.UUID
    ) -> Generation:
        project = self.project_repo.get(project_id)

        if payload.export_as != "pptx":
            # RM-14 (deferred, gated on Q1): no PDF export yet. Refused here,
            # before any row is written, rather than queuing a job destined
            # to fail in the worker.
            raise ValidationError("PDF export is not available yet; request pptx.")

        outline: Outline | None = None
        profile = None
        template: Template | None = None
        ready_source_ids: list[str] = []
        skipped_failed_ids: list[str] = []

        if payload.outline_id is not None:
            outline = self.outline_repo.get(payload.outline_id)
            if outline.project_id != project_id:
                raise NotFoundError("Outline not found for this project.")
            if not outline.valid:
                raise ValidationError("Outline is not valid; fix it before generating.")

            if outline.profile_id is not None:
                # Governed: the profile pins tone/verbosity/language/template
                # and gates the rendered deck with a consistency check.
                profile = self.profile_repo.get_version(outline.profile_id, outline.profile_version)
                if profile is None:
                    raise NotFoundError("Pinned profile version not found.")
                template = self.template_repo.get_version(profile.template_id, profile.template_version)
                if template is None:
                    raise NotFoundError("Pinned template version not found.")

                # Source readiness policy: block while anything is still
                # analyzing (no partial deck); proceed from what's ready,
                # skipping anything that failed to ingest; block if nothing
                # is ready.
                sources = self.source_repo.list_by_project(project_id)
                in_progress = [
                    s for s in sources if s.status in (SourceStatus.queued, SourceStatus.processing)
                ]
                if in_progress:
                    raise SourcesNotReadyError(
                        f"{len(in_progress)} source(s) are still being analyzed; "
                        "wait for analysis to finish."
                    )
                ready = [s for s in sources if s.status is SourceStatus.ready]
                if not ready:
                    raise NoReadySourcesError(
                        "No sources are ready; upload a source and wait for analysis "
                        "before generating."
                    )
                ready_source_ids = [str(s.id) for s in ready]
                skipped_failed_ids = [str(s.id) for s in sources if s.status is SourceStatus.failed]
                if skipped_failed_ids:
                    logger.warning(
                        "generation_skips_failed_sources",
                        extra={"project_id": str(project_id), "skipped_source_ids": skipped_failed_ids},
                    )
            else:
                # DG-2: a confirmed freeform outline. Structure is already
                # fixed; there is no profile to govern it further.
                template = self._resolve_template(payload.template_id)
                ready_source_ids = self._ready_source_ids(project_id)
        else:
            if payload.content_source is None:
                raise ValidationError("Provide either content_source (freeform) or outline_id.")
            template = self._resolve_template(payload.template_id)
            ready_source_ids = self._ready_source_ids(project_id)

        # Quota gate -- before any row is written, so a blocked attempt
        # consumes no quota and leaves nothing behind.
        authorize_generation(
            db=self.gen_repo.db,
            tenant_id=self.gen_repo.tenant_id,
            actor_user_id=created_by,
            alert_sink=self.alert_sink,
        )

        llm_config = TenantLlmConfigService(self.gen_repo.db, self.gen_repo.tenant_id)
        provider_config = llm_config.get_config()
        model = payload.model or provider_config.get("model")

        # Governed: the pinned profile IS the governance -- its tone/verbosity/
        # language win over whatever the request happened to carry (which
        # defaults to Tone.default/Verbosity.standard when unset, silently
        # discarding what the profile actually declares). Freeform has no
        # profile to defer to, so the request's own knobs apply.
        if profile is not None:
            tone_value = profile.tone.value
            density_value = profile.verbosity.value
            language = profile.language
        else:
            tone_value = payload.tone.value
            density_value = payload.density.value
            language = payload.language or get_settings().default_language

        # Checked BEFORE resolving content: `resolve_freeform_content` can make
        # an LLM call (content_source="notebook" synthesises a brief), and
        # spending that only to refuse the generation a moment later bills the
        # user for a request that was never going to succeed.
        #
        # Three distinct codes, because each situation needs a different
        # response from the user.
        if template is None:
            raise ValidationError(
                "Select a template to generate a deck. Slides are cloned from a "
                "template's own designed slides, so one is required -- there is no "
                "default theme. If no template is listed, a workspace admin needs to "
                "upload a .pptx on the Templates page first.",
                code="template_required",
            )
        if not template.slide_catalog or template.catalog_reviewed_at is None:
            raise ValidationError(
                f"Template '{template.name}' is not ready to generate from: "
                f"{template.catalog_error or 'its design catalog has not been reviewed by an admin yet.'} "
                "Ask a workspace admin to review its catalog on the Templates page.",
                code="template_not_usable",
            )
        catalog = DesignCatalog.model_validate(template.slide_catalog)

        if outline is not None:
            outline_content = OutlineContent(**outline.content)
            deck_plan = deck_plan_from_outline(
                outline=outline_content, catalog=catalog, deck_title=project.name or "Presentation"
            )
        else:
            content = await resolve_freeform_content(
                project=project,
                content_source=payload.content_source,
                custom_markdown=payload.custom_markdown,
                chat_message_id=payload.chat_message_id,
                provider_config=provider_config,
                model=model,
                language=language,
                guide_repo=self.guide_repo,
                chat_repo=self.chat_repo,
                source_repo=self.source_repo,
                on_client=self.on_client,
                llm=self.llm,
            )
            # An explicit per-request model still wins; the task override is
            # the default when the caller expressed no preference.
            plan_model = payload.model or llm_config.model_for("deck_plan")
            deck_plan, plan_usage = await plan_deck(
                content=content,
                catalog=catalog,
                n_slides_hint=payload.n_slides,
                tone=tone_value,
                density=density_value,
                language=language,
                llm=self.llm,
                provider_config=provider_config,
                model_override=plan_model,
            )
            # Cost attribution needs the model that actually ran, not the
            # tenant default -- you cannot attribute what you do not record.
            logger.info(
                "deck_plan_completed",
                extra={
                    "model": plan_model or provider_config.get("model"),
                    "tokens_in": plan_usage.tokens_in,
                    "tokens_out": plan_usage.tokens_out,
                    "attempts": plan_usage.attempts,
                    "overflow_anchors": len(plan_usage.overflow),
                },
            )

        generation = Generation(
            project_id=project_id,
            outline_id=outline.id if outline is not None else None,
            profile_id=profile.logical_id if profile is not None else None,
            profile_version=profile.version if profile is not None else None,
            template_id=template.logical_id if template is not None else None,
            template_version=template.version if template is not None else None,
            source_ids=ready_source_ids,
            model=model,
            provider=provider_config.get("provider"),
            deck_plan=deck_plan.model_dump(mode="json"),
            params={
                "tone": tone_value,
                "verbosity": density_value,
                "n_slides": len(deck_plan.slides),
                "language": language,
                "export_as": payload.export_as,
            },
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

        # Metered regardless of downstream outcome: the quota was consumed by
        # the planning call that already ran.
        meter_generation(
            db=self.gen_repo.db,
            tenant_id=self.gen_repo.tenant_id,
            actor_user_id=created_by,
            resource={
                "generation_id": str(generation.id),
                "path": "governed" if profile is not None else "freeform",
                "content_source": payload.content_source,
                "outline_id": str(outline.id) if outline is not None else None,
                "profile_version": profile.version if profile is not None else None,
                "template_version": template.version if template is not None else None,
                "source_ids": ready_source_ids,
                "skipped_failed_source_ids": skipped_failed_ids,
            },
        )
        logger.info(
            "generation_queued",
            extra={"generation_id": str(generation.id), "path": "governed" if profile else "freeform"},
        )
        return generation
