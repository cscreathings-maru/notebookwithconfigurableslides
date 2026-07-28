"""Contract test for the Open Notebook calls the orchestrator depends on.

Pins the exact HTTP surface. A MockTransport asserts each client method issues the
expected method + path + body and parses the pinned response shape, so upstream drift
fails loudly in CI instead of silently in production (constitution principle IV).

**Verified against the pinned image** `lfnovo/open_notebook:v1-latest`
(digest `sha256:e53f90d6…`) by reading `/app/api/main.py` and `/app/api/routers/`:

| Call | Route | Source |
|---|---|---|
| create_notebook | `POST /api/notebooks` | `routers/notebooks.py:132` |
| add_source | `POST /api/sources/json` | `routers/sources.py:708` |
| get_source_status | `GET /api/sources/{id}/status` | `routers/sources.py:843` |
| _is_embedded | `GET /api/sources/{id}` | `routers/sources.py:755` |
| search | `POST /api/search` | `routers/search.py:21` |

Every router mounts with `prefix="/api"` (`main.py:383-399`) — there is no version
segment. This module previously pinned an assumed `/api/v1/...` surface referencing an
undefined `OPEN_NOTEBOOK_API_VERSION`, and was skipped at module level, so none of its
assertions had run since the client was rewritten (tech debt TD-12).
"""

from __future__ import annotations

import json

import httpx

from src.engines.open_notebook import OpenNotebookClient

BASE = "http://open-notebook.test"


def _client(handler) -> OpenNotebookClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE)
    return OpenNotebookClient(client=http)


def _recorder(status: int, payload: dict):
    """A handler that records the request and replies with `payload`."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(status, json=payload)

    return handler, seen


async def test_create_notebook_pinned_call() -> None:
    # Arrange
    handler, seen = _recorder(201, {"id": "notebook:nb_123"})

    # Act
    notebook_id = await _client(handler).create_notebook(name="Acme Q3", namespace="acme")

    # Assert
    assert notebook_id == "notebook:nb_123"
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/notebooks"
    assert seen["body"]["name"] == "Acme Q3"
    # The real NotebookCreate takes name + description; namespace rides in the latter.
    assert "acme" in seen["body"]["description"]


async def test_add_source_pinned_call() -> None:
    # Arrange
    handler, seen = _recorder(201, {"id": "source:src_456"})

    # Act
    source_id = await _client(handler).add_source(
        notebook_id="notebook:nb_123",
        uri="https://objectstore.test/tenant/doc.pdf",
        provider_config={"provider": "deepseek"},
    )

    # Assert
    assert source_id == "source:src_456"
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/sources/json"
    assert seen["body"]["notebooks"] == ["notebook:nb_123"]
    assert seen["body"]["type"] == "link"
    assert seen["body"]["url"] == "https://objectstore.test/tenant/doc.pdf"
    assert seen["body"]["embed"] is True


async def test_source_status_maps_engine_states() -> None:
    # Arrange / Act / Assert -- each engine string collapses to our three-state model
    for raw, expected in [
        ("completed", "ready"),
        ("indexed", "ready"),
        ("failed", "failed"),
        ("cancelled", "failed"),
    ]:
        handler, seen = _recorder(200, {"status": raw})
        status = await _client(handler).get_source_status(source_id="source:src_456")
        assert status == expected, raw
        assert seen["path"] == "/api/sources/source:src_456/status"


async def test_ambiguous_status_falls_back_to_the_embedded_flag() -> None:
    """An empty or unknown command status is not authoritative; `embedded` is."""

    # Arrange -- status says nothing useful, the source record says embedded
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": ""})
        return httpx.Response(200, json={"id": "source:src_456", "embedded": True})

    # Act
    status = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert status == "ready"


async def test_not_embedded_and_unknown_status_stays_processing() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "queued"})
        return httpx.Response(200, json={"id": "source:src_456", "embedded": False})

    # Act
    status = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert status == "processing"


async def test_search_pinned_call_and_response_shape() -> None:
    # Arrange
    handler, seen = _recorder(
        200,
        {
            "results": [{"content": "Revenue grew 12%.", "parent_id": "source:src_456"}],
            "total_count": 1,
            "search_type": "vector",
        },
    )

    # Act
    results = await _client(handler).search(
        allowed_source_refs={"source:src_456"}, query="revenue"
    )

    # Assert -- request shape
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/search"
    assert seen["body"]["type"] == "vector"
    assert seen["body"]["search_sources"] is True
    # Notes carry no source parent, so they cannot be project-scoped -- never searched.
    assert seen["body"]["search_notes"] is False

    # Assert -- response mapping
    assert results == [{"text": "Revenue grew 12%.", "source_ref": "source:src_456"}]


async def test_search_availability_failure_degrades_to_no_grounding() -> None:
    """A 400 (e.g. no embedding model configured) must not fail the caller."""
    # Arrange
    handler, _seen = _recorder(400, {"detail": "Vector search requires an embedding model."})

    # Act
    results = await _client(handler).search(
        allowed_source_refs={"source:src_456"}, query="revenue"
    )

    # Assert
    assert results == []
