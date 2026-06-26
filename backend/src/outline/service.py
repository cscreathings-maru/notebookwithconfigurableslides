"""Outline service: build (LLM), read, and re-validate edited outlines.

Building pins the profile's latest approved version, composes a controlled prompt,
produces a validated outline, persists it, and meters the LLM token usage. Editing
re-validates (repairing onto the existing structure when possible).
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core.errors import NotFoundError, ValidationError
from ..core.logging import get_logger
from ..ingestion.repository import ProjectRepository
from ..metering.service import MeteringService
from ..models import Outline
from ..registry.repository import ProfileRepository
from ..tenancy.llm_config import TenantLlmConfigService
from .builder import build_outline
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
        content, usage = await build_outline(
            project=project,
            profile=profile,
            on_client=self.on_client,
            llm=self.llm,
            provider_config=provider_config,
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
