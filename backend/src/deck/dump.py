"""Slide dump (LD-1) -- serialise a template's slides into compact structured
text for the LLM cataloguing call (`deck/catalog.py`).

Replaces `deck/inspect.py`'s layout-walk. That module read `prs.slide_masters
[*].slide_layouts` because the old renderer built slides FROM layouts; the
assessment (`ASSESSMENT-LLM-DECK-PLANNING.md` §1) found the design lives on
the SLIDES, not the layouts -- the masters carry no images at all. So this
walks `prs.slides` instead, and does no classification itself: recognition is
the LLM's job now (§3), this module's only responsibility is turning shapes
into text a model can read.

Compact matters: ~15k tokens for 30 slides is the whole cataloguing budget
(assessment §4). Per-shape text is capped, not because the content matters
(only recognition matters) but because token cost is linear in it and full
paragraphs of body copy add nothing a truncated preview does not already show.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ..core.logging import get_logger

logger = get_logger("orchestrator.deck.dump")

# Per-shape text preview cap. Long enough to recognise "Lorem ipsum dolor sit
# amet" as placeholder body copy or "Q1 2026" as a real heading; long enough
# is all that's needed since the LLM classifies structure, not content.
_TEXT_PREVIEW_CHARS = 200


def _in_or_none(length) -> float | None:
    """python-pptx returns `Length` (EMU) objects with `.inches`, or None when
    a shape inherits geometry rather than setting its own."""
    return round(length.inches, 2) if length is not None else None


@dataclass(frozen=True)
class ShapeDump:
    # Stable within this slide's XML -- survives `deck/clone.py`'s deepcopy
    # untouched (only relationship ids get remapped, never the shape's own
    # id), which is what lets `deck/renderer.py` resolve an anchor by this
    # value AFTER cloning, not just at cataloguing time.
    shape_id: int
    kind: str  # "text" | "picture" | "table" | "chart" | "group" | "other"
    name: str
    left_in: float | None
    top_in: float | None
    width_in: float | None
    height_in: float | None
    # Truncated current text, or None for a shape with nothing to show
    # (a picture, an empty text box, page furniture).
    text: str | None
    is_placeholder: bool
    # Populated only for kind="group" -- a shape's real content can sit
    # several levels down a corporate template's grouped artwork, and
    # `deck/renderer.py` needs the same nesting to resolve an anchor by id
    # regardless of depth (assessment §6 risk table).
    children: tuple["ShapeDump", ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SlideDump:
    slide_index: int
    shapes: tuple[ShapeDump, ...]


def _shape_kind(shape) -> str:
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        return "group"
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        return "picture"
    # has_table/has_chart exist only on GraphicFrame, not the BaseShape every
    # other shape type shares -- absent on anything else, hence getattr.
    if getattr(shape, "has_table", False):
        return "table"
    if getattr(shape, "has_chart", False):
        return "chart"
    if getattr(shape, "has_text_frame", False):
        return "text"
    return "other"


def _preview(text: str) -> str | None:
    stripped = " ".join(text.split())  # collapse newlines/runs of whitespace
    if not stripped:
        return None
    if len(stripped) <= _TEXT_PREVIEW_CHARS:
        return stripped
    return stripped[:_TEXT_PREVIEW_CHARS].rstrip() + "…"


def _dump_shape(shape) -> ShapeDump:
    kind = _shape_kind(shape)
    text = _preview(shape.text_frame.text) if kind == "text" else None
    children = tuple(_dump_shape(child) for child in shape.shapes) if kind == "group" else ()
    return ShapeDump(
        shape_id=shape.shape_id,
        kind=kind,
        name=shape.name,
        left_in=_in_or_none(shape.left),
        top_in=_in_or_none(shape.top),
        width_in=_in_or_none(shape.width),
        height_in=_in_or_none(shape.height),
        text=text,
        is_placeholder=shape.is_placeholder,
        children=children,
    )


def dump_presentation(pptx_bytes: bytes) -> tuple[SlideDump, ...]:
    """Every slide's shapes -- the raw material `deck/catalog.py` sends to the
    LLM. Deliberately does not skip or filter anything (a slide the model
    should catalogue as `unusable` still needs to be SEEN to be judged that
    way, per the assessment's "recognition, not computation" framing)."""
    prs = Presentation(io.BytesIO(pptx_bytes))
    dumps = tuple(
        SlideDump(slide_index=idx, shapes=tuple(_dump_shape(shape) for shape in slide.shapes))
        for idx, slide in enumerate(prs.slides)
    )
    logger.info("presentation_dumped", extra={"slide_count": len(dumps)})
    return dumps


def _render_shape_text(shape: ShapeDump, *, indent: int) -> list[str]:
    pad = "  " * indent
    pos = (
        f"pos=({shape.left_in:g},{shape.top_in:g}) size=({shape.width_in:g},{shape.height_in:g})"
        if None not in (shape.left_in, shape.top_in, shape.width_in, shape.height_in)
        else "pos=(inherited)"
    )
    placeholder = " placeholder" if shape.is_placeholder else ""
    text_part = f' text="{shape.text}"' if shape.text is not None else ""
    lines = [f'{pad}shape {shape.shape_id} [{shape.kind}{placeholder}] "{shape.name}" {pos}{text_part}']
    for child in shape.children:
        lines.extend(_render_shape_text(child, indent=indent + 1))
    return lines


def render_slide_dump_text(dump: SlideDump) -> str:
    """One slide's `ShapeDump` tree -> compact indented text, the unit
    `deck/catalog.py` sends per slide (or batches of slides) to the LLM."""
    lines = [f"SLIDE {dump.slide_index}"]
    for shape in dump.shapes:
        lines.extend(_render_shape_text(shape, indent=1))
    return "\n".join(lines)


def render_presentation_dump_text(dumps: tuple[SlideDump, ...]) -> str:
    return "\n\n".join(render_slide_dump_text(dump) for dump in dumps)
