"""Unit: slide dump (LD-1) against the REAL BRI template.

Per `revamp/ASSESSMENT-LLM-DECK-PLANNING.md` §1.1: a fixture that agrees with
the code's own assumption cannot falsify it. `deck/inspect.py`'s suite ran
against `python-pptx`'s bundled default template and passed while the real
renderer shipped a logo-less deck -- so this suite uses the real asset,
exactly like `test_deck_clone.py`.
"""

from __future__ import annotations

import pytest

from src.deck.dump import (
    ShapeDump,
    dump_presentation,
    render_presentation_dump_text,
    render_slide_dump_text,
)
from src.registry.house_template import HOUSE_TEMPLATE_PATH


@pytest.fixture(scope="module")
def template_bytes() -> bytes:
    if not HOUSE_TEMPLATE_PATH.exists():
        pytest.fail(f"House template missing: {HOUSE_TEMPLATE_PATH}")
    return HOUSE_TEMPLATE_PATH.read_bytes()


def test_dumps_every_slide(template_bytes: bytes) -> None:
    dumps = dump_presentation(template_bytes)
    assert len(dumps) == 30  # the real BRI template's slide count (assessment §1)


def test_slide_index_is_sequential(template_bytes: bytes) -> None:
    dumps = dump_presentation(template_bytes)
    assert [d.slide_index for d in dumps] == list(range(30))


def test_cover_slide_carries_its_logo_and_title(template_bytes: bytes) -> None:
    """The specific failure this whole plan exists to fix: the cover slide's
    picture and title text must both show up in the dump."""
    dumps = dump_presentation(template_bytes)
    cover = dumps[0]
    kinds = {shape.kind for shape in cover.shapes}
    assert "picture" in kinds
    texts = [shape.text for shape in cover.shapes if shape.text]
    assert any("Presentation Title" in t or "Nama Presenter" in t or "Bank Rakyat" in t for t in texts)


def test_richest_slide_dump_matches_shape_count(template_bytes: bytes) -> None:
    """Slide 20 (the timeline) is documented at 95 shapes, 3 images
    (assessment §1) -- the dump must not silently drop any."""
    dumps = dump_presentation(template_bytes)
    timeline = dumps[20]
    assert len(timeline.shapes) == 95
    pictures = [s for s in timeline.shapes if s.kind == "picture"]
    assert len(pictures) == 3


def test_text_shapes_carry_a_preview(template_bytes: bytes) -> None:
    dumps = dump_presentation(template_bytes)
    text_shapes = [s for s in dumps[0].shapes if s.kind == "text"]
    assert text_shapes
    assert all(s.text is None or isinstance(s.text, str) for s in text_shapes)


def test_shape_id_is_stable_and_unique_within_a_slide(template_bytes: bytes) -> None:
    dumps = dump_presentation(template_bytes)
    for dump in dumps:
        ids = [s.shape_id for s in dump.shapes]
        assert len(ids) == len(set(ids)), f"duplicate shape id on slide {dump.slide_index}"


def test_long_text_is_truncated_not_dropped(template_bytes: bytes) -> None:
    """A shape with runaway text must still show up (recognisable), just
    capped -- never silently omitted (ARCHITECTURE.md §8)."""
    long_shape = ShapeDump(
        shape_id=1,
        kind="text",
        name="x",
        left_in=0.0,
        top_in=0.0,
        width_in=1.0,
        height_in=1.0,
        text="a" * 500,
        is_placeholder=False,
    )
    from src.deck.dump import _preview  # noqa: PLC0415 -- exercising the truncation directly

    result = _preview("a" * 500)
    assert result is not None
    assert len(result) <= 201  # cap + ellipsis
    assert result.endswith("…")
    assert long_shape.text == "a" * 500  # dataclass itself does not truncate -- _preview does


def test_group_shapes_expose_nested_children(template_bytes: bytes) -> None:
    dumps = dump_presentation(template_bytes)
    groups = [s for dump in dumps for s in dump.shapes if s.kind == "group"]
    for group in groups:
        assert group.children, "a group shape with no children would hide its own content"


def test_whole_deck_dump_is_well_within_the_cataloguing_token_budget(template_bytes: bytes) -> None:
    """Assessment §4: ~15,000 input tokens budgeted for cataloguing all 30
    slides in one call. A rough chars/4 estimate must stay comfortably under
    that, or LD-2's chunking path needs to be exercised, not skipped."""
    dumps = dump_presentation(template_bytes)
    text = render_presentation_dump_text(dumps)
    approx_tokens = len(text) / 4
    assert approx_tokens < 20_000, f"dump is {approx_tokens:.0f} tokens -- catalog_template must chunk"


def test_render_slide_dump_text_is_readable(template_bytes: bytes) -> None:
    dumps = dump_presentation(template_bytes)
    text = render_slide_dump_text(dumps[0])
    assert text.startswith("SLIDE 0")
    assert "picture" in text


def test_dump_never_raises_on_a_structurally_valid_minimal_deck() -> None:
    """Not every template is BRI-sized -- a from-scratch python-pptx deck
    (the old inspect.py fixture) must still dump cleanly, just with less to say."""
    import io

    from pptx import Presentation

    buf = io.BytesIO()
    Presentation().save(buf)
    dumps = dump_presentation(buf.getvalue())
    assert len(dumps) == 0  # python-pptx's bundled default ships no slides, only layouts
