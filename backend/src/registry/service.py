"""Registry services: versioned profiles + templates with an immutability guard.

Rules enforced here:
- Editing a profile creates a NEW version (the prior version is never mutated).
- A profile/template version referenced by any Generation is frozen: its status
  cannot be transitioned (approve/archive) — attempts raise VersionInUseError (409).
- Profiles must bind an APPROVED template version (governance gate).
- A template's usable state is `catalog_status` + `catalog_reviewed_at` (LD-2/
  LD-3/L3) -- an LLM reads the uploaded `.pptx` as a design catalog (async,
  a job, never inline) and an admin reviews it once before the template can
  be approved. Replaces `inspection_status`/`deck/inspect.py`'s synchronous
  geometric read entirely (Phase C cutover, `PLAN-LLM-DECK-PLANNING.md` LD-9).
"""

from __future__ import annotations

import uuid
from typing import Any

from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.logging import get_logger
from ..deck.catalog import DesignCatalog
from ..jobs.service import JobService
from ..metering.service import MeteringService
from ..models import (
    JobType,
    RegistryStatus,
    StakeholderProfile,
    Template,
    TemplateCatalogStatus,
    Tone,
    Verbosity,
)
from ..models.base import utcnow
from ..storage.object_store import ObjectStore
from .repository import ProfileRepository, RegistryUsage, TemplateRepository

logger = get_logger("orchestrator.registry")

_PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class VersionInUseError(ConflictError):
    code = "version_in_use"


def apply_catalog_result(template: Template, *, catalog: DesignCatalog | None, error: str | None) -> None:
    """Persist an LD-2 cataloguing outcome onto `template` in place -- the
    worker-side counterpart to `_apply_inspection` (`workers/tasks.py::
    run_catalog_template`), called once the async cataloguing job has run.

    Never called inline with `create`: an LLM call belongs in a job, not a
    request/response cycle (`TemplateCatalogStatus.cataloguing`'s docstring).
    """
    if error is not None:
        template.slide_catalog = None
        template.catalog_status = TemplateCatalogStatus.failed
        template.catalog_error = error
        return
    template.slide_catalog = catalog.model_dump(mode="json") if catalog is not None else None
    template.catalog_status = TemplateCatalogStatus.ready
    template.catalog_error = None
    # A fresh (or re-run) catalog is unreviewed until an admin looks at it
    # again (L3) -- carrying a stale review forward across a re-catalogue
    # would silently approve content nobody has seen.
    template.catalog_reviewed_at = None
    template.catalog_reviewed_by = None


