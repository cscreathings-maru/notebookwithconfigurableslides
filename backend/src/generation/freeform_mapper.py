"""Map a freeform Studio deck request to a Presenton generate payload.

Freeform decks are not governed by a profile: the user picks the content source and
the deck knobs directly. Structure comes from the content itself (or custom
markdown), not a fixed section list.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "en"


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
        "include_table_of_contents": True,
    }
    # Custom markdown drives slide structure directly.
    if content_source == "custom":
        params["slides_markdown"] = content
    if template_ref:
        params["template"] = template_ref
    if instructions:
        params["instructions"] = instructions
    return params
