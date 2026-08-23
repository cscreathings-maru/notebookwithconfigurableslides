"""Unit: template cataloguing (LD-2) -- `deck/dump.py` output -> `DesignCatalog`.

Exercises the orchestration (`deck/catalog.py::catalog_template`) against the
real BRI template's dump via `FakeLlm.catalog_template` (deterministic-shape,
no network) plus a set of hand-built raw-response tests that pin the parts
that must NEVER trust the model: `capacity` and `char_budget` are computed in
Python, not requested from the LLM (module docstring).
"""

from __future__ import annotations

import pytest

from src.core.errors import ValidationError
from src.deck.catalog import (
    Anchor,
    Design,
    DesignCatalog,
    _char_budget,
    _coerce_design,
    _derive_capacity,
    catalog_template,
    design_id_for,
)
from src.deck.dump import ShapeDump, SlideDump, dump_presentation
from src.registry.house_template import HOUSE_TEMPLATE_PATH
from tests.fakes import FakeLlm


@pytest.fixture(scope="module")
def bri_dumps() -> tuple:
    if not HOUSE_TEMPLATE_PATH.exists():
        pytest.fail(f"House template missing: {HOUSE_TEMPLATE_PATH}")
    return dump_presentation(HOUSE_TEMPLATE_PATH.read_bytes())


@pytest.mark.asyncio
async def test_catalogues_every_slide_of_the_real_template(bri_dumps: tuple) -> None:
    llm = FakeLlm()
    catalog, usage = await catalog_template(dumps=bri_dumps, llm=llm, provider_config={})
    assert len(catalog.designs) == 30
    assert {d.slide_index for d in catalog.designs} == set(range(30))
    assert usage.tokens_in > 0
    assert "catalog_template" in llm.calls


@pytest.mark.asyncio
async def test_cover_slide_is_usable_with_a_title_anchor(bri_dumps: tuple) -> None:
    llm = FakeLlm()
    catalog, _ = await catalog_template(dumps=bri_dumps, llm=llm, provider_config={})
    cover = catalog.by_id(design_id_for(0))
    assert cover is not None
    assert cover.usable is True
    assert any(a.purpose == "title" for a in cover.anchors)


@pytest.mark.asyncio
async def test_a_slide_with_no_text_is_marked_unusable_with_a_reason() -> None:
    """A pure-decoration slide (assessment §1's slide 29: a 39-image logo
    library, nothing to replace) must surface as `usable=False`, never
    silently dropped from the catalog -- exercised through the full
    orchestration, not just `_coerce_design` directly."""
    logo_library = SlideDump(
        slide_index=0,
        shapes=(
            ShapeDump(
                shape_id=1,
                kind="picture",
                name="logo 1",
                left_in=0.0,
                top_in=0.0,
                width_in=1.0,
                height_in=1.0,
                text=None,
                is_placeholder=False,
            ),
        ),
    )
    cover = SlideDump(
        slide_index=1,
        shapes=(
            ShapeDump(
                shape_id=2,
                kind="text",
                name="title",
                left_in=0.5,
                top_in=0.5,
                width_in=5.0,
                height_in=1.0,
                text="Presentation Title",
                is_placeholder=True,
            ),
        ),
    )
    llm = FakeLlm()
    catalog, _ = await catalog_template(dumps=(logo_library, cover), llm=llm, provider_config={})
    unusable = [d for d in catalog.designs if not d.usable]
    assert unusable, "expected at least one design with nothing to replace"
    for design in unusable:
        assert design.reason


@pytest.mark.asyncio
async def test_capacity_is_never_taken_from_the_llm(bri_dumps: tuple) -> None:
    """Even if the fake supplied a `capacity` field, catalog_template must
    ignore it -- capacity is derived from anchors (plan §2.1)."""

    class LyingLlm(FakeLlm):
        async def catalog_template(self, *, slide_dump_text, slide_indexes, provider_config, model_override=None):
            result = await super().catalog_template(
                slide_dump_text=slide_dump_text,
                slide_indexes=slide_indexes,
                provider_config=provider_config,
                model_override=model_override,
            )
            for raw in result.raw_designs:
                raw["capacity"] = 999  # a field the schema does not even define
            return result

    catalog, _ = await catalog_template(dumps=bri_dumps, llm=LyingLlm(), provider_config={})
    assert all(d.capacity != 999 for d in catalog.designs)


