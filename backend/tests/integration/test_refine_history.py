"""Integration: refine (edit outline -> regenerate) + version history provenance.

Proves cheap iteration: editing an outline and regenerating does NOT re-ingest
sources (no new Open Notebook add_source), reuses the same pinned profile/template
versions, and reflects only the intended change. Also proves the history endpoint
exposes full provenance per version, and that editing a profile never mutates a
past generation's pinned versions/params.
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
from src.models import Generation
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, FakePresenton

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}
EDIT_MARKER = "EDITED-UNIQUE-MARKER-42"


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


# --- helpers -------------------------------------------------------------


def _set_byok(client, seed: Fixtures) -> None:
    assert (
        client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub)).status_code
        == 200
    )


def _approved_profile_and_template(client, seed: Fixtures) -> str:
    t = client.post(
        "/api/v1/templates",
        data={"name": "Brand", "brand_tokens": json.dumps({"primary": "#101010"})},
        headers=auth(seed.admin_a_sub),
    ).json()
    client.post(f"/api/v1/templates/{t['id']}/approve", headers=auth(seed.admin_a_sub))
    body = {
        "name": "Group Management",
        "audience": "executives",
        "template_id": t["id"],
        "tone": "professional",
        "verbosity": "standard",
        "slide_min": 4,
        "slide_max": 12,
        "language": "en",
        "section_structure": [{"title": "Summary"}, {"title": "Results"}],
        "prompt_config": {"system": "stay on brand"},
    }
    p = client.post("/api/v1/profiles", json=body, headers=auth(seed.admin_a_sub)).json()
    client.post(f"/api/v1/profiles/{p['id']}/approve", headers=auth(seed.admin_a_sub))
    return p["id"]


async def _project_with_ready_source(client, seed: Fixtures, on_client: FakeOpenNotebook) -> str:
    project = client.post(
        "/api/v1/projects", json={"name": "Q3"}, headers=auth(seed.author_a_sub)
    ).json()
    source = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth(seed.author_a_sub),
    ).json()
    with SessionLocal() as db:
        await ingest_source(
            db=db,
            source_id=uuid.UUID(source["id"]),
            tenant_id=seed.tenant_a,
            on_client=on_client,
            object_store=FakeObjectStore(),
            provider_config=PROVIDER,
        )
        db.commit()
    return project["id"]


async def _generate(client, seed: Fixtures, project_id: str, outline_id: str, presenton, store) -> dict:
    gen = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline_id},
        headers=auth(seed.author_a_sub),
    ).json()
    with SessionLocal() as db:
        await generate_presentation(
            db=db,
            generation_id=uuid.UUID(gen["id"]),
            tenant_id=seed.tenant_a,
            presenton=presenton,
            object_store=store,
        )
        db.commit()
    return gen


# --- tests ---------------------------------------------------------------


async def test_edit_then_regenerate_does_not_reingest(
    client, seed: Fixtures, presenton, store, on_client
) -> None:
    _set_byok(client, seed)
    profile_id = _approved_profile_and_template(client, seed)
    project_id = await _project_with_ready_source(client, seed, on_client)

    ingest_add_source_calls = on_client.calls.count("add_source")
    assert ingest_add_source_calls == 1  # one ingestion happened

    outline = client.post(
        f"/api/v1/projects/{project_id}/outline",
        json={"profile_id": profile_id},
        headers=auth(seed.author_a_sub),
    ).json()
    gen1 = await _generate(client, seed, project_id, outline["id"], presenton, store)

    # Edit the outline: change one talking point's wording only.
    current = client.get(f"/api/v1/outlines/{outline['id']}", headers=auth(seed.author_a_sub)).json()
    content = current["content"]
    assert content["talking_points"], "fixture should produce talking points"
    content["talking_points"][0]["text"] = EDIT_MARKER
    edited = client.put(
        f"/api/v1/outlines/{outline['id']}",
        json={"content": content},
        headers=auth(seed.author_a_sub),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["valid"] is True

    gen2 = await _generate(client, seed, project_id, outline["id"], presenton, store)

    # CORE: no re-ingestion — Open Notebook add_source was not called again.
    assert on_client.calls.count("add_source") == ingest_add_source_calls

    # Pinned profile/template versions are reused unchanged.
    assert gen2["profile_version"] == gen1["profile_version"]
    assert gen2["template_version"] == gen1["template_version"]

    # Only the intended change propagated: gen2 carries the edit, gen1 does not.
    with SessionLocal() as db:
        g1 = db.get(Generation, uuid.UUID(gen1["id"]))
        g2 = db.get(Generation, uuid.UUID(gen2["id"]))
        # slides_markdown is Presenton's string[] (one block per slide).
        assert EDIT_MARKER in "\n".join(g2.params["slides_markdown"])
        assert EDIT_MARKER not in "\n".join(g1.params["slides_markdown"])


async def test_history_exposes_full_provenance(
    client, seed: Fixtures, presenton, store, on_client
) -> None:
    _set_byok(client, seed)
    profile_id = _approved_profile_and_template(client, seed)
    project_id = await _project_with_ready_source(client, seed, on_client)

    me = client.get("/api/v1/auth/me", headers=auth(seed.author_a_sub)).json()
    author_id = me["user"]["id"]

    outline = client.post(
        f"/api/v1/projects/{project_id}/outline",
        json={"profile_id": profile_id},
        headers=auth(seed.author_a_sub),
    ).json()
    await _generate(client, seed, project_id, outline["id"], presenton, store)
    await _generate(client, seed, project_id, outline["id"], presenton, store)

    history = client.get(
        f"/api/v1/projects/{project_id}/generations", headers=auth(seed.author_a_sub)
    )
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 2

    for row in rows:
        assert row["profile_version"] >= 1
        assert row["template_version"] >= 1
        assert row["model"] == "deepseek-chat"
        assert row["provider"] == "deepseek"
        assert row["created_by"] == author_id
        assert row["created_at"]
        assert row["status"] == "ready"
        # Sanitized params: provenance present, engine template ref hidden.
        assert row["params"]["tone"] == "professional"
        assert "n_slides" in row["params"]
        assert "template" not in row["params"]


async def test_editing_profile_does_not_mutate_past_generation(
    client, seed: Fixtures, presenton, store, on_client
) -> None:
    _set_byok(client, seed)
    profile_id = _approved_profile_and_template(client, seed)
    project_id = await _project_with_ready_source(client, seed, on_client)

    outline = client.post(
        f"/api/v1/projects/{project_id}/outline",
        json={"profile_id": profile_id},
        headers=auth(seed.author_a_sub),
    ).json()
    gen1 = await _generate(client, seed, project_id, outline["id"], presenton, store)
    assert gen1["profile_version"] == 1

    # Edit the profile -> new version 2 (immutable versioning from the registry).
    edited = client.put(
        f"/api/v1/profiles/{profile_id}",
        json={
            "name": "Group Management v2",
            "audience": "board",
            "template_id": _template_id_of_profile(client, seed, profile_id),
            "tone": "casual",
            "verbosity": "concise",
            "slide_min": 3,
            "slide_max": 6,
            "language": "en",
            "section_structure": [{"title": "Summary"}],
            "prompt_config": {},
        },
        headers=auth(seed.admin_a_sub),
    )
    assert edited.status_code == 201
    assert edited.json()["version"] == 2

    # The past generation still pins version 1.
    detail = client.get(
        f"/api/v1/generations/{gen1['id']}", headers=auth(seed.author_a_sub)
    ).json()
    assert detail["profile_version"] == 1


def _template_id_of_profile(client, seed: Fixtures, profile_id: str) -> str:
    profiles = client.get("/api/v1/profiles", headers=auth(seed.admin_a_sub)).json()
    row = next(p for p in profiles if p["id"] == profile_id)
    return row["template_id"]
