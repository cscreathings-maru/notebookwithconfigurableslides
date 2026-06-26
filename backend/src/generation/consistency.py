"""Consistency checker — the eval gate before a deck is published.

Judges the deck Presenton actually produced (via `DeckFacts` parsed from the PPTX),
not merely the plan that drove it. Asserts: every required section is present and in
order *in the deck*, the real slide count is within the profile's range, a template was
applied, and no banned content shipped. Returns a structured report; the worker blocks
(status=failed) on failure. If the artifact could not be parsed, that alone fails the
gate (a corrupt/empty deck is never published).
"""

from __future__ import annotations

from typing import Any

from ..models import StakeholderProfile
from .artifact import DeckFacts

# Default banned tokens — placeholder/boilerplate that must never ship.
DEFAULT_BANNED_TERMS = ("lorem ipsum", "todo", "tbd", "placeholder", "xxx")


def _titles_in_order(required: list[str], actual: tuple[str, ...]) -> bool:
    """True if every required title appears, in order, among the deck's slide titles.

    Matching is case-insensitive and substring-tolerant (a slide title may decorate the
    section name, e.g. "2. Results"). Order is enforced as a subsequence so a title slide
    or section dividers between required sections do not break the check.
    """
    norm_actual = [t.lower() for t in actual]
    cursor = 0
    for want in required:
        needle = want.lower().strip()
        match_at = next(
            (i for i in range(cursor, len(norm_actual)) if needle and needle in norm_actual[i]),
            None,
        )
        if match_at is None:
            return False
        cursor = match_at + 1
    return True


def check_consistency(
    *,
    profile: StakeholderProfile,
    deck: DeckFacts | None,
    template_applied: bool,
    banned_terms: tuple[str, ...] = DEFAULT_BANNED_TERMS,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # A deck we cannot read fails the gate outright.
    checks.append(
        {
            "name": "artifact_readable",
            "passed": deck is not None,
            "detail": {"parsed": deck is not None},
        }
    )
    if deck is None:
        return {"passed": False, "checks": checks}

    required_titles = [
        (e["title"] if isinstance(e, dict) else str(e))
        for e in (profile.section_structure or [])
    ]
    checks.append(
        {
            "name": "required_sections_present_and_ordered",
            "passed": _titles_in_order(required_titles, deck.titles),
            "detail": {"expected": required_titles, "actual_titles": list(deck.titles)},
        }
    )

    checks.append(
        {
            "name": "slide_count_in_range",
            "passed": profile.slide_min <= deck.slide_count <= profile.slide_max,
            "detail": {
                "n_slides": deck.slide_count,
                "min": profile.slide_min,
                "max": profile.slide_max,
            },
        }
    )

    checks.append(
        {
            "name": "template_applied",
            "passed": bool(template_applied),
            "detail": {"applied": bool(template_applied)},
        }
    )

    haystack = deck.text.lower()
    hits = [term for term in banned_terms if term in haystack]
    checks.append(
        {"name": "no_banned_content", "passed": not hits, "detail": {"hits": hits}}
    )

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "checks": checks}
