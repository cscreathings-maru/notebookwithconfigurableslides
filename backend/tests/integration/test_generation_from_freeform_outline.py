"""DG-2: POST /projects/{id}/generations with outline_id pointing at a FREEFORM
outline (Outline.profile_id is None).

The governed outline_id path is already covered in test_generation.py. This covers
the new branch: routing decides which service handles outline_id based on whether
the outline has a profile, structure comes from the confirmed outline (not
re-derived from a content blob), consistency is skipped the same way any other
freeform generation skips it, and cross-project/invalid-outline guards hold.

RM-11: every generation renders from a real, inspected template now -- there is
no engine-side stock theme to fall back to (D2). A template with a real `.pptx`
is created and selected in every test that actually renders a deck.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.generation.artifact import inspect_pptx
from src.generation.worker import generate_presentation
from src.main import app
from src.models import Generation, Outline
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, catalog_and_approve, usable_pptx_bytes

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}

CUSTOM_PAYLOAD = {
    "content_source": "custom",
    "custom_markdown": "First topic with details.\n\nSecond topic with more.",
    "tone": "professional",
    "density": "standard",
}


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture(autouse=True)
def _wire(store):
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: FakeOpenNotebook()
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


def _project(client, sub: str) -> str:
    return client.post("/api/v1/projects", json={"name": "DG-2"}, headers=auth(sub)).json()["id"]


async def _approved_template_id(client, seed: Fixtures) -> str:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Brand", "brand_tokens": json.dumps({})},
        files={
            "file": (
                "brand.pptx",
                usable_pptx_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 201, resp.text
    template = resp.json()
    approved = await catalog_and_approve(
        tenant_id=seed.tenant_a,
        template_logical_id=template["id"],
        client=client,
        headers=auth(seed.admin_a_sub),
    )
    return approved["id"]


def _freeform_outline(client, sub: str, project_id: str) -> dict:
    resp = client.post(
        f"/api/v1/projects/{project_id}/outline", json=CUSTOM_PAYLOAD, headers=auth(sub)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_generation_from_freeform_outline_has_no_profile(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    outline = _freeform_outline(client, seed.author_a_sub, project_id)
    template_id = await _approved_template_id(client, seed)

    resp = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline["id"], "template_id": template_id},
        headers=auth(seed.author_a_sub),
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["outline_id"] == outline["id"]
    assert body["profile_version"] is None


async def test_rendered_deck_matches_the_confirmed_outline_sections(
    client, seed: Fixtures, store: FakeObjectStore
) -> None:
    """The generated deck's structure must come from the outline the user
    confirmed, not be re-derived from a content blob the way plain freeform is.

    The test harness's TestClient skips the Arq lifespan (conftest.py), so a
    dispatched job is never actually picked up by a worker in-process -- the
    worker is invoked directly here, same as test_generation.py already does.
    """
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    outline = _freeform_outline(client, seed.author_a_sub, project_id)
    section_titles = [s["title"] for s in outline["content"]["sections"]]
    template_id = await _approved_template_id(client, seed)

    gen = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline["id"], "template_id": template_id},
        headers=auth(seed.author_a_sub),
    )
    assert gen.status_code == 202, gen.text

    with SessionLocal() as db:
        await generate_presentation(
            db=db,
            generation_id=uuid.UUID(gen.json()["id"]),
            tenant_id=seed.tenant_a,
            object_store=store,
        )
        db.commit()

    detail = client.get(
        f"/api/v1/generations/{gen.json()['id']}", headers=auth(seed.author_a_sub)
    ).json()
    assert detail["status"] == "ready"

    # The response never exposes the storage key (T-1.5) -- read it back off
    # the row directly, the same provenance boundary `api/generations.py` enforces.
    with SessionLocal() as db:
        row = db.get(Generation, uuid.UUID(gen.json()["id"]))
        pptx_key = row.pptx_uri
    assert pptx_key

    facts = inspect_pptx(store.get_bytes(key=pptx_key))
    # Slide 0 is the synthetic title slide (deck/from_outline.py); the rest
    # follow the outline's own section order.
    assert list(facts.titles[1:]) == section_titles


async def test_freeform_from_outline_publishes_without_a_consistency_check(
    client, seed: Fixtures, store: FakeObjectStore
) -> None:
    """Same skip every other freeform generation gets -- there's no profile to
    check against (generation/worker.py)."""
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    outline = _freeform_outline(client, seed.author_a_sub, project_id)
    template_id = await _approved_template_id(client, seed)
    gen = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline["id"], "template_id": template_id},
        headers=auth(seed.author_a_sub),
    ).json()

    with SessionLocal() as db:
        await generate_presentation(
            db=db,
            generation_id=uuid.UUID(gen["id"]),
            tenant_id=seed.tenant_a,
            object_store=store,
        )
        db.commit()

    final = client.get(f"/api/v1/generations/{gen['id']}", headers=auth(seed.author_a_sub)).json()
    assert final["status"] == "ready"
    assert final["consistency_report"] == {"passed": True, "checks": [], "mode": "freeform"}


def test_generating_from_an_invalid_outline_is_rejected(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    outline = _freeform_outline(client, seed.author_a_sub, project_id)

    # Break it directly: PUT re-validates and would refuse an invalid edit, so the
    # only way to reach a persisted invalid=False row is to write one.
    with SessionLocal() as db:
        row = db.get(Outline, uuid.UUID(outline["id"]))
        row.valid = False
        db.add(row)
        db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline["id"]},
        headers=auth(seed.author_a_sub),
    )

    assert resp.status_code == 422, resp.text


def test_generating_from_another_projects_outline_is_not_found(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    project_a = _project(client, seed.author_a_sub)
    project_b = _project(client, seed.author_a_sub)
    outline = _freeform_outline(client, seed.author_a_sub, project_a)

    resp = client.post(
        f"/api/v1/projects/{project_b}/generations",
        json={"outline_id": outline["id"]},
        headers=auth(seed.author_a_sub),
    )

    assert resp.status_code == 404, resp.text
