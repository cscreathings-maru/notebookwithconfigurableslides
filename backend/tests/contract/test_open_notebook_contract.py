"""Contract test for the Open Notebook calls the orchestrator depends on.

Pins the exact HTTP surface. A MockTransport asserts each client method issues the
expected method + path + body and parses the pinned response shape, so upstream drift
fails loudly in CI instead of silently in production (constitution principle IV).

**Verified against the pinned image** `lfnovo/open_notebook:v1-latest`
(digest `sha256:e53f90d6…`) by reading `/app/api/main.py` and `/app/api/routers/`:

| Call | Route | Source |
|---|---|---|
| create_notebook | `POST /api/notebooks` | `routers/notebooks.py:132` |
| add_source_file | `POST /api/sources` (multipart) | `routers/sources.py` |
| add_source_link | `POST /api/sources/json` | `routers/sources.py:708` |
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


def _raw_recorder(status: int, payload: dict):
    """Like `_recorder`, but keeps the body as bytes — multipart is not JSON."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["content_type"] = request.headers.get("content-type", "")
        seen["raw"] = request.content
        return httpx.Response(status, json=payload)

    return handler, seen


async def test_add_source_file_uploads_the_bytes() -> None:
    """Files must be UPLOADED, not linked.

    `type: "link"` selects the engine's web-page extractor. A .docx behind a presigned
    object-store URL failed in under a second with `started_at: null` and "Could not
    extract content from this source" — the binary never reached a document handler.
    This test pins the upload surface so that regression cannot return silently.
    """
    # Arrange
    handler, seen = _raw_recorder(201, {"id": "source:src_456"})

    # Act
    source_id = await _client(handler).add_source_file(
        notebook_id="notebook:nb_123",
        filename="Panduan.docx",
        content=b"PK\x03\x04 fake docx bytes",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )

    # Assert -- request shape
    assert source_id == "source:src_456"
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/sources"
    assert seen["content_type"].startswith("multipart/form-data")

    body = seen["raw"]
    # Every field arrives as form data: booleans are strings, `notebooks` a JSON array.
    assert b'name="type"' in body and b"upload" in body
    assert b'"notebook:nb_123"' in body, "notebooks must be a JSON array string"
    assert b'name="embed"' in body and b"true" in body
    # The file itself crossed the boundary -- this is the whole point of the fix.
    assert b"fake docx bytes" in body
    assert b"Panduan.docx" in body


async def test_add_source_link_pinned_call() -> None:
    """Real web URLs keep the JSON path -- unchanged behaviour for user-supplied links."""
    # Arrange
    handler, seen = _recorder(201, {"id": "source:src_456"})

    # Act
    source_id = await _client(handler).add_source_link(
        notebook_id="notebook:nb_123",
        url="https://example.test/article",
    )

    # Assert
    assert source_id == "source:src_456"
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/sources/json"
    assert seen["body"]["notebooks"] == ["notebook:nb_123"]
    assert seen["body"]["type"] == "link"
    assert seen["body"]["url"] == "https://example.test/article"
    assert seen["body"]["embed"] is True


async def test_source_status_maps_engine_states() -> None:
    # Arrange / Act / Assert -- each engine string collapses to our three-state model
    for raw, expected in [
        ("completed", "ready"),
        ("indexed", "ready"),
        ("failed", "failed"),
        ("cancelled", "failed"),
    ]:
        handler, seen = _recorder(200, {"status": raw, "message": f"command {raw}"})
        progress = await _client(handler).get_source_status(source_id="source:src_456")
        assert progress.state == expected, raw
        assert seen["path"] == "/api/sources/source:src_456/status"


async def test_ambiguous_status_falls_back_to_the_embedded_flag() -> None:
    """An empty or unknown command status is not authoritative; `embedded` is."""

    # Arrange -- status says nothing useful, the source record says embedded
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": ""})
        return httpx.Response(200, json={"id": "source:src_456", "embedded": True})

    # Act
    progress = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert progress.state == "ready"


async def test_not_embedded_and_unknown_status_stays_processing() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "queued"})
        return httpx.Response(200, json={"id": "source:src_456", "embedded": False})

    # Act
    progress = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert progress.state == "processing"


async def test_search_pinned_call_and_response_shape() -> None:
    # Arrange
    # The real payload, verbatim from a live instance: snippets live under `matches`
    # (a LIST), the source is `parent_id`, and there is no scalar `content` field.
    handler, seen = _recorder(
        200,
        {
            "results": [
                {
                    "id": "source:src_456",
                    "matches": ["Revenue grew 12%."],
                    "parent_id": "source:src_456",
                    "similarity": 0.335,
                    "title": "q3.docx",
                }
            ],
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


async def test_multiple_matches_on_one_hit_are_all_kept() -> None:
    """A hit carries every matched chunk; dropping any loses grounding the engine found."""
    # Arrange
    handler, _seen = _recorder(
        200,
        {
            "results": [
                {
                    "matches": ["Bab 3 — Daftar BRImerchant", "Untuk Siapa Panduan Ini?"],
                    "parent_id": "source:src_456",
                }
            ],
            "total_count": 1,
        },
    )

    # Act
    results = await _client(handler).search(
        allowed_source_refs={"source:src_456"}, query="merchant"
    )

    # Assert
    assert len(results) == 1
    assert "Bab 3 — Daftar BRImerchant" in results[0]["text"]
    assert "Untuk Siapa Panduan Ini?" in results[0]["text"]


async def test_a_hit_with_no_usable_text_is_dropped_not_fabricated() -> None:
    """An unrecognised payload yields no grounding rather than an empty citation."""
    # Arrange
    handler, _seen = _recorder(
        200, {"results": [{"parent_id": "source:src_456", "matches": []}], "total_count": 1}
    )

    # Act
    results = await _client(handler).search(
        allowed_source_refs={"source:src_456"}, query="merchant"
    )

    # Assert
    assert results == []


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


async def test_a_failed_status_carries_the_engines_own_reason() -> None:
    """`SourceStatusResponse.message` is required, and it is the only thing that tells a
    user *why* a source failed. Discarding it left "Analysis failed for this source." —
    a string this codebase wrote, carrying nothing the engine had said."""
    # Arrange
    handler, _seen = _recorder(
        200,
        {
            "status": "failed",
            "message": "Unsupported file type: could not extract text",
            "processing_info": {"error": "content-core found no extractor for .docx"},
        },
    )

    # Act
    progress = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert progress.state == "failed"
    assert progress.detail is not None
    assert "Unsupported file type" in progress.detail
    assert "content-core" in progress.detail, "processing_info detail must survive too"


async def test_a_status_with_no_message_is_not_fabricated() -> None:
    """Absent detail stays absent; the caller decides what to say, not this client."""
    # Arrange
    handler, _seen = _recorder(200, {"status": "failed"})

    # Act
    progress = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert progress.state == "failed"
    assert progress.detail is None


async def test_the_engine_detail_is_length_capped() -> None:
    """Source.error is String(1024); an unbounded engine payload must not overflow it."""
    # Arrange
    handler, _seen = _recorder(200, {"status": "failed", "message": "x" * 5000})

    # Act
    progress = await _client(handler).get_source_status(source_id="source:src_456")

    # Assert
    assert progress.detail is not None
    assert len(progress.detail) <= 1024
