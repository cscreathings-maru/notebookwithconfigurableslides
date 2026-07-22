"""Integration: notebook guide + chat-with-sources over the HTTP stack.

Exercises the NotebookLM-style features end to end with fake engine clients: guide
generation (summary + suggested questions), the RAG chat answer with citations, and
tenant isolation on both. LITE_MODE stays false (SaaS path) — the tenant BYOK config
is seeded like the other integration tests.
"""

from __future__ import annotations

import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.ingestion.service import ingest_source
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}


@pytest.fixture
def on_client() -> FakeOpenNotebook:
    return FakeOpenNotebook()


@pytest.fixture
def llm() -> FakeLlm:
    return FakeLlm()


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture(autouse=True)
def _wire(on_client, llm, store):
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: on_client
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


async def _project_with_ready_source(client, seed: Fixtures, on_client: FakeOpenNotebook) -> str:
    """Create a project + drive one source to ready so it has a notebook to search."""
    project = client.post(
        "/api/v1/projects", json={"name": "Guided"}, headers=auth(seed.author_a_sub)
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


async def test_guide_generates_summary_and_questions(
    client, seed: Fixtures, on_client, llm
) -> None:
    _set_byok(client, seed)
    project_id = await _project_with_ready_source(client, seed, on_client)

    # Before generation the guide does not exist yet.
    missing = client.get(f"/api/v1/projects/{project_id}/guide", headers=auth(seed.author_a_sub))
    assert missing.status_code == 404

    gen = client.post(f"/api/v1/projects/{project_id}/guide", headers=auth(seed.author_a_sub))
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert body["status"] == "ready"
    assert "revenue" in body["summary"].lower()
    assert len(body["suggested_questions"]) == 3
    assert all(q.endswith("?") for q in body["suggested_questions"])
    assert "search" in on_client.calls  # grounded via Open Notebook search

    # Now GET returns the stored guide.
    got = client.get(f"/api/v1/projects/{project_id}/guide", headers=auth(seed.author_a_sub))
    assert got.status_code == 200
    assert got.json()["summary"] == body["summary"]


async def test_chat_answers_with_citations_and_persists(
    client, seed: Fixtures, on_client, llm
) -> None:
    _set_byok(client, seed)
    project_id = await _project_with_ready_source(client, seed, on_client)

    ask = client.post(
        f"/api/v1/projects/{project_id}/chat",
        json={"question": "How did revenue change?"},
        headers=auth(seed.author_a_sub),
    )
    assert ask.status_code == 200, ask.text
    answer = ask.json()
    assert answer["role"] == "assistant"
    assert answer["content"]
    assert len(answer["citations"]) >= 1
    assert answer["citations"][0]["snippet"]

    # Both the user turn and the assistant turn persist, in order.
    thread = client.get(
        f"/api/v1/projects/{project_id}/chat", headers=auth(seed.author_a_sub)
    ).json()
    assert [m["role"] for m in thread] == ["user", "assistant"]
    assert thread[0]["content"] == "How did revenue change?"


async def test_guide_and_chat_are_tenant_isolated(client, seed: Fixtures, on_client, llm) -> None:
    _set_byok(client, seed)
    project_id = await _project_with_ready_source(client, seed, on_client)
    client.post(f"/api/v1/projects/{project_id}/guide", headers=auth(seed.author_a_sub))

    # A different tenant's admin cannot read this project's guide or chat.
    other = auth(seed.admin_b_sub)
    assert client.get(f"/api/v1/projects/{project_id}/guide", headers=other).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}/chat", headers=other).status_code == 404
