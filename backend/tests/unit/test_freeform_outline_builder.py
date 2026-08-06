"""DG-1: build_freeform_outline — no profile, the LLM proposes structure itself.

Unlike the governed path (test_outline_determinism.py), structure here comes FROM
the model's response, not from a fixed section_structure -- these tests assert the
mapping from the model's raw {"title", "bullets"} shape into a valid OutlineContent,
and that a malformed/empty draft fails loudly rather than silently.
"""

from __future__ import annotations

import pytest

from src.core.errors import ValidationError
from src.outline.builder import FreeformOutlineLlmResult, build_freeform_outline


class _StubLlm:
    """Returns exactly the sections handed to it -- the builder's mapping is what's
    under test here, not any particular model's judgement."""

    def __init__(self, sections: list[dict]) -> None:
        self._sections = sections
        self.calls: list[dict] = []

    async def draft_outline(
        self, *, content, tone, density, n_slides_hint, language, provider_config
    ):
        self.calls.append(
            {
                "content": content,
                "tone": tone,
                "density": density,
                "n_slides_hint": n_slides_hint,
                "language": language,
            }
        )
        return FreeformOutlineLlmResult(sections=self._sections, tokens_in=42, tokens_out=17)


async def test_maps_model_sections_and_bullets_into_a_valid_outline() -> None:
    llm = _StubLlm(
        [
            {"title": "Overview", "bullets": ["Revenue grew 12%", "Costs stable"]},
            {"title": "Risks", "bullets": ["Supply chain"]},
        ]
    )

    content, usage = await build_freeform_outline(
        content="Revenue grew 12%. Costs stable. Supply chain is a risk.",
        tone="professional",
        density="standard",
        n_slides_hint=None,
        language="English",
        llm=llm,
        provider_config={"provider": "deepseek"},
    )

    assert [s.title for s in content.sections] == ["Overview", "Risks"]
    assert [s.order for s in content.sections] == [0, 1]
    overview_id = content.sections[0].id
    assert [tp.text for tp in content.talking_points if tp.section_id == overview_id] == [
        "Revenue grew 12%",
        "Costs stable",
    ]
    assert usage.tokens_in == 42 and usage.tokens_out == 17


async def test_passes_the_advanced_knobs_and_hint_through_to_the_llm() -> None:
    llm = _StubLlm([{"title": "A", "bullets": []}])

    await build_freeform_outline(
        content="x",
        tone="funny",
        density="text-heavy",
        n_slides_hint=6,
        language="Bahasa Indonesia",
        llm=llm,
        provider_config={},
    )

    assert llm.calls[0]["tone"] == "funny"
    assert llm.calls[0]["density"] == "text-heavy"
    assert llm.calls[0]["n_slides_hint"] == 6
    assert llm.calls[0]["language"] == "Bahasa Indonesia"


async def test_duplicate_titles_get_disambiguated_ids() -> None:
    llm = _StubLlm(
        [
            {"title": "Overview", "bullets": ["a"]},
            {"title": "Overview", "bullets": ["b"]},
        ]
    )

    content, _usage = await build_freeform_outline(
        content="x", tone="default", density="standard", n_slides_hint=None,
        language="English", llm=llm, provider_config={},
    )

    ids = [s.id for s in content.sections]
    assert len(ids) == len(set(ids)), "duplicate section ids would fail validate_outline"


async def test_blank_or_malformed_sections_are_dropped_not_crashed_on() -> None:
    llm = _StubLlm(
        [
            {"title": "", "bullets": ["orphaned, no title"]},
            "not even a dict",
            {"title": "Real Section", "bullets": [123, None, "  ", "Kept"]},
        ]
    )

    content, _usage = await build_freeform_outline(
        content="x", tone="default", density="standard", n_slides_hint=None,
        language="English", llm=llm, provider_config={},
    )

    assert [s.title for s in content.sections] == ["Real Section"]
    assert [tp.text for tp in content.talking_points] == ["123", "Kept"]


async def test_a_draft_with_no_usable_sections_fails_loudly() -> None:
    """No fixed structure to repair onto here -- an empty/unusable draft is a
    ValidationError the caller surfaces and regenerates from, never a silent
    fallback to an empty deck (the codebase's standing rule against
    degradation-that-looks-like-success)."""
    llm = _StubLlm([{"title": "", "bullets": []}])

    with pytest.raises(ValidationError):
        await build_freeform_outline(
            content="x", tone="default", density="standard", n_slides_hint=None,
            language="English", llm=llm, provider_config={},
        )


async def test_empty_content_is_rejected_before_calling_the_llm() -> None:
    llm = _StubLlm([{"title": "Should never be reached", "bullets": []}])

    with pytest.raises(ValidationError):
        await build_freeform_outline(
            content="   ", tone="default", density="standard", n_slides_hint=None,
            language="English", llm=llm, provider_config={},
        )

    assert llm.calls == []
