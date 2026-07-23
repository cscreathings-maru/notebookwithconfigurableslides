"""Map a freeform Studio deck request to a Presenton generate payload.

Matches the self-hosted Presenton contract (POST /api/v1/ppt/presentation/generate):
tone, verbosity, web_search, n_slides, export_as and template are all first-class
generate params, and `slides_markdown` is a string[] (one entry per slide). Freeform
decks are not governed by a profile — the user picks the content source and the deck
knobs directly, and structure comes from the content itself (or the custom markdown).
"""

from __future__ import annotations

import re
from typing import Any

# Presenton expects a language *name*, not an ISO code. This is only a safety net —
# the service always passes an explicit language (settings.default_language).
DEFAULT_LANGUAGE = "Bahasa Indonesia"

# A line that is exactly `---` (optionally padded) separates custom slides.
_SLIDE_SEPARATOR = re.compile(r"^\s*---\s*$", re.MULTILINE)


def split_custom_slides(markdown: str) -> list[str]:
    """Split authored markdown into one block per slide.

    Preferred separator is a `---` divider; otherwise split on top-level `##`
    headings; otherwise treat the whole thing as a single slide.
    """
    text = markdown.strip()
    if not text:
        return []

    if _SLIDE_SEPARATOR.search(text):
        parts = [p.strip() for p in _SLIDE_SEPARATOR.split(text)]
        return [p for p in parts if p]

    if re.search(r"^\s*##\s+", text, re.MULTILINE):
        # Keep each heading with its body; the split drops the delimiter, so re-add.
        chunks = re.split(r"(?=^\s*##\s+)", text, flags=re.MULTILINE)
        return [c.strip() for c in chunks if c.strip()]

    return [text]


def build_freeform_request(
    *,
    content: str,
    content_source: str,
    tone: str,
    density: str,
    n_slides: int,
    template_ref: str | None,
    web_search: bool,
    export_as: str,
    language: str = DEFAULT_LANGUAGE,
    instructions: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "content": content,
        "n_slides": n_slides,
        "language": language,
        "tone": tone,
        "verbosity": density,
        "web_search": web_search,
        "export_as": export_as,
        "include_title_slide": True,
        "include_table_of_contents": False,
    }
    # Custom markdown drives slide structure directly (one entry per slide).
    if content_source == "custom":
        params["slides_markdown"] = split_custom_slides(content)
    # Presenton defaults template to "general"; only override when we have a ref.
    if template_ref:
        params["template"] = template_ref
    if instructions:
        params["instructions"] = instructions
    return params
