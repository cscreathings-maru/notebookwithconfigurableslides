"""Unit: outline -> `DeckPlan`, deterministic, against the real BRI catalog."""

from __future__ import annotations

import pytest

from src.deck.catalog import catalog_template
from src.deck.dump import dump_presentation
from src.deck.from_outline import deck_plan_from_outline
from src.outline.schema import OutlineContent, OutlineSection, TalkingPoint
from src.registry.house_template import HOUSE_TEMPLATE_PATH
from tests.fakes import FakeLlm


@pytest.fixture(scope="module")
async def bri_catalog():
    if not HOUSE_TEMPLATE_PATH.exists():
        pytest.fail(f"House template missing: {HOUSE_TEMPLATE_PATH}")
    dumps = dump_presentation(HOUSE_TEMPLATE_PATH.read_bytes())
    catalog, _usage = await catalog_template(dumps=dumps, llm=FakeLlm(), provider_config={})
    return catalog


def _outline() -> OutlineContent:
    return OutlineContent(
        sections=[
            OutlineSection(id="results", title="Results", order=1),
            OutlineSection(id="intro", title="Introduction", order=0),
        ],
        talking_points=[
            TalkingPoint(section_id="intro", text="Revenue up 12%"),
            TalkingPoint(section_id="results", text="Margin stable"),
            TalkingPoint(section_id="results", text="Costs controlled"),
        ],
    )


def test_first_slide_is_the_deck_title(bri_catalog) -> None:
    plan = deck_plan_from_outline(outline=_outline(), catalog=bri_catalog, deck_title="Q3 Review")
    first_design = bri_catalog.by_id(plan.slides[0].design_id)
    title_anchor = next(a for a in first_design.anchors if a.purpose == "title")
    assert plan.slides[0].anchor_texts[title_anchor.anchor_id] == "Q3 Review"


def test_sections_render_in_order_regardless_of_talking_point_order(bri_catalog) -> None:
    """Section order must hold regardless of how many `(lanjutan)` slides a
    section with many talking points splits into (L6) -- the real BRI
    catalog's chosen content design may have a small capacity, so "Results"
    (2 points) can legitimately split into 2 slides. Ordering is checked on
    the first slide of each section, not a raw title list."""
    plan = deck_plan_from_outline(outline=_outline(), catalog=bri_catalog, deck_title="Q3 Review")
    content_design_id = plan.slides[1].design_id
    content_design = bri_catalog.by_id(content_design_id)
    title_anchor = next(a for a in content_design.anchors if a.purpose == "title")

    titles = [s.anchor_texts.get(title_anchor.anchor_id) for s in plan.slides[1:]]
    first_titles = [t for t in titles if t is not None and not t.endswith("(lanjutan)")]
    assert first_titles == ["Introduction", "Results"]


def test_every_slide_references_a_real_usable_design(bri_catalog) -> None:
    plan = deck_plan_from_outline(outline=_outline(), catalog=bri_catalog, deck_title="Q3 Review")
    usable_ids = {d.design_id for d in bri_catalog.usable_designs}
    for slide in plan.slides:
        assert slide.design_id in usable_ids
        design = bri_catalog.by_id(slide.design_id)
        assert set(slide.anchor_texts) <= {a.anchor_id for a in design.anchors}


def test_section_with_no_talking_points_still_gets_a_slide_with_a_title(bri_catalog) -> None:
    outline = OutlineContent(sections=[OutlineSection(id="empty", title="Empty", order=0)], talking_points=[])
    plan = deck_plan_from_outline(outline=outline, catalog=bri_catalog, deck_title="X")
    content_design = bri_catalog.by_id(plan.slides[1].design_id)
    title_anchor = next(a for a in content_design.anchors if a.purpose == "title")
    assert plan.slides[1].anchor_texts.get(title_anchor.anchor_id) == "Empty"


def test_a_section_with_more_points_than_capacity_splits_with_lanjutan_suffix() -> None:
    """L6: overflow content splits across repeated uses of the same design,
    with a `(lanjutan)`-suffixed continuation title -- built here against a
    hand-crafted single-anchor-capacity catalog so the split is forced
    deterministically, rather than depending on how many item anchors the
    real BRI template's chosen design happens to offer."""
    from src.deck.catalog import Anchor, Design, DesignCatalog

    catalog = DesignCatalog(
        designs=[
            Design(
                design_id="slide-0",
                slide_index=0,
                role="cover",
                capacity=0,
                anchors=[Anchor(anchor_id="1", purpose="title")],
                usable=True,
            ),
            Design(
                design_id="slide-1",
                slide_index=1,
                role="single_point",
                capacity=0,
                anchors=[Anchor(anchor_id="10", purpose="title"), Anchor(anchor_id="11", purpose="body")],
                usable=True,
            ),
        ]
    )
    outline = OutlineContent(
        sections=[OutlineSection(id="s", title="Section", order=0)],
        talking_points=[
            TalkingPoint(section_id="s", text="Point 1"),
            TalkingPoint(section_id="s", text="Point 2"),
        ],
    )
    plan = deck_plan_from_outline(outline=outline, catalog=catalog, deck_title="Deck")

    content_slides = [s for s in plan.slides if s.design_id == "slide-1"]
    assert len(content_slides) == 2
    assert content_slides[0].anchor_texts["10"] == "Section"
    assert content_slides[0].anchor_texts["11"] == "Point 1"
    assert content_slides[1].anchor_texts["10"] == "Section (lanjutan)"
    assert content_slides[1].anchor_texts["11"] == "Point 2"
