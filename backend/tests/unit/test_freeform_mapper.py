"""Unit tests for the freeform (NotebookLM Studio) Presenton mapping + model list."""

from __future__ import annotations

from src.generation.freeform_mapper import build_freeform_request, split_custom_slides


def test_freeform_request_carries_all_knobs() -> None:
    params = build_freeform_request(
        content="A synthesized brief.",
        content_source="summary",
        tone="professional",
        density="concise",
        n_slides=8,
        template_ref=None,
        web_search=True,
        export_as="pdf",
    )
    assert params["content"] == "A synthesized brief."
    assert params["n_slides"] == 8
    assert params["tone"] == "professional"
    assert params["verbosity"] == "concise"
    assert params["web_search"] is True
    assert params["export_as"] == "pdf"
    # Presenton wants a language name, not an ISO code; default targets Indonesian.
    assert params["language"] == "Bahasa Indonesia"
    # Non-custom sources do not force a fixed slides markdown structure.
    assert "slides_markdown" not in params
    assert "template" not in params  # defaults to Presenton's "general"


def test_freeform_request_honors_explicit_language() -> None:
    params = build_freeform_request(
        content="A brief.",
        content_source="summary",
        tone="professional",
        density="standard",
        n_slides=6,
        template_ref=None,
        web_search=False,
        export_as="pptx",
        language="English",
    )
    assert params["language"] == "English"


def test_freeform_custom_markdown_is_split_into_slide_array() -> None:
    params = build_freeform_request(
        content="## Slide One\n- point\n\n---\n\n## Slide Two\n- another",
        content_source="custom",
        tone="casual",
        density="standard",
        n_slides=5,
        template_ref="tmpl_ref_123",
        web_search=False,
        export_as="pptx",
    )
    # slides_markdown is a string[] — one entry per slide.
    assert params["slides_markdown"] == ["## Slide One\n- point", "## Slide Two\n- another"]
    assert params["template"] == "tmpl_ref_123"


def test_split_custom_slides_falls_back_to_headings_then_whole() -> None:
    assert split_custom_slides("## A\n- x\n## B\n- y") == ["## A\n- x", "## B\n- y"]
    assert split_custom_slides("just one block") == ["just one block"]
    assert split_custom_slides("   ") == []


def test_model_dropdown_puts_active_default_first_and_dedupes() -> None:
    from src.core.config import Settings

    s = Settings(
        OPENROUTER_MODEL="openai/gpt-4o-mini",
        OPENROUTER_MODELS="deepseek/deepseek-chat-v3,openai/gpt-4o-mini,openai/gpt-4o-mini",
    )
    models = s.openrouter_model_list
    assert models[0] == "openai/gpt-4o-mini"
    assert models.count("openai/gpt-4o-mini") == 1
    assert "deepseek/deepseek-chat-v3" in models
