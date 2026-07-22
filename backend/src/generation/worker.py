"""Generation worker core — call Presenton, store artifacts, enforce consistency.

Idempotent: a ready generation is a no-op. Resumable: artifacts are produced and
persisted before the generation is marked ready, and a generation that already has a
Presenton presentation id is not regenerated. A failed consistency check blocks
publication (status=failed) but never leaves a corrupt/half-written ready state.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..models import Generation, GenerationStatus
from ..registry.repository import ProfileRepository
from ..storage.object_store import ObjectStore
from .artifact import inspect_pptx
from .consistency import check_consistency
from .repository import GenerationRepository

logger = get_logger("orchestrator.generation.worker")

_PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_PDF_TYPE = "application/pdf"


def _artifact_key(tenant_id: uuid.UUID, gen: Generation, ext: str) -> str:
    return f"{tenant_id.hex}/{gen.project_id.hex}/generations/{gen.id.hex}/deck.{ext}"


async def generate_presentation(
    *,
    db: Session,
    generation_id: uuid.UUID,
    tenant_id: uuid.UUID,
    presenton,
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

    # Produce + persist artifacts (skip if a prior attempt already did — resumable).
    if not gen.presenton_presentation_id:
        result = await presenton.generate(params=gen.params)
        gen.presenton_presentation_id = result["presentation_id"]

        pptx_bytes = await presenton.download(path=result["path"])
        pptx_key = _artifact_key(tenant_id, gen, "pptx")
        object_store.put_bytes(key=pptx_key, data=pptx_bytes, content_type=_PPTX_TYPE)
        gen.pptx_uri = pptx_key

        pdf = await presenton.export(
            presentation_id=gen.presenton_presentation_id, target_format="pdf"
        )
        pdf_bytes = await presenton.download(path=pdf["path"])
        pdf_key = _artifact_key(tenant_id, gen, "pdf")
        object_store.put_bytes(key=pdf_key, data=pdf_bytes, content_type=_PDF_TYPE)
        gen.pdf_uri = pdf_key

        db.add(gen)
        db.flush()

    # Freeform (NotebookLM) decks have no governing profile — there is nothing to
    # check consistency against, so publish once artifacts exist.
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
        # A template was applied iff one was requested and the engine returned a deck.
        template_applied=bool(gen.params.get("template")) and bool(gen.presenton_presentation_id),
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
