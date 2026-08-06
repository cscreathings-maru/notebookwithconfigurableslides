"""Outline service: build (LLM), read, and re-validate edited outlines.

Building pins the profile's latest approved version, composes a controlled prompt,
produces a validated outline, persists it, and meters the LLM token usage. Editing
re-validates (repairing onto the existing structure when possible).
"""

from __future__ import annotations

import uuid
from typing import Any

from ..chat.repository import ChatRepository
from ..content.resolver import resolve_freeform_content
from ..core.config import get_settings
from ..core.errors import ValidationError
from ..core.logging import get_logger
from ..guide.repository import GuideRepository
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..metering.service import MeteringService
from ..models import Outline
from ..registry.repository import ProfileRepository
from ..tenancy.llm_config import TenantLlmConfigService
from .builder import build_freeform_outline, build_outline
from .repository import OutlineRepository
from .schema import OutlineContent
from .validator import repair_outline, validate_outline

logger = get_logger("orchestrator.outline")


class OutlineService:
    def __init__(
        self,
        *,
        repo: OutlineRepository,
        project_repo: ProjectRepository,
        profile_repo: ProfileRepository,
        on_client,
        llm,
    ):
        self.repo = repo
        self.project_repo = project_repo
        self.profile_repo = profile_repo
        self.on_client = on_client
        self.llm = llm

    @property
    def _tenant_id(self) -> uuid.UUID:
        return self.repo.tenant_id

    async def build(self, *, project_id: uuid.UUID, profile_id: uuid.UUID, created_by: uuid.UUID) -> Outline:
        project = self.project_repo.get(project_id)
        profile = self.profile_repo.latest_approved(profile_id)
        if profile is None:
            raise ValidationError(
                "No approved version of this profile exists.", code="profile_not_approved"
            )

        provider_config = TenantLlmConfigService(self.repo.db, self._tenant_id).get_config()
        # Scope retrieval to this project's own sources -- the engine index is shared.
        allowed = SourceRepository(self.repo.db, self._tenant_id).engine_source_refs(
            project_id
        )
        content, usage = await build_outline(
            project=project,
            profile=profile,
            on_client=self.on_client,
            llm=self.llm,
            provider_config=provider_config,
            allowed_source_refs=allowed,
        )

        outline = Outline(
            project_id=project.id,
            profile_id=profile.logical_id,
            profile_version=profile.version,
            schema_version=content.schema_version,
            content=content.model_dump(),
            valid=True,
        )
        self.repo.add(outline)

        MeteringService(self.repo.db, self._tenant_id).record(
            action="outline.created",
            resource={"outline_id": str(outline.id), "project_id": str(project.id)},
            actor_user_id=created_by,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
        )
        logger.info("outline_built", extra={"outline_id": str(outline.id)})
        return outline

    async def build_freeform(
        self,
        *,
        project_id: uuid.UUID,
        content_source: str,
        custom_markdown: str | None,
        chat_message_id: uuid.UUID | None,
        tone: str,
        density: str,
        n_slides_hint: int | None,
        language: str | None,
        created_by: uuid.UUID,
    ) -> Outline:
        """Ungoverned outline (DG-1): no profile, LLM proposes structure itself.

        Same four content sources as freeform generation (`resolve_freeform_content`,
        shared with `FreeformGenerationService` so the two never drift on what each
        choice means), then one LLM call for structure + wording
        (`build_freeform_outline`). Persisted with `profile_id=None` -- the marker
        `generation/worker.py` already uses to skip the consistency gate for
        freeform generations applies here too, once a generation is built from this
        outline (DG-2).
        """
        project = self.project_repo.get(project_id)
        provider_config = TenantLlmConfigService(self.repo.db, self._tenant_id).get_config()
        resolved_language = language or get_settings().default_language

        content = await resolve_freeform_content(
            project=project,
            content_source=content_source,
            custom_markdown=custom_markdown,
            chat_message_id=chat_message_id,
            provider_config=provider_config,
            model=provider_config.get("model"),
            language=resolved_language,
            guide_repo=GuideRepository(self.repo.db, self._tenant_id),
            chat_repo=ChatRepository(self.repo.db, self._tenant_id),
            source_repo=SourceRepository(self.repo.db, self._tenant_id),
            on_client=self.on_client,
            llm=self.llm,
        )

        outline_content, usage = await build_freeform_outline(
            content=content,
            tone=tone,
            density=density,
            n_slides_hint=n_slides_hint,
            language=resolved_language,
            llm=self.llm,
            provider_config=provider_config,
        )

        outline = Outline(
            project_id=project.id,
            profile_id=None,
            profile_version=None,
            schema_version=outline_content.schema_version,
            content=outline_content.model_dump(),
            valid=True,
        )
        self.repo.add(outline)

        MeteringService(self.repo.db, self._tenant_id).record(
            action="outline.created",
            resource={
                "outline_id": str(outline.id),
                "project_id": str(project.id),
                "path": "freeform",
                "content_source": content_source,
            },
            actor_user_id=created_by,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
        )
        logger.info("freeform_outline_built", extra={"outline_id": str(outline.id)})
        return outline

    def get(self, outline_id: uuid.UUID) -> Outline:
        return self.repo.get(outline_id)

    def update(self, outline_id: uuid.UUID, *, content: dict[str, Any]) -> Outline:
        outline = self.repo.get(outline_id)

        model, errors = validate_outline(content)
        if model is None:
            existing_titles = [
                s.get("title") for s in (outline.content.get("sections") or []) if s.get("title")
            ]
            if existing_titles:
                model, errors = validate_outline(repair_outline(content, existing_titles))
        if model is None:
            raise ValidationError(f"Outline is invalid: {errors}")

        validated: OutlineContent = model
        outline.content = validated.model_dump()
        outline.schema_version = validated.schema_version
        outline.valid = True
        self.repo.db.add(outline)
        self.repo.db.flush()
        return outline
