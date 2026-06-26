"""Unit: the consistency gate judges the PRODUCED deck, not the plan.

Covers the G1 fix — the checker reads real PPTX bytes (slide count, slide titles,
text) and blocks on a deck that violates the profile contract or cannot be parsed.
"""

from __future__ import annotations

import uuid

from src.generation.artifact import inspect_pptx
from src.generation.consistency import check_consistency
from src.models import StakeholderProfile, Tone, Verbosity
from tests.fakes import _pptx_from_markdown


def _profile(slide_min: int = 4, slide_max: int = 12) -> StakeholderProfile:
    return StakeholderProfile(
        logical_id=uuid.uuid4(),
        version=1,
        tenant_id=uuid.uuid4(),
        name="Board",
        audience="board",
        template_id=uuid.uuid4(),
        template_version=1,
        tone=Tone.professional,
        verbosity=Verbosity.concise,
        slide_min=slide_min,
        slide_max=slide_max,
        language="en",
        section_structure=[{"title": "Executive Summary"}, {"title": "Results"}],
        prompt_config={},
    )


_MARKDOWN = "## Executive Summary\n- revenue up\n\n## Results\n- margin stable"


def test_passes_when_deck_matches_contract() -> None:
    deck = inspect_pptx(_pptx_from_markdown("Q3", _MARKDOWN, n_slides=4))
    report = check_consistency(profile=_profile(), deck=deck, template_applied=True)
    assert report["passed"] is True
    # The slide count asserted is the REAL one read from the deck, not the request.
    count_check = next(c for c in report["checks"] if c["name"] == "slide_count_in_range")
    assert count_check["detail"]["n_slides"] == 4


def test_fails_when_required_section_missing_from_deck() -> None:
    deck = inspect_pptx(_pptx_from_markdown("Q3", "## Executive Summary\n- only one", n_slides=4))
    report = check_consistency(profile=_profile(), deck=deck, template_applied=True)
    assert report["passed"] is False
    section_check = next(
        c for c in report["checks"] if c["name"] == "required_sections_present_and_ordered"
    )
    assert section_check["passed"] is False


def test_fails_when_real_slide_count_out_of_range() -> None:
    # Deck honors n_slides=2, but the profile requires at least 4.
    deck = inspect_pptx(_pptx_from_markdown("Q3", _MARKDOWN, n_slides=2))
    report = check_consistency(profile=_profile(slide_min=4), deck=deck, template_applied=True)
    assert report["passed"] is False


def test_fails_on_banned_content_in_the_deck() -> None:
    md = "## Executive Summary\n- TODO finalize numbers\n\n## Results\n- margin stable"
    deck = inspect_pptx(_pptx_from_markdown("Q3", md, n_slides=4))
    report = check_consistency(profile=_profile(), deck=deck, template_applied=True)
    assert report["passed"] is False
    banned = next(c for c in report["checks"] if c["name"] == "no_banned_content")
    assert "todo" in banned["detail"]["hits"]


def test_fails_when_no_template_applied() -> None:
    deck = inspect_pptx(_pptx_from_markdown("Q3", _MARKDOWN, n_slides=4))
    report = check_consistency(profile=_profile(), deck=deck, template_applied=False)
    assert report["passed"] is False


def test_unreadable_artifact_fails_the_gate() -> None:
    report = check_consistency(profile=_profile(), deck=inspect_pptx(b"not-a-pptx"), template_applied=True)
    assert report["passed"] is False
    assert report["checks"][0]["name"] == "artifact_readable"
    assert report["checks"][0]["passed"] is False
