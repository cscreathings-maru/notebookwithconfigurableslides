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
from ..jobs.service import JobService
from ..metering.service import MeteringService
from ..models import (
    JobType,
    RegistrationStatus,
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


def tenant_namespace(db, tenant_id: uuid.UUID) -> str:
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
        job_service: JobService,
    ):
        self.repo = repo
        self.usage = usage
        self.presenton = presenton
        self.object_store = object_store
        self.job_service = job_service

    async def create(
        self,
        *,
        name: str,
        brand_tokens: dict[str, Any],
        pptx_filename: str | None,
        pptx_content: bytes | None,
        created_by: uuid.UUID,
    ) -> Template:
        """Store the row and dispatch registration; does not wait for it (TM-2).

        Registration is `POST /template/async` on the engine side -- layout
        generation for every slide, running in parallel, that can take minutes.
        Blocking this request on it is the reason there was never a progress
        state: a registering template was indistinguishable from a failed one.
        The row starts `pending` (the model's own default) and the worker
        (`registry/registration.py`) drives it to a terminal state.
        """
        logical_id = uuid.uuid4()
        source_pptx_uri: str | None = None

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

        template = Template(
            logical_id=logical_id,
            version=1,
            name=name,
            source_pptx_uri=source_pptx_uri,
            brand_tokens=brand_tokens,
            status=RegistryStatus.draft,
            registration_status=RegistrationStatus.pending,
            created_by=created_by,
        )
        self.repo.add(template)
        self.repo.db.flush()  # need template.id for the job's ref_id
        self._audit("template.created", template, created_by)

        job, _ = self.job_service.create(
            job_type=JobType.register_template,
            idempotency_key=f"register_template:{template.id}",
            ref_id=template.id,
        )
        await self.job_service.commit_and_dispatch(job)

        logger.info("template_created_registration_queued", extra={"template_id": str(logical_id)})
        return template

    async def reregister(
        self, logical_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None
    ) -> Template:
        """Re-queue engine registration for an existing template, from its stored PPTX.

        Registration previously happened only at creation, so a template registered
        through a broken request could never repair itself -- the operator's only route
        was re-uploading the same deck under a new name. The PPTX is already in object
        storage, so nothing needs re-uploading from the browser.

        Deliberately does NOT create a new version: the template's content is unchanged.
        What changes is the engine ref, which was never user-visible and was wrong.
        Async (TM-2), same as `create` -- resets to `pending` and returns immediately;
        the caller polls the same way it already does after creation.
        """
        latest = self.repo.latest(logical_id)
        if latest is None:
            raise NotFoundError("Template not found.")
        if not latest.source_pptx_uri:
            raise ValidationError(
                "This template has no stored PPTX. The slide engine derives colours, "
                "fonts and layouts from an uploaded deck, so there is nothing to "
                "register — create a template with a .pptx instead.",
                code="no_source_pptx",
            )

        latest.registration_status = RegistrationStatus.pending
        latest.registration_error = None
        self.repo.db.add(latest)
        self.repo.db.flush()

        job, _ = self.job_service.create(
            job_type=JobType.register_template,
            idempotency_key=f"register_template:{latest.id}:retry:{uuid.uuid4().hex}",
            ref_id=latest.id,
        )
        await self.job_service.commit_and_dispatch(job)

        self._audit("template.reregistration_queued", latest, actor_user_id)
        logger.info("template_reregistration_queued", extra={"template_id": str(logical_id)})
        return latest

    async def delete(
        self, logical_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None
    ) -> None:
        """Delete every version of a logical template (TM-5), engine-side then here.

        Refuses if ANY version is pinned by a Generation -- deleting it would strand
        that generation's provenance (`Generation.template_id`/`template_version`),
        the same invariant `VersionInUseError` already protects on status
        transitions, just checked across every version rather than one.
        """
        rows = self.repo.all_versions(logical_id)
        if not rows:
            raise NotFoundError("Template not found.")
        if self.usage.template_logical_id_in_use(logical_id):
            raise VersionInUseError(
                "This template is used by an existing generation and cannot be deleted."
            )

        # Engine side first: if this fails, nothing here has been touched yet, so
        # a retry is just calling delete again -- never a NoteAI row with no
        # engine counterpart to explain.
        engine_refs = {r.presenton_template_ref for r in rows if r.presenton_template_ref}
        for ref in engine_refs:
            await self.presenton.delete_template(ref=ref)

        version_count = len(rows)
        for row in rows:
            self.repo.db.delete(row)
        self.repo.db.flush()

        # Captured before delete, not read off the now-deleted rows: audit/log
        # after a flush should describe what happened, not risk touching an
        # ORM object SQLAlchemy considers gone.
        MeteringService(self.repo.db, self.repo.tenant_id).audit(
            action="template.deleted",
            resource={
                "template_id": str(logical_id),
                "versions_deleted": version_count,
            },
            actor_user_id=actor_user_id,
        )
        logger.info(
            "template_deleted",
            extra={"template_id": str(logical_id), "versions": version_count},
        )

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
