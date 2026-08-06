"""DG-1: POST /projects/{id}/outline, freeform branch (content_source, no profile_id).

Drives the freeform outline path through the public API. The governed branch is
already covered elsewhere (tests/eval/test_outline_determinism.py at the builder
level, tests/integration/test_generation.py through the API) -- these assert the
NEW branch specifically: routing, persistence with a null profile, metering, and
that the existing PUT /outlines/{id} edit path keeps working for a profile-less row.
"""

from __future__ import annotations

import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
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


@pytest.fixture(autouse=True)
def _wire():
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: FakePresenton()
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: FakeOpenNotebook()
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


def _project(client, sub: str) -> str:
    return client.post("/api/v1/projects", json={"name": "Freeform Outline"}, headers=auth(sub)).json()["id"]


CUSTOM_PAYLOAD = {
    "content_source": "custom",
    "custom_markdown": "First topic.\n\nSecond topic with more detail.",
    "tone": "professional",
    "density": "standard",
}


def test_freeform_outline_has_no_profile_and_a_valid_structure(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act
    resp = client.post(
        f"/api/v1/projects/{project_id}/outline", json=CUSTOM_PAYLOAD, headers=auth(seed.author_a_sub)
    )

    # Assert
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["profile_id"] is None
    assert body["profile_version"] is None
    assert body["valid"] is True
    assert len(body["content"]["sections"]) >= 1
    section_ids = {s["id"] for s in body["content"]["sections"]}
    assert all(tp["section_id"] in section_ids for tp in body["content"]["talking_points"])


def test_missing_both_profile_id_and_content_source_is_rejected(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    resp = client.post(f"/api/v1/projects/{project_id}/outline", json={}, headers=auth(seed.author_a_sub))

    assert resp.status_code == 422, resp.text


def test_custom_content_source_requires_markdown(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    resp = client.post(
        f"/api/v1/projects/{project_id}/outline",
        json={"content_source": "custom"},
        headers=auth(seed.author_a_sub),
    )

    assert resp.status_code == 422, resp.text


def test_regenerate_is_a_second_call_producing_a_distinct_outline(client, seed: Fixtures) -> None:
    """No dedicated 'rebuild' endpoint -- Regenerate is calling the same POST again
    with the same settings, per the plan's build-order note (DG-1.3)."""
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    first = client.post(
        f"/api/v1/projects/{project_id}/outline", json=CUSTOM_PAYLOAD, headers=auth(seed.author_a_sub)
    ).json()
    second = client.post(
        f"/api/v1/projects/{project_id}/outline", json=CUSTOM_PAYLOAD, headers=auth(seed.author_a_sub)
    ).json()

    assert first["id"] != second["id"]


def test_freeform_outline_is_metered_and_labelled(client, seed: Fixtures) -> None:
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    client.post(f"/api/v1/projects/{project_id}/outline", json=CUSTOM_PAYLOAD, headers=auth(seed.author_a_sub))

    audit = client.get("/api/v1/audit", headers=auth(seed.admin_a_sub)).json()
    created = [e for e in audit if e["action"] == "outline.created"]
    assert created, "freeform outline emitted no usage record"
    assert created[-1]["resource"]["path"] == "freeform"
    assert created[-1]["resource"]["content_source"] == "custom"


def test_editing_a_freeform_outline_still_works(client, seed: Fixtures) -> None:
    """PUT /outlines/{id} is unchanged code -- this pins that nullable profile_id
    didn't break the existing edit/re-validate path."""
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    outline = client.post(
        f"/api/v1/projects/{project_id}/outline", json=CUSTOM_PAYLOAD, headers=auth(seed.author_a_sub)
    ).json()

    edited_content = outline["content"]
    edited_content["sections"][0]["title"] = "Renamed Section"

    resp = client.put(
        f"/api/v1/outlines/{outline['id']}",
        json={"content": edited_content},
        headers=auth(seed.author_a_sub),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["content"]["sections"][0]["title"] == "Renamed Section"
    assert resp.json()["profile_id"] is None


async def test_notebook_content_source_reuses_scoped_search(client, seed: Fixtures) -> None:
    """Same scoping discipline as freeform generation and chat -- retrieval goes
    through the same on_client.search() call, restricted to this project's sources."""
    on_client = FakeOpenNotebook(
        notebook_id="nb_1", source_id="src_1", corpus={"src_1": "Revenue grew 12% YoY."}
    )
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: on_client
    _set_byok(client, seed)

    project_id = _project(client, seed.author_a_sub)
    src_resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        files={"file": ("notes.txt", b"content", "text/plain")},
        headers=auth(seed.author_a_sub),
    )
    assert src_resp.status_code == 202, src_resp.text

    with SessionLocal() as db:
        await ingest_source(
            db=db,
            source_id=uuid.UUID(src_resp.json()["id"]),
            tenant_id=seed.tenant_a,
            on_client=on_client,
            object_store=FakeObjectStore(),
            provider_config=PROVIDER,
        )
        db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/outline",
        json={"content_source": "notebook", "tone": "professional", "density": "standard"},
        headers=auth(seed.author_a_sub),
    )

    assert resp.status_code == 201, resp.text
    assert on_client.searched_scopes, "notebook content source never called search()"
