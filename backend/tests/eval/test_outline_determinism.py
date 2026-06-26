"""Eval: deterministic structure.

The same project + profile (+ pinned template version) must yield the same section
set and order every run — only wording may vary. Structure is derived from the
profile's section_structure, NOT from the LLM, so two builds with a model that
returns different talking points still produce identical sections.
"""

from __future__ import annotations

import uuid

from src.models import Project, StakeholderProfile, Tone, Verbosity
from src.outline.builder import build_outline
from tests.fakes import FakeLlm, FakeOpenNotebook


def _profile() -> StakeholderProfile:
    return StakeholderProfile(
        logical_id=uuid.uuid4(),
        version=3,
        tenant_id=uuid.uuid4(),
        name="Board Update",
        audience="board",
        template_id=uuid.uuid4(),
        template_version=2,
        tone=Tone.professional,
        verbosity=Verbosity.concise,
        slide_min=5,
        slide_max=9,
        language="en",
        section_structure=[
            {"title": "Executive Summary"},
            {"title": "Financial Results"},
            {"title": "Strategic Risks"},
            {"title": "Outlook"},
        ],
        prompt_config={"system": "Be precise."},
    )


def _project() -> Project:
    return Project(
        tenant_id=uuid.uuid4(),
        name="Q3",
        on_notebook_id="nb_acme",
        created_by=uuid.uuid4(),
    )


async def _build_once(profile: Project) -> list[tuple[str, str, int]]:
    content, _usage = await build_outline(
        project=_project(),
        profile=profile,
        on_client=FakeOpenNotebook(),
        llm=FakeLlm(),
        provider_config={"provider": "deepseek", "model": "deepseek-chat"},
    )
    return [(s.id, s.title, s.order) for s in content.sections]


async def test_same_inputs_yield_same_section_set_and_order() -> None:
    profile = _profile()
    first = await _build_once(profile)
    second = await _build_once(profile)

    assert first == second
    # And it matches the profile's declared structure, in order.
    assert [t for _, t, _ in first] == [
        "Executive Summary",
        "Financial Results",
        "Strategic Risks",
        "Outlook",
    ]
    assert [o for _, _, o in first] == [0, 1, 2, 3]


async def test_outline_is_valid_and_points_reference_real_sections() -> None:
    content, usage = await build_outline(
        project=_project(),
        profile=_profile(),
        on_client=FakeOpenNotebook(),
        llm=FakeLlm(),
        provider_config={},
    )
    section_ids = {s.id for s in content.sections}
    assert all(tp.section_id in section_ids for tp in content.talking_points)
    assert usage.tokens_in > 0 and usage.tokens_out > 0
