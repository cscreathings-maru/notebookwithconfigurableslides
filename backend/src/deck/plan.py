"""The `DeckPlan` contract and deck planning orchestration (LD-5, LD-6, LD-7).

L4: **one LLM call plans the whole deck** -- order, design per section, text
per anchor. Replaces the two-call pipeline this supersedes (content planning
in the old `deck/planner.py` + layout matching in `deck/matcher.py`): now that
a template's designs are catalogued once, at onboarding
(`deck/catalog.py`), matching content to a design is a much smaller judgement
per generation than matching content to raw template geometry every time
(assessment §2) -- small enough to fold into the same call that writes the
content.

**Why "capacity respected" (LD-7) needs no extra check beyond anchor
membership:** `PlanSlide.anchor_texts` is keyed by `anchor_id` -- a shape id
that must already exist on the chosen design. There is no way for a plan to
"overflow" a design's capacity, because there is no way to address an anchor
the design does not have. Capacity only matters as a PROMPTING concern (L6:
split excess content across repeated uses of the same design, suffixing a
continuation's title `(lanjutan)`) -- the validation that matters is anchor
membership, which is enforced here unconditionally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from ..core.errors import ValidationError
from ..core.logging import get_logger
from .catalog import Design, DesignCatalog

logger = get_logger("orchestrator.deck.plan")

DECK_PLAN_SCHEMA_VERSION = "1.0"

# LD-7: a response with nothing usable is regenerated once, then surfaced --
# never silently rendered as an empty or half-built deck.
_MAX_ATTEMPTS = 2


class PlanSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design_id: str = Field(..., min_length=1)
    anchor_texts: dict[str, str] = Field(..., min_length=1)


class DeckPlan(BaseModel):
    """The planning call's full output for one generation (LD-5)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = DECK_PLAN_SCHEMA_VERSION
    slides: list[PlanSlide] = Field(..., min_length=1)
    # The model's own free-text commentary (e.g. "content ran long, split
    # across two cards slides") -- never written into the rendered deck,
    # surfaced to an operator/admin the way `deck/planner.py`'s overflow
    # notes are.
    notes: str | None = None


@dataclass(frozen=True)
class OverflowNote:
    slide_index: int
    design_id: str
    anchor_id: str
    budget: int
    original_length: int


@dataclass
class PlanUsage:
    tokens_in: int
    tokens_out: int
    overflow: tuple[OverflowNote, ...]
    attempts: int


@dataclass
class PlanLlmResult:
    """Raw slides proposed by the model -- see `_build_catalog_plan_messages`
    (`engines/llm.py`) for the exact JSON shape requested."""

    raw_slides: list[dict[str, Any]]
    notes: str | None
    tokens_in: int
    tokens_out: int


class PlanLlm(Protocol):
    async def plan_deck(
        self,
        *,
        content: str,
        catalog: list[dict[str, Any]],
        n_slides_hint: int | None,
        tone: str,
        density: str,
        language: str,
        provider_config: dict[str, Any],
        model_override: str | None = None,
    ) -> PlanLlmResult: ...


def _compact_catalog(designs: tuple[Design, ...]) -> list[dict[str, Any]]:
    """The prompt's view of the catalog -- role, capacity, and each anchor's
    id/purpose/budget. Deliberately omits `current_text`: the model needs to
    know WHERE it can write and how much fits, never what placeholder copy
    used to say there (that would just be noise it might echo back)."""
    return [
        {
            "design_id": d.design_id,
            "role": d.role,
            "capacity": d.capacity,
            "anchors": [
                {"anchor_id": a.anchor_id, "purpose": a.purpose, "char_budget": a.char_budget}
                for a in d.anchors
            ],
        }
        for d in designs
    ]


def _truncate_at_word_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip()
    return cut or text[:limit]


def _validate_slides(
    raw_slides: list[dict[str, Any]], *, catalog: DesignCatalog
) -> tuple[list[PlanSlide], list[OverflowNote]]:
    """Coerces a not-fully-trusted response into slides that are guaranteed
    renderable: an unknown/unusable `design_id` drops the slide; an unknown
    `anchor_id` drops just that anchor; text beyond a budget is truncated at
    a word boundary and recorded, never silently accepted or silently
    dropped whole. Only a response with NOTHING usable produces an empty
    result -- the caller's retry (LD-7) is what happens next."""
    overflow: list[OverflowNote] = []
    slides: list[PlanSlide] = []

    for idx, raw in enumerate(raw_slides):
        if not isinstance(raw, dict):
            continue
        design_id = str(raw.get("design_id") or "").strip()
        design = catalog.by_id(design_id)
        if design is None or not design.usable:
            logger.warning(
                "deck_plan_slide_rejected_unknown_design",
                extra={"slide_index": idx, "design_id": design_id},
            )
            continue

        raw_texts = raw.get("anchor_texts")
        if not isinstance(raw_texts, dict):
            continue

        anchor_texts: dict[str, str] = {}
        for raw_anchor_id, raw_text in raw_texts.items():
            anchor = design.anchor(str(raw_anchor_id))
            if anchor is None:
                logger.warning(
                    "deck_plan_anchor_rejected_unknown",
                    extra={"slide_index": idx, "design_id": design_id, "anchor_id": str(raw_anchor_id)},
                )
                continue
            text = str(raw_text or "").strip()
            if not text:
                continue
            if anchor.char_budget is not None and len(text) > anchor.char_budget:
                overflow.append(
                    OverflowNote(
                        slide_index=idx,
                        design_id=design_id,
                        anchor_id=anchor.anchor_id,
                        budget=anchor.char_budget,
                        original_length=len(text),
                    )
                )
                text = _truncate_at_word_boundary(text, anchor.char_budget)
            anchor_texts[anchor.anchor_id] = text

        if not anchor_texts:
            continue  # nothing to render for this slide -- skip it, not an empty clone

        try:
            slides.append(PlanSlide(design_id=design_id, anchor_texts=anchor_texts))
        except PydanticValidationError as exc:
            logger.warning("deck_plan_slide_invalid", extra={"slide_index": idx, "error": str(exc)})
            continue

    return slides, overflow


async def plan_deck(
    *,
    content: str,
    catalog: DesignCatalog,
    n_slides_hint: int | None,
    tone: str,
    density: str,
    language: str,
    llm: PlanLlm,
    provider_config: dict[str, Any],
    model_override: str | None = None,
) -> tuple[DeckPlan, PlanUsage]:
    """Content + catalog -> validated `DeckPlan`, one call (LD-6), retried
    once on a wholly-unusable response before surfacing failure (LD-7, G7).
    """
    usable = catalog.usable_designs
    if not usable:
        raise ValidationError(
            "Template has no usable design to plan against -- cataloguing "
            "should have caught this (DesignCatalog.usable_designs)."
        )
    catalog_brief = _compact_catalog(usable)

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        result = await llm.plan_deck(
            content=content,
            catalog=catalog_brief,
            n_slides_hint=n_slides_hint,
            tone=tone,
            density=density,
            language=language,
            provider_config=provider_config,
            model_override=model_override,
        )
        slides, overflow = _validate_slides(result.raw_slides, catalog=catalog)
        if slides:
            plan = DeckPlan(slides=slides, notes=result.notes)
            usage = PlanUsage(
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                overflow=tuple(overflow),
                attempts=attempt,
            )
            return plan, usage
        logger.warning(
            "deck_plan_attempt_produced_nothing_usable",
            extra={"attempt": attempt, "max_attempts": _MAX_ATTEMPTS},
        )

    raise ValidationError(
        "Could not build a valid deck plan from the model's response, even after a retry."
    )
