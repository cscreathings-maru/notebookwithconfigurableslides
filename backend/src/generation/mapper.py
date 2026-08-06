"""Param mapper: pinned profile + validated outline -> Presenton generate request.

`slides_markdown` is derived from the outline so the engine cannot re-invent
structure — it only renders the fixed sections in order with the provided wording.
The template ref is engine-internal and stays inside `params` (never surfaced).
"""

from __future__ import annotations

from typing import Any

from ..models import StakeholderProfile, Template
from ..outline.schema import OutlineContent


def _instructions(profile: StakeholderProfile) -> str:
    cfg = profile.prompt_config or {}
    if isinstance(cfg, dict):
        return str(cfg.get("system") or cfg.get("instructions") or "")
    return str(cfg)


def slides_markdown_from_outline(outline: OutlineContent) -> list[str]:
    """One markdown block per section (in order), bullets = talking points.

    Presenton's `slides_markdown` is a string[] — one entry per slide — so the
    engine renders the fixed sections in order rather than re-inventing structure.

    Public (not `_`-prefixed): shared with the freeform-from-outline generation path
    (DG-2, `generation/freeform_service.py`) so a confirmed outline's structure is
    fixed the same way here as it is for the governed path -- one implementation of
    "outline -> slides_markdown", not two that can drift.
    """
    points_by_section: dict[str, list[str]] = {}
    for tp in outline.talking_points:
        points_by_section.setdefault(tp.section_id, []).append(tp.text)

    blocks: list[str] = []
    for section in sorted(outline.sections, key=lambda s: s.order):
        lines = [f"## {section.title}"]
        for text in points_by_section.get(section.id, []):
            lines.append(f"- {text}")
        blocks.append("\n".join(lines))
    return blocks


def _content_brief(profile: StakeholderProfile, outline: OutlineContent) -> str:
    titles = ", ".join(s.title for s in sorted(outline.sections, key=lambda s: s.order))
    return f"Presentation for {profile.audience}. Sections: {titles}."


def _n_slides(profile: StakeholderProfile, outline: OutlineContent) -> int:
    # One slide per section + a title slide, clamped to the profile's range.
    desired = len(outline.sections) + 1
    return max(profile.slide_min, min(desired, profile.slide_max))


def build_presenton_request(
    *, profile: StakeholderProfile, template: Template, outline: OutlineContent
) -> dict[str, Any]:
    return {
        "content": _content_brief(profile, outline),
        "slides_markdown": slides_markdown_from_outline(outline),
        "instructions": _instructions(profile),
        "tone": profile.tone.value,
        "verbosity": profile.verbosity.value,
        "n_slides": _n_slides(profile, outline),
        "language": profile.language,
        "template": template.presenton_template_ref,
        "include_title_slide": True,
        "include_table_of_contents": True,
        "export_as": "pptx",
    }
