"""Outline -> `DeckPlan`, deterministically (LD-9's adaptation of RM-11's idea).

No LLM call: an outline's structure (section order, titles, talking points)
is already fixed by the time this runs -- the governed path fixed it via
`profile.section_structure`, a confirmed freeform outline fixed it when the
user confirmed the draft. Re-deriving it through `deck/plan.py`'s LLM call
would be both wasteful and a chance to drift from what was actually reviewed.

Design SELECTION has no fixed vocabulary to key off anymore (`deck/catalog.py`'s
`role` is a free-text LLM label, not the old `LayoutRole` enum) -- this picks
designs by ANCHOR SHAPE instead: a design with a `title`-purpose anchor and
no substantial body anchors is the cover; a design with `body`/`item_N_body`
anchors is content. That is a structural property every catalogued design
carries regardless of what the model happened to call its `role`.
"""

from __future__ import annotations

from ..core.errors import ValidationError
from ..outline.schema import OutlineContent
from .catalog import Anchor, Design, DesignCatalog
from .plan import DeckPlan, PlanSlide


def _title_anchor(design: Design) -> Anchor | None:
    return next((a for a in design.anchors if a.purpose == "title"), None)


def _content_anchors(design: Design) -> list[Anchor]:
    """The anchors that hold a section's talking points, in reading order --
    `item_N_body` groups (cards, bullet rows) if present, else a plain
    `body` anchor. Never both: a design's content capacity is one or the
    other, per `deck/catalog.py`'s vocabulary."""
    items = sorted(
        (a for a in design.anchors if a.purpose.startswith("item_") and a.purpose.endswith("_body")),
        key=lambda a: a.purpose,
    )
    if items:
        return items
    return [a for a in design.anchors if a.purpose == "body"]


def _pick_cover_design(usable: tuple[Design, ...]) -> Design:
    """Prefers a design whose role NAMES it a cover/title slide; falls back
    to any design with a title and no content capacity (a divider-shaped
    slide is the next-closest thing to a cover); falls back to the first
    usable design outright -- cataloguing guarantees at least one exists."""
    for d in usable:
        if any(hint in d.role.lower() for hint in ("cover", "title")):
            return d
    for d in usable:
        if _title_anchor(d) is not None and not _content_anchors(d):
            return d
    return usable[0]


def _pick_content_design(usable: tuple[Design, ...], *, exclude_id: str) -> Design:
    others_with_content = [d for d in usable if d.design_id != exclude_id and _content_anchors(d)]
    if others_with_content:
        return others_with_content[0]
    any_with_content = [d for d in usable if _content_anchors(d)]
    if any_with_content:
        return any_with_content[0]
    return usable[0]


def deck_plan_from_outline(*, outline: OutlineContent, catalog: DesignCatalog, deck_title: str) -> DeckPlan:
    """One title slide (`deck_title`) followed by one content slide per
    outline section, in order, with that section's talking points as its
    content. A section with more points than the chosen design's capacity
    holds splits across repeated uses of the SAME design (L6), continuation
    titles suffixed `(lanjutan)` -- mirrors what `deck/plan.py`'s LLM path is
    instructed to do, done here without a model since the structure is
    already fixed.
    """
    usable = catalog.usable_designs
    if not usable:
        raise ValidationError("Template has no usable design to build a deck from.")

    cover = _pick_cover_design(usable)
    content_design = _pick_content_design(usable, exclude_id=cover.design_id)
    content_anchors = _content_anchors(content_design)
    content_title_anchor = _title_anchor(content_design)
    chunk_size = max(len(content_anchors), 1)

    points_by_section: dict[str, list[str]] = {}
    for tp in outline.talking_points:
        points_by_section.setdefault(tp.section_id, []).append(tp.text)

    slides: list[PlanSlide] = []

    cover_title_anchor = _title_anchor(cover)
    if cover_title_anchor is not None:
        slides.append(PlanSlide(design_id=cover.design_id, anchor_texts={cover_title_anchor.anchor_id: deck_title}))

    for section in sorted(outline.sections, key=lambda s: s.order):
        points = points_by_section.get(section.id, [])
        chunks = [points[i : i + chunk_size] for i in range(0, len(points), chunk_size)] or [[]]
        for chunk_index, chunk in enumerate(chunks):
            anchor_texts: dict[str, str] = {}
            if content_title_anchor is not None:
                title_text = section.title if chunk_index == 0 else f"{section.title} (lanjutan)"
                anchor_texts[content_title_anchor.anchor_id] = title_text
            for anchor, text in zip(content_anchors, chunk, strict=False):
                anchor_texts[anchor.anchor_id] = text
            if anchor_texts:
                slides.append(PlanSlide(design_id=content_design.design_id, anchor_texts=anchor_texts))

    if not slides:
        raise ValidationError("Could not build any slide from this outline against the template's catalog.")

    return DeckPlan(slides=slides, notes=None)