@pytest.mark.asyncio
async def test_empty_template_is_rejected() -> None:
    with pytest.raises(ValidationError):
        await catalog_template(dumps=(), llm=FakeLlm(), provider_config={})


@pytest.mark.asyncio
async def test_chunking_splits_across_multiple_llm_calls(bri_dumps: tuple) -> None:
    llm = FakeLlm()
    catalog, _ = await catalog_template(
        dumps=bri_dumps, llm=llm, provider_config={}, max_chars_per_call=20_000
    )
    assert len(catalog.designs) == 30
    # 48k characters of dump cannot fit in 20k-character calls.
    assert llm.calls.count("catalog_template") >= 3


@pytest.mark.asyncio
async def test_the_default_batch_keeps_every_prompt_small(bri_dumps: tuple) -> None:
    """The whole template in one call built a 21k-token prompt, and asking a
    reasoning model to classify 30 slides at once made it spend its entire
    output budget thinking (production, 2026-08-23). Reasoning scales with
    how much is asked at once, so the guarantee that matters is per-CALL
    size, not total size."""

    class SizeRecordingLlm(FakeLlm):
        def __init__(self) -> None:
            super().__init__()
            self.prompt_chars: list[int] = []

        async def catalog_template(self, *, slide_dump_text, slide_indexes, provider_config, model_override=None):
            self.prompt_chars.append(len(slide_dump_text))
            return await super().catalog_template(
                slide_dump_text=slide_dump_text,
                slide_indexes=slide_indexes,
                provider_config=provider_config,
                model_override=model_override,
            )

    limit = 6000
    llm = SizeRecordingLlm()
    catalog, _ = await catalog_template(
        dumps=bri_dumps, llm=llm, provider_config={}, max_chars_per_call=limit
    )

    assert len(catalog.designs) == 30, "chunking must not lose a slide"
    assert len(llm.prompt_chars) > 1, "the default must actually chunk, not send one giant call"

    # Every call is inside the limit, except one holding a single slide that
    # exceeds it alone (BRI's 7,960-char timeline) -- a slide cannot be split.
    single_slide_calls = [n for n, size in enumerate(llm.prompt_chars) if size > limit]
    assert len(single_slide_calls) <= 1, "only an oversized SINGLE slide may exceed the limit"
    assert max(llm.prompt_chars) < 2 * limit, "no call may be wildly over the limit"


@pytest.mark.asyncio
async def test_batches_run_concurrently_not_one_after_another(bri_dumps: tuple) -> None:
    """Nine sequential calls at ~80s each ran past the worker's job timeout
    and the whole catalogue was lost (production, 2026-08-23). The batches
    are independent, so they must overlap rather than queue."""
    import asyncio

    class SlowLlm(FakeLlm):
        def __init__(self) -> None:
            super().__init__()
            self.in_flight = 0
            self.peak_in_flight = 0

        async def catalog_template(self, *, slide_dump_text, slide_indexes, provider_config, model_override=None):
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            try:
                await asyncio.sleep(0.02)  # stand in for a slow provider
                return await super().catalog_template(
                    slide_dump_text=slide_dump_text,
                    slide_indexes=slide_indexes,
                    provider_config=provider_config,
                    model_override=model_override,
                )
            finally:
                self.in_flight -= 1

    llm = SlowLlm()
    catalog, _ = await catalog_template(dumps=bri_dumps, llm=llm, provider_config={}, concurrency=4)

    assert len(catalog.designs) == 30
    assert llm.peak_in_flight > 1, "batches ran strictly one after another"
    assert llm.peak_in_flight <= 4, "concurrency limit was not respected"


@pytest.mark.asyncio
async def test_concurrency_one_still_works(bri_dumps: tuple) -> None:
    """The sequential path stays valid -- an operator throttling a rate-limited
    provider must not lose correctness for it."""
    llm = FakeLlm()
    catalog, _ = await catalog_template(dumps=bri_dumps, llm=llm, provider_config={}, concurrency=1)
    assert len(catalog.designs) == 30


