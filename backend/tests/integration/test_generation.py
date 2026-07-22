"""Integration: upload -> analyze -> outline -> generate -> download.

Drives the whole pipeline through the public API with the engines, LLM, and object
store faked. Asserts the deck becomes ready with a passing consistency report and
that engine ids/paths never reach the client.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.generation.worker import generate_presentation
from src.ingestion.service import ingest_source
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, FakePresenton

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}


@pytest.fixture
def presenton() -> FakePresenton:
    return FakePresenton()


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture
def on_client() -> FakeOpenNotebook:
    return FakeOpenNotebook(notebook_id="nb_acme", source_id="src_1")


@pytest.fixture(autouse=True)
def _wire(presenton, store, on_client):
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: presenton
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: on_client
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


def _approved_template(client, seed: Fixtures) -> dict:
    t = client.post(
        "/api/v1/templates",
        data={"name": "Brand", "brand_tokens": json.dumps({"primary": "#101010"})},
        headers=auth(seed.admin_a_sub),
    ).json()
    return client.post(
        f"/api/v1/templates/{t['id']}/approve", headers=auth(seed.admin_a_sub)
    ).json()


def _approved_profile(client, seed: Fixtures, template_id: str) -> dict:
    body = {
        "name": "Group Management",
        "audience": "executives",
        "template_id": template_id,
        "tone": "professional",
        "verbosity": "standard",
        "slide_min": 4,
        "slide_max": 12,
        "language": "en",
        "section_structure": [
            {"title": "Executive Summary"},
            {"title": "Results"},
            {"title": "Risks"},
        ],
        "prompt_config": {"system": "Stay on brand."},
    }
    p = client.post("/api/v1/profiles", json=body, headers=auth(seed.admin_a_sub)).json()
    return client.post(
        f"/api/v1/profiles/{p['id']}/approve", headers=auth(seed.admin_a_sub)
    ).json()


async def _project_with_ready_source(
    client, seed: Fixtures, on_client: FakeOpenNotebook
) -> str:
    project = client.post(
        "/api/v1/projects", json={"name": "Q3 Deck"}, headers=auth(seed.author_a_sub)
    ).json()
    source = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth(seed.author_a_sub),
    ).json()
    # Drive the source to ready via the ingest pipeline (same fake engine).
    await _ingest(source["id"], seed.tenant_a, on_client)
    return project["id"]


async def _ingest(source_id: str, tenant_id: uuid.UUID, on_client: FakeOpenNotebook) -> None:
    with SessionLocal() as db:
        await ingest_source(
            db=db,
            source_id=uuid.UUID(source_id),
            tenant_id=tenant_id,
            on_client=on_client,
            object_store=FakeObjectStore(),
            provider_config=PROVIDER,
        )
        db.commit()


async def _run_generation(generation_id: str, tenant_id: uuid.UUID, presenton, store) -> None:
    with SessionLocal() as db:
        await generate_presentation(
            db=db,
            generation_id=uuid.UUID(generation_id),
            tenant_id=tenant_id,
            presenton=presenton,
            object_store=store,
        )
        db.commit()


async def test_full_pipeline_to_ready_and_download(
    client, seed: Fixtures, presenton, store, on_client
) -> None:
    _set_byok(client, seed)
    template = _approved_template(client, seed)
    profile = _approved_profile(client, seed, template["id"])
    project_id = await _project_with_ready_source(client, seed, on_client)

    # Outline build (sync): structure fixed to the profile's sections.
    outline = client.post(
        f"/api/v1/projects/{project_id}/outline",
        json={"profile_id": profile["id"]},
        headers=auth(seed.author_a_sub),
    )
    assert outline.status_code == 201, outline.text
    outline_body = outline.json()
    assert outline_body["valid"] is True
    titles = [s["title"] for s in outline_body["content"]["sections"]]
    assert titles == ["Executive Summary", "Results", "Risks"]

    # Enqueue generation.
    gen = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline_body["id"]},
        headers=auth(seed.author_a_sub),
    )
    assert gen.status_code == 202, gen.text
    gen_body = gen.json()
    assert gen_body["status"] == "queued"
    assert "presenton_presentation_id" not in gen_body

    # Run the worker pipeline.
    await _run_generation(gen_body["id"], seed.tenant_a, presenton, store)

    detail = client.get(
        f"/api/v1/generations/{gen_body['id']}", headers=auth(seed.author_a_sub)
    ).json()
    assert detail["status"] == "ready"
    assert detail["consistency_report"]["passed"] is True
    # Presenton returns one file per call; the governed path requests pptx.
    assert detail["artifacts"] == {"pptx": True, "pdf": False}
    assert "presenton_presentation_id" not in detail
    assert "pptx_uri" not in detail

    # Download returns a signed URL, not the engine path.
    dl = client.get(
        f"/api/v1/generations/{gen_body['id']}/download?format=pptx",
        headers=auth(seed.author_a_sub),
    ).json()
    assert "objectstore.test" in dl["url"]
    assert "/app_data/" not in dl["url"]


def test_generation_blocked_until_sources_ready(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    template = _approved_template(client, seed)
    profile = _approved_profile(client, seed, template["id"])

    project = client.post(
        "/api/v1/projects", json={"name": "Pending"}, headers=auth(seed.author_a_sub)
    ).json()
    # Source stays queued (never ingested).
    client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
        headers=auth(seed.author_a_sub),
    )

    outline = client.post(
        f"/api/v1/projects/{project['id']}/outline",
        json={"profile_id": profile["id"]},
        headers=auth(seed.author_a_sub),
    ).json()
    gen = client.post(
        f"/api/v1/projects/{project['id']}/generations",
        json={"outline_id": outline["id"]},
        headers=auth(seed.author_a_sub),
    )
    assert gen.status_code == 409
    assert gen.json()["error"]["code"] == "sources_not_ready"


async def test_generation_proceeds_from_ready_and_skips_failed_sources(
    client, seed: Fixtures, presenton, store, on_client
) -> None:
    """A source that FAILED to ingest must not block generation forever — the deck is
    built from the ready sources and the failed one is recorded as skipped."""
    _set_byok(client, seed)
    template = _approved_template(client, seed)
    profile = _approved_profile(client, seed, template["id"])

    project = client.post(
        "/api/v1/projects", json={"name": "Mixed"}, headers=auth(seed.author_a_sub)
    ).json()

    ready = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("ok.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth(seed.author_a_sub),
    ).json()
    await _ingest(ready["id"], seed.tenant_a, on_client)

    broken = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("bad.pdf", b"corrupt", "application/pdf")},
        headers=auth(seed.author_a_sub),
    ).json()
    await _ingest(broken["id"], seed.tenant_a, FakeOpenNotebook(status_sequence=["failed"]))

    outline = client.post(
        f"/api/v1/projects/{project['id']}/outline",
        json={"profile_id": profile["id"]},
        headers=auth(seed.author_a_sub),
    ).json()
    gen = client.post(
        f"/api/v1/projects/{project['id']}/generations",
        json={"outline_id": outline["id"]},
        headers=auth(seed.author_a_sub),
    )
    assert gen.status_code == 202, gen.text
    await _run_generation(gen.json()["id"], seed.tenant_a, presenton, store)

    detail = client.get(
        f"/api/v1/generations/{gen.json()['id']}", headers=auth(seed.author_a_sub)
    ).json()
    assert detail["status"] == "ready"

    # Provenance records only the ready source; the failed one was skipped.
    with SessionLocal() as db:
        from src.models import Generation

        row = db.get(Generation, uuid.UUID(gen.json()["id"]))
        assert row.source_ids == [ready["id"]]


async def test_generation_blocked_when_no_source_is_ready(
    client, seed: Fixtures, on_client
) -> None:
    _set_byok(client, seed)
    template = _approved_template(client, seed)
    profile = _approved_profile(client, seed, template["id"])

    project = client.post(
        "/api/v1/projects", json={"name": "AllFailed"}, headers=auth(seed.author_a_sub)
    ).json()
    only = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("bad.pdf", b"corrupt", "application/pdf")},
        headers=auth(seed.author_a_sub),
    ).json()
    await _ingest(only["id"], seed.tenant_a, FakeOpenNotebook(status_sequence=["failed"]))

    outline = client.post(
        f"/api/v1/projects/{project['id']}/outline",
        json={"profile_id": profile["id"]},
        headers=auth(seed.author_a_sub),
    ).json()
    gen = client.post(
        f"/api/v1/projects/{project['id']}/generations",
        json={"outline_id": outline["id"]},
        headers=auth(seed.author_a_sub),
    )
    assert gen.status_code == 409
    assert gen.json()["error"]["code"] == "no_ready_sources"
