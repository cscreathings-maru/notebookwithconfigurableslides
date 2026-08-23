"""The `DesignCatalog` contract and cataloguing orchestration (LD-2).

`deck/dump.py` -> LLM -> `DesignCatalog`. Replaces `deck/inspect.py`'s
geometric `LayoutCatalog`: recognition (what kind of slide is this, which
shapes are content) is the LLM's job now (`ASSESSMENT-LLM-DECK-PLANNING.md`
§3); everything that is actually arithmetic stays in Python, deterministic,
never asked of the model:

- **capacity** is never requested from the LLM -- it "falls out for free"
  (plan §2.1) as the count of distinct `item_<N>_*` anchor groups the model
  identified, computed here.
- **char_budget** is never requested from the LLM either -- it reuses
  `deck/inspect.py`'s own geometry formula (box size -> character capacity),
  keyed by an anchor's `purpose` instead of a placeholder's `kind`, computed
  here from the shape geometry `deck/dump.py` already recorded.

That split matters: the model is asked to do only the part actually hard to
compute (recognition), and never the part that is easy to get wrong by
hallucination (arithmetic on numbers it cannot reliably reproduce).

An anchor whose `anchor_id` does not resolve to a real shape on that slide is
dropped, not kept with a guess -- `deck/renderer.py` resolves anchors by
exactly this id, and a dangling one would render nothing into a broken plan
that looks fine until someone opens the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..core.errors import ValidationError
from ..core.logging import get_logger
from .dump import ShapeDump, SlideDump, render_slide_dump_text

logger = get_logger("orchestrator.deck.catalog")

DESIGN_CATALOG_SCHEMA_VERSION = "1.0"

# Characters of slide dump per LLM call (~4 chars/token). Callers pass
# `settings.deck_catalog_max_chars_per_call` (`workers/tasks.py`); this
# default matches it for direct/test callers.
#
# The whole template used to go in one request. That fits a 32k context on
# paper, but context was never the binding constraint: a 21k-token prompt
# asking a REASONING model to classify 30 slides at once made it spend its
# entire 16k output budget on internal reasoning and return `content: null`
# (production, 2026-08-23). Less asked per call means less to reason about
# per call, which is what keeps the answer inside the budget.
_DEFAULT_MAX_CHARS_PER_CALL = 6000

_ITEM_GROUP_RE = re.compile(r"^item_(\d+)_")

# Reused from `deck/inspect.py`'s character-budget heuristic -- same
# typographic approximations (average glyph width, line height, fill
# factor), now keyed by an anchor's `purpose` rather than a placeholder's
# `kind`, since there is no placeholder type here anymore, only the LLM's
# label.
_AVG_CHAR_WIDTH_EM = 0.50
_LINE_HEIGHT_EM = 1.20
_FILL_FACTOR = 0.85
_DEFAULT_FONT_PT = {
    "title": 32.0,
    "subtitle": 20.0,
    "body": 18.0,
}
_ITEM_TITLE_FONT_PT = 24.0  # a card/bullet-group title runs smaller than the slide title


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_id: str = Field(..., min_length=1)  # the shape id from deck/dump.py, stringified
    current_text: str = ""
    # title | subtitle | body | item_<N>_title | item_<N>_body | visual_caption | other
    purpose: str = Field(..., min_length=1)
    char_budget: int | None = None


class Design(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design_id: str = Field(..., min_length=1)
    slide_index: int = Field(..., ge=0)
    role: str = Field(..., min_length=1)  # the LLM's own label: cover/divider/cards/timeline/...
    capacity: int = Field(default=0, ge=0)  # derived, never LLM-supplied -- see module docstring
    anchors: list[Anchor] = Field(default_factory=list)
    usable: bool = True
    reason: str | None = None  # populated when usable=False

    def anchor(self, anchor_id: str) -> Anchor | None:
        return next((a for a in self.anchors if a.anchor_id == anchor_id), None)


class DesignCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = DESIGN_CATALOG_SCHEMA_VERSION
    designs: list[Design] = Field(..., min_length=1)

    def by_id(self, design_id: str) -> Design | None:
        return next((d for d in self.designs if d.design_id == design_id), None)

    @property
    def usable_designs(self) -> tuple[Design, ...]:
        return tuple(d for d in self.designs if d.usable)


@dataclass
class CatalogUsage:
    tokens_in: int
    tokens_out: int


@dataclass
class CatalogLlmResult:
    """One batch's raw designs -- see `_build_catalog_messages`
    (`engines/llm.py`) for the exact JSON shape requested."""

    raw_designs: list[dict[str, Any]]
    tokens_in: int
    tokens_out: int


class CatalogLlm(Protocol):
    async def catalog_template(
        self,
        *,
        slide_dump_text: str,
        slide_indexes: list[int],
        provider_config: dict[str, Any],
        model_override: str | None = None,
    ) -> CatalogLlmResult: ...


def design_id_for(slide_index: int) -> str:
    return f"slide-{slide_index}"


def _find_shape(shapes: tuple[ShapeDump, ...], shape_id: int) -> ShapeDump | None:
    for shape in shapes:
        if shape.shape_id == shape_id:
            return shape
        if shape.children:
            found = _find_shape(shape.children, shape_id)
            if found is not None:
                return found
    return None


def _font_pt_for_purpose(purpose: str) -> float | None:
    if purpose in _DEFAULT_FONT_PT:
        return _DEFAULT_FONT_PT[purpose]
    if purpose.endswith("_title"):
        return _ITEM_TITLE_FONT_PT
    if purpose.endswith("_body"):
        return _DEFAULT_FONT_PT["body"]
    return None


def _char_budget(*, width_in: float | None, height_in: float | None, purpose: str) -> int | None:
    font_pt = _font_pt_for_purpose(purpose)
    if font_pt is None or not width_in or not height_in or width_in <= 0 or height_in <= 0:
        return None
    char_width_in = font_pt * _AVG_CHAR_WIDTH_EM / 72
    line_height_in = font_pt * _LINE_HEIGHT_EM / 72
    if char_width_in <= 0 or line_height_in <= 0:
        return None
    chars_per_line = width_in / char_width_in
    lines = height_in / line_height_in
    return max(0, int(chars_per_line * lines * _FILL_FACTOR))


def _derive_capacity(anchors: list[Anchor]) -> int:
    """The number of distinct `item_<N>_*` groups -- plan §2.1's "capacity
    falls out of this for free", no geometric grouping (the withdrawn SC-2)."""
    groups = {m.group(1) for a in anchors if (m := _ITEM_GROUP_RE.match(a.purpose))}
    return len(groups)