@pytest.mark.asyncio
async def test_designs_stay_in_slide_order_regardless_of_completion_order(bri_dumps: tuple) -> None:
    """Concurrency must not reorder the catalog: the admin reviews it against
    the deck, slide 1 first."""
    import asyncio
    import random

    class JitteryLlm(FakeLlm):
        async def catalog_template(self, *, slide_dump_text, slide_indexes, provider_config, model_override=None):
            await asyncio.sleep(random.uniform(0, 0.03))  # noqa: S311 -- test jitter, not crypto
            return await super().catalog_template(
                slide_dump_text=slide_dump_text,
                slide_indexes=slide_indexes,
                provider_config=provider_config,
                model_override=model_override,
            )

    catalog, _ = await catalog_template(dumps=bri_dumps, llm=JitteryLlm(), provider_config={}, concurrency=4)
    assert [d.slide_index for d in catalog.designs] == list(range(30))


def test_derive_capacity_counts_distinct_item_groups() -> None:
    anchors = [
        Anchor(anchor_id="1", purpose="item_1_title"),
        Anchor(anchor_id="2", purpose="item_1_body"),
        Anchor(anchor_id="3", purpose="item_2_title"),
        Anchor(anchor_id="4", purpose="item_2_body"),
        Anchor(anchor_id="5", purpose="title"),  # not an item group
    ]
    assert _derive_capacity(anchors) == 2


def test_char_budget_scales_with_box_area() -> None:
    small = _char_budget(width_in=1.0, height_in=0.3, purpose="body")
    large = _char_budget(width_in=9.0, height_in=4.5, purpose="body")
    assert small is not None and large is not None
    assert large > small


def test_char_budget_none_for_unbudgeted_purpose() -> None:
    assert _char_budget(width_in=5.0, height_in=2.0, purpose="visual_caption") is None
    assert _char_budget(width_in=5.0, height_in=2.0, purpose="other") is None


def test_char_budget_none_without_geometry() -> None:
    assert _char_budget(width_in=None, height_in=None, purpose="body") is None


def _dump_with_shapes(*shapes: ShapeDump) -> SlideDump:
    return SlideDump(slide_index=0, shapes=tuple(shapes))


def test_anchor_referencing_missing_shape_is_dropped() -> None:
    dump = _dump_with_shapes(
        ShapeDump(
            shape_id=1,
            kind="text",
            name="a",
            left_in=0.5,
            top_in=0.5,
            width_in=5.0,
            height_in=1.0,
            text="Real title",
            is_placeholder=True,
        )
    )
    raw = {
        "slide_index": 0,
        "role": "cover",
        "usable": True,
        "anchors": [
            {"anchor_id": "1", "purpose": "title"},
            {"anchor_id": "999", "purpose": "body"},  # does not exist on this slide
        ],
    }
    design = _coerce_design(raw, dump=dump)
    assert len(design.anchors) == 1
    assert design.anchors[0].anchor_id == "1"


def test_anchor_current_text_comes_from_the_dump_not_the_model() -> None:
    dump = _dump_with_shapes(
        ShapeDump(
            shape_id=7,
            kind="text",
            name="a",
            left_in=0.5,
            top_in=0.5,
            width_in=5.0,
            height_in=1.0,
            text="Actual slide text",
            is_placeholder=True,
        )
    )
    raw = {
        "slide_index": 0,
        "role": "cover",
        "usable": True,
        "anchors": [{"anchor_id": "7", "purpose": "title", "current_text": "hallucinated text"}],
    }
    design = _coerce_design(raw, dump=dump)
    assert design.anchors[0].current_text == "Actual slide text"


def test_design_with_no_anchors_is_unusable_even_if_model_says_usable() -> None:
    dump = _dump_with_shapes(
        ShapeDump(
            shape_id=1,
            kind="picture",
            name="logo",
            left_in=0.0,
            top_in=0.0,
            width_in=1.0,
            height_in=1.0,
            text=None,
            is_placeholder=False,
        )
    )
    raw = {"slide_index": 0, "role": "logo_library", "usable": True, "anchors": []}
    design = _coerce_design(raw, dump=dump)
    assert design.usable is False
    assert design.reason


def test_design_catalog_round_trips_through_json() -> None:
    catalog = DesignCatalog(
        designs=[
            Design(
                design_id="slide-0",
                slide_index=0,
                role="cover",
                capacity=0,
                anchors=[Anchor(anchor_id="1", purpose="title", current_text="Hi")],
                usable=True,
            )
        ]
    )
    data = catalog.model_dump(mode="json")
    restored = DesignCatalog.model_validate(data)
    assert restored == catalog
