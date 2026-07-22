"""Freeform (NotebookLM Studio) deck generation.

Builds a deck directly from a chosen content source with per-deck Presenton config,
bypassing the governed profile/outline/consistency pipeline. Reuses the Generation
model, the generate job/worker, the object store and the download endpoint.
"""

from __future__ import annotations

import uuid

from ..chat.repository import ChatRepository
from ..core.errors import NotFoundError, ValidationError
from ..core.logging import get_logger
from ..guide.repository import GuideRepository
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..jobs.service import JobService
from ..models import Generation, GenerationStatus, JobType, SourceStatus
from ..registry.repository import TemplateRepository
from ..schemas.generation import GenerationCreate
from ..tenancy.llm_config import TenantLlmConfigService
from .freeform_mapper import build_freeform_request
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
    ):
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
        provider_config = TenantLlmConfigService(
            self.gen_repo.db, self.gen_repo.tenant_id
        ).get_config()
        model = payload.model or provider_config.get("model")

        content = await self._resolve_content(project, payload, provider_config, model)

        ready_source_ids = [
            str(s.id)
            for s in self.source_repo.list_by_project(project_id)
            if s.status is SourceStatus.ready
        ]

        template_ref = None
        template_logical_id = None
        template_version = None
        if payload.template_id is not None:
            tmpl = self.template_repo.latest_approved(
                payload.template_id
            ) or self.template_repo.latest(payload.template_id)
            if tmpl is None:
                raise NotFoundError("Template not found.")
            template_ref = tmpl.presenton_template_ref
            template_logical_id = tmpl.logical_id
            template_version = tmpl.version

        params = build_freeform_request(
            content=content,
            content_source=payload.content_source or "custom",
            tone=payload.tone.value,
            density=payload.density.value,
            n_slides=payload.n_slides,
            template_ref=template_ref,
            web_search=payload.web_search,
            export_as=payload.export_as,
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
        await self.job_service.dispatch(job)
        logger.info(
            "freeform_generation_queued",
            extra={"generation_id": str(generation.id), "source": payload.content_source},
        )
        return generation

    async def _resolve_content(
        self, project, payload: GenerationCreate, provider_config: dict, model: str
    ) -> str:
        source = payload.content_source
        if source == "custom":
            if not (payload.custom_markdown or "").strip():
                raise ValidationError("custom_markdown is required for content_source=custom.")
            return payload.custom_markdown.strip()

        if source == "chat":
            if payload.chat_message_id is None:
                raise ValidationError("chat_message_id is required for content_source=chat.")
            message = self.chat_repo.get(payload.chat_message_id)  # 404 across tenants
            return message.content

        if source == "summary":
            guide = self.guide_repo.get_by_project(project.id)
            if guide is None or not guide.summary:
                raise ValidationError("Generate the notebook guide first.")
            return guide.summary

        if source == "notebook":
            snippets = []
            if project.on_notebook_id:
                snippets = await self.on_client.search(
                    notebook_id=project.on_notebook_id,
                    query="comprehensive synthesis of all key content",
                )
            grounding = "\n".join(
                f"- {s.get('text', '')}" for s in snippets if s.get("text")
            ).strip()
            if not grounding:
                raise ValidationError(
                    "No indexed content to synthesize; upload and index sources first."
                )
            answer = await self.llm.chat(
                system=(
                    "Synthesize the source material into a well-structured brief suitable "
                    "for a slide deck. Use clear sections and concise points."
                ),
                user=grounding,
                provider_config=provider_config,
                temperature=0.3,
                max_tokens=1400,
                model_override=model,
            )
            return answer.text

        raise ValidationError("content_source must be summary, notebook, chat, or custom.")
