"""T-2.1: retrieval must never cross project or tenant boundaries.

The gap this closes: `test_tenant_isolation.py` exercises only the Postgres repository
layer, where `TenantScopedRepository._scoped()` makes an unfiltered query impossible.
The engine tier had no isolation test at all -- and Open Notebook's `POST /api/search`
accepts no notebook filter, so `fn::vector_search` scans every embedding in the
instance. One shared index served every project of every tenant.

Scoping is now enforced on the orchestrator side, against the engine source ids
recorded on the caller's own tenant-scoped rows. These tests hold that line.

Every test here fails against the pre-T-2.1 client, which passed `notebook_id` and
never used it.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from src.core.db import SessionLocal
from src.engines.open_notebook import OpenNotebookClient
from src.ingestion.repository import SourceRepository
from src.ingestion.service import ingest_source
from src.main import app
from src.api import deps as api_deps
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook

BASE = "http://open-notebook.test"

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}

# One global index holding two projects' documents -- the real engine's actual shape.
ALPHA_REF = "source:alpha"
BETA_REF = "source:beta"
CORPUS = {
    ALPHA_REF: "ALPHAONLY Acme quarterly revenue grew twelve percent.",
    BETA_REF: "BETAONLY Globex is being acquired for four billion dollars.",
}


# --------------------------------------------------------------------------
# Engine tier -- the real client against a mocked transport
# --------------------------------------------------------------------------


def _client_returning(results: list[dict]) -> tuple[OpenNotebookClient, dict]:
    """A real client whose engine always returns `results`, plus a record of the request."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": results, "total_count": len(results)})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)
    return OpenNotebookClient(client=http), seen


def _global_results() -> list[dict]:
    """What the engine returns: everything it has, from every project."""
    return [
        {"content": text, "parent_id": ref, "id": f"embedding:{ref}"}
        for ref, text in CORPUS.items()
    ]


async def test_search_results_never_cross_notebooks() -> None:
    # Arrange -- engine returns both projects' documents
    client, _seen = _client_returning(_global_results())

    # Act -- ask with only alpha in scope
    results = await client.search(allowed_source_refs={ALPHA_REF}, query="revenue")

    # Assert
    refs = {r["source_ref"] for r in results}
    assert refs == {ALPHA_REF}
    assert not any("BETAONLY" in r["text"] for r in results)


async def test_search_returns_nothing_when_scope_is_empty() -> None:
    """Fail closed: no allow-set means no grounding, never unscoped grounding."""
    # Arrange
    client, seen = _client_returning(_global_results())

    # Act
    results = await client.search(allowed_source_refs=set(), query="revenue")

    # Assert -- and the engine is not even called
    assert results == []
    assert seen == {}


async def test_search_drops_results_whose_source_cannot_be_resolved() -> None:
    """A hit with no usable source ref is unattributable, so it is not grounding."""
    # Arrange
    client, _seen = _client_returning(
        [{"content": "orphaned chunk with no parent"}, *_global_results()]
    )

    # Act
    results = await client.search(allowed_source_refs={ALPHA_REF}, query="revenue")

    # Assert
    assert [r["source_ref"] for r in results] == [ALPHA_REF]


async def test_search_prefers_parent_id_over_the_rows_own_id() -> None:
    """`source_insight` rows alias `id` to the insight, `parent_id` to the source.

    Matching on `id` would drop a legitimate hit -- failing closed, but silently
    losing recall on every insight the engine returns.
    """
    # Arrange -- an insight row: its own id differs from the source it belongs to
    client, _seen = _client_returning(
        [{"content": "ALPHAONLY insight", "id": "insight:xyz", "parent_id": ALPHA_REF}]
    )

    # Act
    results = await client.search(allowed_source_refs={ALPHA_REF}, query="revenue")

    # Assert
    assert [r["source_ref"] for r in results] == [ALPHA_REF]


async def test_search_over_fetches_so_post_filtering_does_not_starve_recall() -> None:
    # Arrange
    client, seen = _client_returning(_global_results())

    # Act
    await client.search(allowed_source_refs={ALPHA_REF}, query="revenue")

    # Assert -- asks the engine for more than the 10 it will return
    assert seen["body"]["limit"] > 10


# --------------------------------------------------------------------------
# Repository tier -- the allow-set itself cannot span tenants
# --------------------------------------------------------------------------


def test_engine_source_refs_are_tenant_scoped(seed: Fixtures) -> None:
    """The allow-set is built through `_scoped()`, so a foreign id cannot enter it."""
    # Arrange -- tenant B's repository, asked for a project id it does not own
    foreign_project = uuid.uuid4()

    # Act
    with SessionLocal() as db:
        refs = SourceRepository(db, seed.tenant_b).engine_source_refs(foreign_project)

    # Assert
    assert refs == set()


# --------------------------------------------------------------------------
# Service tier -- guide and chat, over the HTTP stack
# --------------------------------------------------------------------------


@pytest.fixture
def shared_index() -> FakeOpenNotebook:
    """The app-level engine client: one index holding both projects' content."""
    return FakeOpenNotebook(corpus=CORPUS)


@pytest.fixture(autouse=True)
def _wire(shared_index):
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: shared_index
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
    yield
    app.dependency_overrides.clear()


async def _project_indexed_as(client, seed: Fixtures, name: str, engine_ref: str) -> str:
    """Create a project and drive its one source to ready under `engine_ref`."""
    project = client.post(
        "/api/v1/projects", json={"name": name}, headers=auth(seed.author_a_sub)
    ).json()
    source = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": (f"{name}.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=auth(seed.author_a_sub),
    ).json()
    with SessionLocal() as db:
        await ingest_source(
            db=db,
            source_id=uuid.UUID(source["id"]),
            tenant_id=seed.tenant_a,
            # This project's source is registered in the engine under `engine_ref`.
            on_client=FakeOpenNotebook(source_id=engine_ref),
            object_store=FakeObjectStore(),
            provider_config=PROVIDER,
        )
        db.commit()
    return project["id"]


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


async def test_guide_is_grounded_only_in_own_project_sources(
    client, seed: Fixtures, shared_index
) -> None:
    # Arrange -- two projects, disjoint sources, one shared engine index
    _set_byok(client, seed)
    alpha = await _project_indexed_as(client, seed, "Alpha", ALPHA_REF)
    await _project_indexed_as(client, seed, "Beta", BETA_REF)

    # Act
    body = client.post(
        f"/api/v1/projects/{alpha}/guide", headers=auth(seed.author_a_sub)
    ).json()

    # Assert -- the scope handed to the engine contained only alpha
    assert shared_index.searched_scopes[-1] == {ALPHA_REF}
    assert "BETAONLY" not in body["summary"]


async def test_chat_citations_reference_only_own_project_sources(
    client, seed: Fixtures, shared_index
) -> None:
    # Arrange
    _set_byok(client, seed)
    alpha = await _project_indexed_as(client, seed, "Alpha", ALPHA_REF)
    await _project_indexed_as(client, seed, "Beta", BETA_REF)

    # Act
    body = client.post(
        f"/api/v1/projects/{alpha}/chat",
        json={"question": "What happened?"},
        headers=auth(seed.author_a_sub),
    ).json()

    # Assert
    assert shared_index.searched_scopes[-1] == {ALPHA_REF}
    for citation in body.get("citations", []):
        assert citation.get("source_ref") != BETA_REF
