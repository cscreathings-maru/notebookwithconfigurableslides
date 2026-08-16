"""Generation worker core — render the deck, enforce consistency.

Idempotent: a ready generation is a no-op. Resumable: `pptx_uri` presence IS
the resumability key (RM-11) -- rendering is local and deterministic
(`deck/renderer.py`, no network, no LLM), so "already rendered" is exactly
"the artifact already exists", with no engine-side id to track separately.
A failed consistency check blocks publication (status=failed) but never
leaves a corrupt/half-written ready state.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..deck.plan import DeckPlan
from ..deck.renderer import render_deck
from ..models import Generation, GenerationStatus
from ..registry.repository import ProfileRepository, TemplateRepository
from ..storage.object_store import ObjectStore
from .artifact import inspect_pptx
from .consistency import check_consistency
from .repository import GenerationRepository

logger = get_logger("orchestrator.generation.worker")

_PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _artifact_key(tenant_id: uuid.UUID, gen: Generation, ext: str) -> str:
    return f"{tenant_id.hex}/{gen.project_id.hex}/generations/{gen.id.hex}/deck.{ext}"


async def generate_presentation(
    *,
    db: Session,
    generation_id: uuid.UUID,
    tenant_id: uuid.UUID,
    object_store: ObjectStore,
) -> None:
    repo = GenerationRepository(db, tenant_id)
    gen = repo.get(generation_id)

    if gen.status is GenerationStatus.ready:
        logger.info("generation_noop_already_ready", extra={"generation_id": str(generation_id)})
        return

    gen.status = GenerationStatus.generating
    gen.error = None
    db.add(gen)
    db.flush()

    if not gen.pptx_uri:
        template = None
        if gen.template_id is not None:
            template = TemplateRepository(db, tenant_id).get_version(gen.template_id, gen.template_version)

        if template is None or not template.source_pptx_uri:
            gen.status = GenerationStatus.failed
            gen.error = "Pinned template is no longer available, or has no stored .pptx to render from."
            db.add(gen)
            db.flush()
            logger.warning("generation_template_unavailable", extra={"generation_id": str(generation_id)})
            return

        plan = DeckPlan.model_validate(gen.deck_plan)
        template_bytes = object_store.get_bytes(key=template.source_pptx_uri)

        deck_bytes = render_deck(plan=plan, template_pptx=template_bytes)

        pptx_key = _artifact_key(tenant_id, gen, "pptx")
        object_store.put_bytes(key=pptx_key, data=deck_bytes, content_type=_PPTX_TYPE)
        gen.pptx_uri = pptx_key
        db.add(gen)
        db.flush()

    # Freeform (NotebookLM) decks have no governing profile — there is nothing to
    # check consistency against, so publish once the artifact exists.
    if gen.profile_id is None:
        gen.status = GenerationStatus.ready
        gen.consistency_report = {"passed": True, "checks": [], "mode": "freeform"}
        gen.error = None
        db.add(gen)
        db.flush()
        logger.info(
            "generation_finished",
            extra={"generation_id": str(generation_id), "status": gen.status.value},
        )
        return

    # Consistency gate — judge the deck that was actually produced, not the plan.
    gen.status = GenerationStatus.validating
    db.add(gen)
    db.flush()

    profile = ProfileRepository(db, tenant_id).get_version(gen.profile_id, gen.profile_version)
    deck = inspect_pptx(object_store.get_bytes(key=gen.pptx_uri)) if gen.pptx_uri else None
    report = check_consistency(
        profile=profile,
        deck=deck,
        # A real template is always applied now -- rendering refuses to run
        # at all without one (see the availability check above), so there is
        # no "stock theme" case left to distinguish.
        template_applied=True,
    )
    gen.consistency_report = report
    if report["passed"]:
        gen.status = GenerationStatus.ready
        gen.error = None
    else:
        gen.status = GenerationStatus.failed
        gen.error = "Consistency check failed; deck flagged for review."
    db.add(gen)
    db.flush()
    logger.info(
        "generation_finished",
        extra={"generation_id": str(generation_id), "status": gen.status.value},
    )
