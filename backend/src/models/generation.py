"""Generation — the presentation build, with full provenance.

Introduced in Slice 2 for the registry immutability invariant; expanded in Slice 3
with the outline link, sources used, artifact URIs, and the consistency report.
RM-11 replaced the engine-bound fields (an engine presentation id, and the
engine request in `params`) with `deck_spec`/`layout_plan` -- rendering is
now local (`deck/renderer.py`), so there is no engine id to carry and no
studio-edit divergence (`TD-24`) to guard against.

LD-9 (`PLAN-LLM-DECK-PLANNING.md`) replaces `deck_spec`/`layout_plan` again,
with a single `deck_plan` -- `deck.plan.DeckPlan.model_dump()`. There is no
separate layout-matching step to record anymore (LD-6: one LLM call plans
content AND design together), so there is nothing left to serialize besides
the plan itself.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPkMixin, utcnow


class GenerationStatus(str, enum.Enum):
    """Every value here is written by a step that genuinely just finished.

    `awaiting_review` (RM-9, D5) is VESTIGIAL as of LD-9: it parked a
    generation whose deterministic layout matcher could not confidently
    place a slide. That matcher is deleted (`deck/matcher.py`, LD-11) -- the
    new pipeline has no per-slide confidence score to gate on, because
    rendering a validated `DeckPlan` is fully deterministic (L5). The
    review gate moved from per-deck to per-template instead (L3: an admin
    reviews a template's catalog once, at onboarding -- `TemplateCatalogStatus`,
    `TemplateService.review_catalog`), which is a stronger guarantee than a
    confidence heuristic ever was. The enum value stays (Postgres cannot drop
    it without the rename/recreate dance `JobType.register_template` already
    avoids for the same reason); nothing sets it on a new generation anymore.
    """

    queued = "queued"
    awaiting_review = "awaiting_review"
    generating = "generating"
    validating = "validating"
    ready = "ready"
    failed = "failed"


class Generation(UuidPkMixin, Base):
    __tablename__ = "generation"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=True
    )
    outline_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # Provenance: the exact registry versions this generation pinned. Nullable
    # because freeform (NotebookLM-style) decks are not governed by a profile.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Sources used + the generation options (tone/verbosity/n_slides/language/
    # export_as -- never engine-internal, RM-11 has no engine to be internal to).
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # `deck.plan.DeckPlan.model_dump(mode="json")` (LD-9) -- ordered
    # `[(design_id, {anchor_id: text})]` plus notes. Content AND design
    # selection in one structure; `generation/worker.py` renders it directly
    # against the pinned template's stored `.pptx`, no separate catalog
    # lookup needed at render time (unlike the old `layout_plan`, this
    # doesn't need re-hydrating against anything -- it's already complete).
    deck_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # MinIO artifact keys (never exposed to clients). `pptx_uri` presence is the
    # resumability key (RM-11) -- rendering is deterministic and local, so
    # "already rendered" is exactly "the artifact already exists".
    pptx_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    consistency_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, name="generation_status"),
        default=GenerationStatus.queued,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
