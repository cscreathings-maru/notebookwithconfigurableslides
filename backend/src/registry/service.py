"""Registry services: versioned profiles + templates with an immutability guard.

Rules enforced here:
- Editing a profile creates a NEW version (the prior version is never mutated).
- A profile/template version referenced by any Generation is frozen: its status
  cannot be transitioned (approve/archive) — attempts raise VersionInUseError (409).
- Profiles must bind an APPROVED template version (governance gate).
- Template names sent to Presenton are tenant-namespaced; the engine ref is stored
  but never exposed.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.logging import get_logger
from ..metering.service import MeteringService
from ..models import (
    RegistryStatus,
    StakeholderProfile,
    Template,
    Tenant,
    Tone,
    Verbosity,
)
from ..storage.object_store import ObjectStore
from .repository import ProfileRepository, RegistryUsage, TemplateRepository

logger = get_logger("orchestrator.registry")


class VersionInUseError(ConflictError):
    code = "version_in_use"


def _tenant_namespace(db, tenant_id: uuid.UUID) -> str:
    tenant = db.get(Tenant, tenant_id)
    return tenant.slug if tenant else tenant_id.hex


class TemplateService:
    def __init__(
        self,
        *,
        repo: TemplateRepository,
        usage: RegistryUsage,
        presenton,
        object_store: ObjectStore,
    ):
        self.repo = repo
        self.usage = usage
        self.presenton = presenton
        self.object_store = object_store

    async def create(
        self,
        *,
        name: str,
        brand_tokens: dict[str, Any],
        pptx_filename: str | None,
        pptx_content: bytes | None,
        created_by: uuid.UUID,
    ) -> Template:
        namespace = _tenant_namespace(self.repo.db, self.repo.tenant_id)
        namespaced_name = f"{namespace}__{name}"

        logical_id = uuid.uuid4()
        source_pptx_uri: str | None = None
        pptx_path: str | None = None

        if pptx_filename is not None and pptx_content is not None:
            key = self.object_store.tenant_key(
                tenant_id=self.repo.tenant_id.hex,
                project_id="templates",
                source_id=logical_id.hex,
                filename=pptx_filename,
            )
            self.object_store.put_bytes(
                key=key,
                data=pptx_content,
                content_type=(
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
            )
            source_pptx_uri = key
            pptx_path = self.object_store.presigned_get(key=key)

        # Register/import the template in Presenton (engine ref stays server-side).
        ref = await self.presenton.register_template(
            name=namespaced_name, source_pptx_path=pptx_path
        )

        template = Template(
            logical_id=logical_id,
            version=1,
            name=name,
            presenton_template_ref=ref,
            source_pptx_uri=source_pptx_uri,
            brand_tokens=brand_tokens,
            status=RegistryStatus.draft,
            created_by=created_by,
        )
        self.repo.add(template)
        self._audit("template.created", template, created_by)
        logger.info("template_created", extra={"template_id": str(logical_id)})
        return template

    def approve(self, logical_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None) -> Template:
        latest = self.repo.latest(logical_id)
        if latest is None:
            raise NotFoundError("Template not found.")
        if self.usage.template_version_in_use(logical_id, latest.version):
            raise VersionInUseError("Template version is in use and immutable.")
        _approve_row(latest)
        self.repo.db.add(latest)
        self.repo.db.flush()
        self._audit("template.approved", latest, actor_user_id)
        return latest

    def _audit(self, action: str, template: Template, actor: uuid.UUID | None) -> None:
        MeteringService(self.repo.db, self.repo.tenant_id).audit(
            action=action,
            resource={"template_id": str(template.logical_id), "version": template.version},
            actor_user_id=actor,
        )

    def list_all(self, *, approved_only: bool) -> list[Template]:
        rows = self.repo.list_all()
        if approved_only:
            rows = [r for r in rows if r.status is RegistryStatus.approved]
        return rows


class ProfileService:
    def __init__(
        self,
        *,
        repo: ProfileRepository,
        template_repo: TemplateRepository,
        usage: RegistryUsage,
    ):
        self.repo = repo
        self.template_repo = template_repo
        self.usage = usage

    def _pin_template(self, template_id: uuid.UUID) -> int:
        """Pin to the template's latest APPROVED version, or reject."""
        approved = self.template_repo.latest_approved(template_id)
        if approved is None:
            raise ValidationError(
                "Profile must bind an approved template.", code="template_not_approved"
            )
        return approved.version

    def create(
        self,
        *,
        name: str,
        audience: str,
        template_id: uuid.UUID,
        tone: Tone,
        verbosity: Verbosity,
        slide_min: int,
        slide_max: int,
        language: str,
        section_structure: list[Any],
        prompt_config: dict[str, Any],
        created_by: uuid.UUID,
    ) -> StakeholderProfile:
        template_version = self._pin_template(template_id)
        profile = StakeholderProfile(
            logical_id=uuid.uuid4(),
            version=1,
            name=name,
            audience=audience,
            template_id=template_id,
            template_version=template_version,
            tone=tone,
            verbosity=verbosity,
            slide_min=slide_min,
            slide_max=slide_max,
            language=language,
            section_structure=section_structure,
            prompt_config=prompt_config,
            status=RegistryStatus.draft,
            created_by=created_by,
        )
        self.repo.add(profile)
        self._audit("profile.created", profile, created_by)
        logger.info("profile_created", extra={"profile_id": str(profile.logical_id)})
        return profile

    def update(self, logical_id: uuid.UUID, **fields: Any) -> StakeholderProfile:
        """Create a NEW version; the prior version is never mutated."""
        latest = self.repo.latest(logical_id)
        if latest is None:
            raise NotFoundError("Profile not found.")

        template_id: uuid.UUID = fields["template_id"]
        template_version = self._pin_template(template_id)

        new_version = StakeholderProfile(
            logical_id=logical_id,
            version=self.repo.next_version(logical_id),
            name=fields["name"],
            audience=fields["audience"],
            template_id=template_id,
            template_version=template_version,
            tone=fields["tone"],
            verbosity=fields["verbosity"],
            slide_min=fields["slide_min"],
            slide_max=fields["slide_max"],
            language=fields["language"],
            section_structure=fields["section_structure"],
            prompt_config=fields["prompt_config"],
            status=RegistryStatus.draft,
            created_by=fields["created_by"],
        )
        self.repo.add(new_version)
        self._audit("profile.updated", new_version, fields.get("created_by"))
        logger.info(
            "profile_versioned",
            extra={"profile_id": str(logical_id), "version": new_version.version},
        )
        return new_version

    def approve(
        self, logical_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None
    ) -> StakeholderProfile:
        latest = self.repo.latest(logical_id)
        if latest is None:
            raise NotFoundError("Profile not found.")
        if self.usage.profile_version_in_use(logical_id, latest.version):
            raise VersionInUseError("Profile version is in use and immutable.")
        _approve_row(latest)
        self.repo.db.add(latest)
        self.repo.db.flush()
        self._audit("profile.approved", latest, actor_user_id)
        return latest

    def _audit(
        self, action: str, profile: StakeholderProfile, actor: uuid.UUID | None
    ) -> None:
        MeteringService(self.repo.db, self.repo.tenant_id).audit(
            action=action,
            resource={"profile_id": str(profile.logical_id), "version": profile.version},
            actor_user_id=actor,
        )

    def list_all(self, *, approved_only: bool) -> list[StakeholderProfile]:
        rows = self.repo.list_all()
        if approved_only:
            rows = [r for r in rows if r.status is RegistryStatus.approved]
        return rows


def _approve_row(row) -> None:
    if row.status is RegistryStatus.approved:
        return  # idempotent
    if row.status is not RegistryStatus.draft:
        raise ConflictError(
            f"Cannot approve a '{row.status.value}' version.", code="invalid_transition"
        )
    row.status = RegistryStatus.approved