class TemplateService:
    def __init__(
        self,
        *,
        repo: TemplateRepository,
        usage: RegistryUsage,
        object_store: ObjectStore,
        job_service: JobService,
    ):
        self.repo = repo
        self.usage = usage
        self.object_store = object_store
        self.job_service = job_service

    async def _dispatch_cataloguing(self, template: Template, *, idempotency_key: str) -> None:
        job, _ = self.job_service.create(
            job_type=JobType.catalog_template,
            idempotency_key=idempotency_key,
            ref_id=template.id,
        )
        await self.job_service.commit_and_dispatch(job)

    async def create(
        self,
        *,
        name: str,
        brand_tokens: dict[str, Any],
        pptx_filename: str | None,
        pptx_content: bytes | None,
        created_by: uuid.UUID,
    ) -> Template:
        """Store the row and enqueue LD-2 cataloguing.

        Cataloguing is NOT inline: it is an LLM call over the whole deck, so
        it runs as a job (LD-3) -- the response carries `catalog_status:
        "cataloguing"`, not a terminal outcome, when a PPTX was uploaded.
        The template stays `draft`/unapproved until an admin reviews the
        finished catalog (`review_catalog`) -- there is no auto-approve
        anymore (L3: a catalog nobody has seen is not yet trustworthy).
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
            self.object_store.put_bytes(key=key, data=pptx_content, content_type=_PPTX_MEDIA_TYPE)
            source_pptx_uri = key

        template = Template(
            logical_id=logical_id,
            version=1,
            name=name,
            source_pptx_uri=source_pptx_uri,
            brand_tokens=brand_tokens,
            status=RegistryStatus.draft,
            catalog_status=(
                TemplateCatalogStatus.cataloguing if pptx_content is not None else TemplateCatalogStatus.no_source
            ),
            created_by=created_by,
        )
        self.repo.add(template)
        self.repo.db.flush()
        self._audit("template.created", template, created_by)
        logger.info(
            "template_created",
            extra={"template_id": str(logical_id), "catalog_status": template.catalog_status.value},
        )

        if pptx_content is not None:
            # Stable per-template key: guards against a double form-submit
            # (two near-simultaneous `create()` calls for the same upload)
            # collapsing into one job, not into two.
            await self._dispatch_cataloguing(template, idempotency_key=f"catalog_template:{template.id}")

        return template

    async def recatalog(self, logical_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None) -> Template:
        """Re-run LD-2 cataloguing against the template's stored `.pptx`
        (the LLM counterpart to `reinspect`). Parks at `cataloguing` again --
        the caller polls, same as `create`.

        The idempotency key carries a fresh nonce on every call, deliberately
        NOT the stable `catalog_template:{template.id}` `create()` uses:
        reusing that key meant `JobService.create()`'s own dedupe always
        found the ORIGINAL job (however old, however permanently stuck) and
        returned it unchanged -- `recatalog` could never actually start a new
        attempt. An admin clicking "re-catalogue" is a deliberate retry, not
        an accidental double-submit to guard against (bug found in
        production 2026-08-17: a template stuck `cataloguing` forever
        because every `/recatalog` call silently no-opped against the first,
        already-failed job).
        """
        latest = self.repo.latest(logical_id)
        if latest is None:
            raise NotFoundError("Template not found.")
        if not latest.source_pptx_uri:
            raise ValidationError(
                "This template has no stored .pptx to catalogue.", code="no_source_pptx"
            )
        latest.catalog_status = TemplateCatalogStatus.cataloguing
        latest.catalog_error = None
        self.repo.db.add(latest)
        self.repo.db.flush()
        self._audit("template.recatalogued", latest, actor_user_id)
        await self._dispatch_cataloguing(
            latest, idempotency_key=f"catalog_template:{latest.id}:{uuid.uuid4().hex}"
        )
        return latest

    def review_catalog(
        self,
        logical_id: uuid.UUID,
        *,
        designs: list[dict[str, Any]] | None,
        actor_user_id: uuid.UUID | None,
    ) -> Template:
        """LD-4/L3: an admin reviews the LLM's catalog, optionally correcting
        role/anchor labels, and marks it reviewed -- THE approval gate now
        (replaces "usable inspection auto-approves"): a catalog nobody has
        looked at is not something a deck should be planned against, so
        review is what moves `status` to `approved`, not cataloguing success
        alone.

        `designs`, when given, REPLACES the stored catalog's designs
        wholesale -- validated through the same `DesignCatalog` pydantic
        contract cataloguing itself produces, so a correction cannot save a
        shape id that structurally could not have come from `deck/catalog.py`
        in the first place.
        """
        latest = self.repo.latest(logical_id)
        if latest is None:
            raise NotFoundError("Template not found.")
        if latest.catalog_status is not TemplateCatalogStatus.ready:
            raise ValidationError(
                f"This template's catalog is '{latest.catalog_status.value}', not ready to review.",
                code="catalog_not_ready",
            )

        if designs is not None:
            try:
                corrected = DesignCatalog(designs=designs)
            except Exception as exc:  # pydantic ValidationError -- reject, don't guess
                raise ValidationError(f"Invalid catalog correction: {exc}") from exc
            latest.slide_catalog = corrected.model_dump(mode="json")

        latest.catalog_reviewed_at = utcnow()
        latest.catalog_reviewed_by = actor_user_id
        latest.status = RegistryStatus.approved
        self.repo.db.add(latest)
        self.repo.db.flush()
        self._audit("template.catalog_reviewed", latest, actor_user_id)
        logger.info("template_catalog_reviewed", extra={"template_id": str(logical_id)})
        return latest

    def delete(self, logical_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None) -> None:
        """Delete every version of a logical template (TM-5).

        Refuses if ANY version is pinned by a Generation -- deleting it would strand
        that generation's provenance (`Generation.template_id`/`template_version`),
        the same invariant `VersionInUseError` already protects on status
        transitions, just checked across every version rather than one.

        No engine-side call (RM-3) -- inspection never registers anything
        outside this database, so there is nothing else to clean up.
        """
        rows = self.repo.all_versions(logical_id)
        if not rows:
            raise NotFoundError("Template not found.")
        if self.usage.template_logical_id_in_use(logical_id):
            raise VersionInUseError(
                "This template is used by an existing generation and cannot be deleted."
            )

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