def _coerce_anchor(raw: Any, *, shapes: tuple[ShapeDump, ...], slide_index: int) -> Anchor | None:
    if not isinstance(raw, dict):
        return None
    anchor_id = str(raw.get("anchor_id") or "").strip()
    purpose = str(raw.get("purpose") or "").strip()
    if not anchor_id or not purpose:
        return None
    try:
        shape = _find_shape(shapes, int(anchor_id))
    except ValueError:
        shape = None
    if shape is None:
        logger.warning(
            "catalog_anchor_dropped_unresolvable",
            extra={"slide_index": slide_index, "anchor_id": anchor_id, "purpose": purpose},
        )
        return None
    return Anchor(
        anchor_id=anchor_id,
        current_text=shape.text or "",
        purpose=purpose,
        char_budget=_char_budget(width_in=shape.width_in, height_in=shape.height_in, purpose=purpose),
    )


def _coerce_design(raw: Any, *, dump: SlideDump) -> Design:
    design_id = design_id_for(dump.slide_index)
    if not isinstance(raw, dict):
        return Design(
            design_id=design_id,
            slide_index=dump.slide_index,
            role="unusable",
            capacity=0,
            anchors=[],
            usable=False,
            reason="LLM returned no classification for this slide",
        )

    role = str(raw.get("role") or "").strip() or "unusable"
    raw_anchors = raw.get("anchors")
    anchors: list[Anchor] = []
    if isinstance(raw_anchors, list):
        for raw_anchor in raw_anchors:
            anchor = _coerce_anchor(raw_anchor, shapes=dump.shapes, slide_index=dump.slide_index)
            if anchor is not None:
                anchors.append(anchor)

    model_says_usable = bool(raw.get("usable", True))
    usable = model_says_usable and bool(anchors)
    reason: str | None = None
    if not usable:
        given_reason = raw.get("reason")
        reason = str(given_reason).strip() if given_reason else None
        if not reason:
            reason = (
                "LLM marked this slide unusable"
                if not model_says_usable
                else "no anchors this renderer can address were identified"
            )

    return Design(
        design_id=design_id,
        slide_index=dump.slide_index,
        role=role,
        capacity=_derive_capacity(anchors),
        anchors=anchors,
        usable=usable,
        reason=reason,
    )


