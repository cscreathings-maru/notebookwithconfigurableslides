"""Contract: outline -> Presenton generate request mapping, and the pinned call.

The validated outline drives structure: `slides_markdown` is derived from the
outline (section order fixed), and tone/verbosity/n_slides/template/language come
from the pinned profile + template. The engine never re-invents structure.
"""

from __future__ import annotations

import uuid

import httpx

from src.engines.presenton import PresentonClient
from src.generation.mapper import build_presenton_request
from src.models import StakeholderProfile, Template, Tone, Verbosity
from src.outline.schema import OUTLINE_SCHEMA_VERSION, OutlineContent, OutlineSection, TalkingPoint


def _profile() -> StakeholderProfile:
    return StakeholderProfile(
        logical_id=uuid.uuid4(),
        version=1,
        tenant_id=uuid.uuid4(),
        name="Group Management",
        audience="executive leadership",
        template_id=uuid.uuid4(),
        template_version=1,
        tone=Tone.professional,
        verbosity=Verbosity.standard,
        slide_min=6,
        slide_max=10,
        language="en",
        section_structure=[{"title": "Introduction"}, {"title": "Results"}, {"title": "Risks"}],
        prompt_config={"system": "Stay on brand."},
    )


def _template() -> Template:
    return Template(
        logical_id=uuid.uuid4(),
        version=1,
        tenant_id=uuid.uuid4(),
        name="Brand",
        presenton_template_ref="tref_acme__Brand",
        brand_tokens={"primary": "#101010"},
    )


def _outline() -> OutlineContent:
    sections = [
        OutlineSection(id="introduction", title="Introduction", order=0),
        OutlineSection(id="results", title="Results", order=1),
        OutlineSection(id="risks", title="Risks", order=2),
    ]
    points = [
        TalkingPoint(section_id="introduction", text="Why we are here"),
        TalkingPoint(section_id="results", text="Revenue up 12%"),
        TalkingPoint(section_id="risks", text="FX exposure"),
    ]
    return OutlineContent(
        schema_version=OUTLINE_SCHEMA_VERSION,
        sections=sections,
        talking_points=points,
        data_bindings=[],
    )


def test_mapping_fixes_structure_from_outline() -> None:
    params = build_presenton_request(profile=_profile(), template=_template(), outline=_outline())

    assert params["tone"] == "professional"
    assert params["verbosity"] == "standard"
    assert params["language"] == "en"
    assert params["template"] == "tref_acme__Brand"
    assert params["include_title_slide"] is True
    assert params["export_as"] == "pptx"

    # slides_markdown is a string[] (one block per slide) pinning section order.
    md = params["slides_markdown"]
    assert isinstance(md, list)
    joined = "\n\n".join(md)
    assert joined.index("Introduction") < joined.index("Results") < joined.index("Risks")
    assert "Revenue up 12%" in joined  # talking points carried through

    # n_slides stays within the profile's range.
    assert 6 <= params["n_slides"] <= 10


def test_mapping_clamps_n_slides_to_profile_range() -> None:
    profile = _profile()
    profile.slide_min = 2
    profile.slide_max = 2
    params = build_presenton_request(profile=profile, template=_template(), outline=_outline())
    assert params["n_slides"] == 2


async def test_presenton_generate_pinned_call() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"presentation_id": "pres_1", "path": "/app_data/pres_1.pptx", "edit_path": "/e"}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://presenton.test")
    client = PresentonClient(client=http)
    res = await client.generate(params={"tone": "professional", "export_as": "pptx"})

    assert res["presentation_id"] == "pres_1"
    assert res["path"] == "/app_data/pres_1.pptx"
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/ppt/presentation/generate"
    assert "edit_path" not in res or res["edit_path"]  # edit_path is internal-only context
