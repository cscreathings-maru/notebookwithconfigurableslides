"""Unit: deck planning (LD-5/6/7) -- `DesignCatalog` + content -> `DeckPlan`.

Uses the real BRI template's catalog (produced the same way
`test_deck_catalog.py` proves it) as the realistic fixture, plus hand-built
catalogs for the validation edge cases LD-7 names explicitly: an unknown
`design_id`, an unknown `anchor_id`, budget overflow, and a response with
nothing usable at all (the retry path).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.errors import ValidationError
from src.deck.catalog import Anchor, Design, DesignCatalog, catalog_template
from src.deck.dump import dump_presentation
from src.deck.plan import DeckPlan, PlanLlmResult, _validate_slides, plan_deck
from src.registry.house_template import HOUSE_TEMPLATE_PATH
from tests.fakes import FakeLlm


@pytest.fixture(scope="module")
async def bri_catalog() -> DesignCatalog:
    if not HOUSE_TEMPLATE_PATH.exists():
        pytest.fail(f"House template missing: {HOUSE_TEMPLATE_PATH}")
    dumps = dump_presentation(HOUSE_TEMPLATE_PATH.read_bytes())
    catalog, _usage = await catalog_template(dumps=dumps, llm=FakeLlm(), provider_config={})
    return catalog


@pytest.mark.asyncio
async def test_plans_the_real_bri_catalog_end_to_end(bri_catalog: DesignCatalog) -> None:
    content = "Ringkasan eksekutif.\n\nPertumbuhan pendapatan 12% YoY.\n\nRisiko utama."
    llm = FakeLlm()

    plan, usage = await plan_deck(
        content=content,
        catalog=bri_catalog,
        n_slides_hint=None,
        tone="professional",
        density="standard",
        language="Bahasa Indonesia",
        llm=llm,
        provider_config={},
    )

    assert isinstance(plan, DeckPlan)
    assert len(plan.slides) == 3
    assert usage.attempts == 1
    assert "plan_deck" in llm.calls


@pytest.mark.asyncio
async def test_every_slide_references_a_real_usable_design(bri_catalog: DesignCatalog) -> None:
    plan, _usage = await plan_deck(
        content="A.\n\nB.\n\nC.\n\nD.",
        catalog=bri_catalog,
        n_slides_hint=None,
        tone="default",
        density="standard",
        language="English",
        llm=FakeLlm(),
        provider_config={},
    )
    usable_ids = {d.design_id for d in bri_catalog.usable_designs}
    for slide in plan.slides:
        assert slide.design_id in usable_ids


@pytest.mark.asyncio
async def test_every_anchor_id_belongs_to_its_slides_design(bri_catalog: DesignCatalog) -> None:
    plan, _usage = await plan_deck(
        content="A.\n\nB.",
        catalog=bri_catalog,
        n_slides_hint=None,
        tone="default",
        density="standard",
        language="English",
        llm=FakeLlm(),
        provider_config={},
    )
    for slide in plan.slides:
        design = bri_catalog.by_id(slide.design_id)
        assert design is not None
        valid_anchor_ids = {a.anchor_id for a in design.anchors}
        assert set(slide.anchor_texts) <= valid_anchor_ids


@pytest.mark.asyncio
async def test_empty_catalog_is_rejected() -> None:
    empty = DesignCatalog(
        designs=[Design(design_id="slide-0", slide_index=0, role="x", capacity=0, anchors=[], usable=False, reason="no anchors")]
    )
    with pytest.raises(ValidationError):
        await plan_deck(
            content="hi",
            catalog=empty,
            n_slides_hint=None,
            tone="default",
            density="standard",
            language="English",
            llm=FakeLlm(),
            provider_config={},
        )


@pytest.mark.asyncio
async def test_retries_once_then_surfaces_when_nothing_is_ever_usable() -> None:
    """LD-7: a plan that fails validation is regenerated once, then
    surfaced -- never rendered as an empty deck."""
    catalog = DesignCatalog(
        designs=[
            Design(
                design_id="slide-0",
                slide_index=0,
                role="cover",
                capacity=0,
                anchors=[Anchor(anchor_id="1", purpose="title", current_text="x")],
                usable=True,
            )
        ]
    )

    class AlwaysHallucinatingLlm:
        def __init__(self) -> None:
            self.call_count = 0

        async def plan_deck(self, **kwargs: Any) -> PlanLlmResult:
            self.call_count += 1
            # References a design_id that does not exist -- every attempt.
            return PlanLlmResult(
                raw_slides=[{"design_id": "does-not-exist", "anchor_texts": {"1": "x"}}],
                notes=None,
                tokens_in=10,
                tokens_out=5,
            )

    llm = AlwaysHallucinatingLlm()
    with pytest.raises(ValidationError):
        await plan_deck(
            content="hi",
            catalog=catalog,
            n_slides_hint=None,
            tone="default",
            density="standard",
            language="English",
            llm=llm,
            provider_config={},
        )
    assert llm.call_count == 2  # LD-7: exactly one retry, not unbounded


@pytest.mark.asyncio
async def test_recovers_on_the_retry_if_the_second_attempt_is_usable() -> None:
    catalog = DesignCatalog(
        designs=[
            Design(
                design_id="slide-0",
                slide_index=0,
                role="cover",
                capacity=0,
                anchors=[Anchor(anchor_id="1", purpose="title", current_text="x")],
                usable=True,
            )
        ]
    )

    class FailsOnceLlm:
        def __init__(self) -> None:
            self.call_count = 0

        async def plan_deck(self, **kwargs: Any) -> PlanLlmResult:
            self.call_count += 1
            if self.call_count == 1:
                return PlanLlmResult(raw_slides=[{"design_id": "nope"}], notes=None, tokens_in=5, tokens_out=1)
            return PlanLlmResult(
                raw_slides=[{"design_id": "slide-0", "anchor_texts": {"1": "Recovered"}}],
                notes=None,
                tokens_in=10,
                tokens_out=5,
            )

    llm = FailsOnceLlm()
    plan, usage = await plan_deck(
        content="hi",
        catalog=catalog,
        n_slides_hint=None,
        tone="default",
        density="standard",
        language="English",
        llm=llm,
        provider_config={},
    )
    assert len(plan.slides) == 1
    assert plan.slides[0].anchor_texts["1"] == "Recovered"
    assert usage.attempts == 2


def _design(anchor_budget: int | None = None) -> Design:
    return Design(
        design_id="slide-0",
        slide_index=0,
        role="cover",
        capacity=0,
        anchors=[Anchor(anchor_id="1", purpose="title", current_text="x", char_budget=anchor_budget)],
        usable=True,
    )


def test_validate_slides_drops_unknown_design_id() -> None:
    catalog = DesignCatalog(designs=[_design()])
    slides, overflow = _validate_slides(
        [{"design_id": "unknown", "anchor_texts": {"1": "hi"}}], catalog=catalog
    )
    assert slides == []
    assert overflow == []


def test_validate_slides_drops_unknown_anchor_id_but_keeps_known_ones() -> None:
    catalog = DesignCatalog(
        designs=[
            Design(
                design_id="slide-0",
                slide_index=0,
                role="cover",
                capacity=0,
                anchors=[Anchor(anchor_id="1", purpose="title", current_text="x")],
                usable=True,
            )
        ]
    )
    slides, _overflow = _validate_slides(
        [{"design_id": "slide-0", "anchor_texts": {"1": "kept", "999": "dropped"}}], catalog=catalog
    )
    assert len(slides) == 1
    assert slides[0].anchor_texts == {"1": "kept"}


def test_validate_slides_truncates_over_budget_text_and_records_overflow() -> None:
    catalog = DesignCatalog(designs=[_design(anchor_budget=10)])
    slides, overflow = _validate_slides(
        [{"design_id": "slide-0", "anchor_texts": {"1": "this text is way over budget"}}], catalog=catalog
    )
    assert len(slides) == 1
    assert len(slides[0].anchor_texts["1"]) <= 10
    assert len(overflow) == 1
    assert overflow[0].anchor_id == "1"
    assert overflow[0].budget == 10


def test_validate_slides_skips_a_design_used_with_no_anchor_text() -> None:
    catalog = DesignCatalog(designs=[_design()])
    slides, _overflow = _validate_slides(
        [{"design_id": "slide-0", "anchor_texts": {"1": "   "}}], catalog=catalog
    )
    assert slides == []


def test_a_design_can_be_referenced_by_multiple_slides_for_lanjutan_splitting() -> None:
    """L6: a design may be reused any number of times -- overflow content
    splits across repeats rather than being dropped."""
    catalog = DesignCatalog(designs=[_design()])
    raw = [
        {"design_id": "slide-0", "anchor_texts": {"1": "Part 1"}},
        {"design_id": "slide-0", "anchor_texts": {"1": "Part 2 (lanjutan)"}},
    ]
    slides, _overflow = _validate_slides(raw, catalog=catalog)
    assert len(slides) == 2
    assert all(s.design_id == "slide-0" for s in slides)