def _batch_by_size(dumps: tuple[SlideDump, ...], max_chars: int) -> list[list[SlideDump]]:
    """Group slides into calls bounded by rendered PROMPT SIZE, not by count.

    Slide sizes within one real template vary by more than 20x -- BRI's cover
    is 341 characters, its 95-shape timeline is 7,960 -- so "N slides per
    call" bounds nothing that matters. Batching by size is what actually
    keeps each request small enough that a model has room to answer.

    A slide larger than `max_chars` on its own is sent alone rather than
    dropped or truncated: a slide is the smallest unit the catalog can
    describe, and losing one would leave a silent hole in the vocabulary.
    """
    batches: list[list[SlideDump]] = []
    current: list[SlideDump] = []
    current_chars = 0

    for dump in dumps:
        size = len(render_slide_dump_text(dump))
        if current and current_chars + size > max_chars:
            batches.append(current)
            current, current_chars = [], 0
        current.append(dump)
        current_chars += size

    if current:
        batches.append(current)
    return batches


async def catalog_template(
    *,
    dumps: tuple[SlideDump, ...],
    llm: CatalogLlm,
    provider_config: dict[str, Any],
    model_override: str | None = None,
    max_chars_per_call: int = _DEFAULT_MAX_CHARS_PER_CALL,
) -> tuple[DesignCatalog, CatalogUsage]:
    """`deck/dump.py` output -> LLM -> validated `DesignCatalog`.

    Never silently drops a slide (`ARCHITECTURE.md` §8): a slide the model
    did not classify, or classified with nothing usable, becomes a `Design`
    with `usable=False` and an honest reason -- visible to the admin review
    (LD-4), never absent from the catalog it is reviewing.
    """
    if not dumps:
        raise ValidationError("Template has no slides to catalogue.")

    designs: list[Design] = []
    tokens_in = tokens_out = 0

    for batch in _batch_by_size(dumps, max_chars_per_call):
        text = "\n\n".join(render_slide_dump_text(d) for d in batch)
        result = await llm.catalog_template(
            slide_dump_text=text,
            slide_indexes=[d.slide_index for d in batch],
            provider_config=provider_config,
            model_override=model_override,
        )
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out

        raw_by_index = {
            raw["slide_index"]: raw
            for raw in result.raw_designs
            if isinstance(raw.get("slide_index"), int)
        }
        for dump in batch:
            designs.append(_coerce_design(raw_by_index.get(dump.slide_index), dump=dump))

    if not any(d.usable for d in designs):
        raise ValidationError(
            "Cataloguing found no usable design in this template -- every slide was "
            "either unclassified or had no anchor a renderer could fill."
        )

    catalog = DesignCatalog(designs=designs)
    logger.info(
        "template_catalogued",
        extra={
            "slide_count": len(designs),
            "usable_count": len(catalog.usable_designs),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        },
    )
    return catalog, CatalogUsage(tokens_in=tokens_in, tokens_out=tokens_out)
