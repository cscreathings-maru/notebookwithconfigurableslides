"""Outline builder — composes a CONTROLLED prompt and produces a validated outline.

Structure is derived from the profile's `section_structure` (fixed order); the LLM
only fills talking points. This guarantees deterministic structure across runs while
wording may vary. Retrieval context comes from Open Notebook. The result is validated
(and repaired onto the required structure if needed).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from ..core.errors import ValidationError
from ..core.logging import get_logger
from ..models import StakeholderProfile
from .schema import (
    OUTLINE_SCHEMA_VERSION,
    DataBinding,
    OutlineContent,
    OutlineSection,
    TalkingPoint,
)
from .validator import repair_outline, validate_outline

logger = get_logger("orchestrator.outline")


@dataclass
class LlmResult:
    points_by_section: dict[str, list[str]]
    tokens_in: int
    tokens_out: int


@dataclass
class OutlineUsage:
    tokens_in: int
    tokens_out: int


class Llm(Protocol):
    async def talking_points(
        self,
        *,
        section_ids: list[str],
        context: list[dict[str, Any]],
        profile: dict[str, Any],
        provider_config: dict[str, Any],
    ) -> LlmResult: ...


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "section"


def sections_from_profile(profile: StakeholderProfile) -> list[OutlineSection]:
    """Deterministic sections from the profile's pinned section_structure."""
    sections: list[OutlineSection] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(profile.section_structure or []):
        title = entry["title"] if isinstance(entry, dict) else str(entry)
        base = slugify(title)
        # Disambiguate duplicate titles deterministically.
        seen[base] = seen.get(base, 0) + 1
        sid = base if seen[base] == 1 else f"{base}-{seen[base]}"
        sections.append(OutlineSection(id=sid, title=title, order=index))
    return sections


def _retrieval_query(profile: StakeholderProfile) -> str:
    titles = ", ".join(
        (e["title"] if isinstance(e, dict) else str(e)) for e in profile.section_structure or []
    )
    return f"Key facts for an {profile.audience} presentation covering: {titles}"


def _profile_brief(profile: StakeholderProfile) -> dict[str, Any]:
    return {
        "audience": profile.audience,
        "tone": profile.tone.value,
        "verbosity": profile.verbosity.value,
        "language": profile.language,
        "prompt_config": profile.prompt_config,
    }


async def build_outline(
    *,
    project,
    profile: StakeholderProfile,
    on_client,
    llm: Llm,
    provider_config: dict[str, Any],
) -> tuple[OutlineContent, OutlineUsage]:
    sections = sections_from_profile(profile)
    if not sections:
        raise ValidationError("Profile has no section_structure to build an outline from.")

    context: list[dict[str, Any]] = []
    if project.on_notebook_id:
        context = await on_client.search(
            notebook_id=project.on_notebook_id, query=_retrieval_query(profile)
        )

    result = await llm.talking_points(
        section_ids=[s.id for s in sections],
        context=context,
        profile=_profile_brief(profile),
        provider_config=provider_config,
    )

    valid_ids = {s.id for s in sections}
    talking_points = [
        TalkingPoint(section_id=sid, text=text)
        for sid, texts in result.points_by_section.items()
        if sid in valid_ids
        for text in texts
        if text
    ]
    data_bindings = _bindings_from_context(sections, context)

    content = OutlineContent(
        schema_version=OUTLINE_SCHEMA_VERSION,
        sections=sections,
        talking_points=talking_points,
        data_bindings=data_bindings,
    )

    model, errors = validate_outline(content.model_dump())
    if model is None:
        repaired = repair_outline(content.model_dump(), [s.title for s in sections])
        model, errors = validate_outline(repaired)
        if model is None:
            raise ValidationError(f"Could not build a valid outline: {errors}")

    return model, OutlineUsage(tokens_in=result.tokens_in, tokens_out=result.tokens_out)


def _bindings_from_context(
    sections: list[OutlineSection], context: list[dict[str, Any]]
) -> list[DataBinding]:
    """Bind the first section to available analysis refs as grounding provenance."""
    bindings: list[DataBinding] = []
    if not sections:
        return bindings
    for item in context:
        ref = item.get("source_ref")
        if ref:
            bindings.append(
                DataBinding(section_id=sections[0].id, key=f"fact-{uuid.uuid4().hex[:8]}", source_ref=ref)
            )
    return bindings
