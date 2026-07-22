"""Unit tests for the freeform (NotebookLM Studio) Presenton mapping + model list."""

from __future__ import annotations

from src.generation.freeform_mapper import build_freeform_request


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
    # Non-custom sources do not force a fixed slides markdown structure.
    assert "slides_markdown" not in params
    assert "template" not in params


def test_freeform_custom_markdown_drives_structure_and_template() -> None:
    params = build_freeform_request(
        content="## Slide One\n- point",
        content_source="custom",
        tone="casual",
        density="standard",
        n_slides=5,
        template_ref="tmpl_ref_123",
        web_search=False,
        export_as="pptx",
    )
    assert params["slides_markdown"] == "## Slide One\n- point"
    assert params["template"] == "tmpl_ref_123"


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
