"""Contract test for the Open Notebook ingest/analyze calls (pinned version).

Pins the exact HTTP surface the orchestrator depends on. A MockTransport asserts
each client method issues the expected method + path + body and parses the pinned
response shape. If the upstream contract drifts, these fail loudly in CI instead of
silently in production (constitution principle IV).
"""

from __future__ import annotations

import httpx
import pytest

from src.engines.open_notebook import OPEN_NOTEBOOK_API_VERSION, OpenNotebookClient

BASE = "http://open-notebook.test"


def _client(handler) -> OpenNotebookClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=BASE)
    return OpenNotebookClient(client=http)


async def test_create_notebook_pinned_call() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "nb_123"})

    client = _client(handler)
    notebook_id = await client.create_notebook(name="Acme Q3", namespace="acme")

    assert notebook_id == "nb_123"
    assert seen["method"] == "POST"
    assert seen["path"] == f"/api/{OPEN_NOTEBOOK_API_VERSION}/notebooks"
    assert seen["body"]["name"] == "Acme Q3"
    assert seen["body"]["namespace"] == "acme"


async def test_add_source_pinned_call() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json={"id": "src_456", "status": "processing"})

    client = _client(handler)
    source_id = await client.add_source(
        notebook_id="nb_123",
        uri="https://objectstore.test/acme/p1/doc.pdf",
        provider_config={"provider": "deepseek", "api_key": "sk-x"},
    )

    assert source_id == "src_456"
    assert seen["method"] == "POST"
    assert seen["path"] == f"/api/{OPEN_NOTEBOOK_API_VERSION}/notebooks/nb_123/sources"
    assert seen["body"]["uri"].endswith("doc.pdf")
    # BYOK provider config is passed per-request to the engine (engine contract).
    assert seen["body"]["provider"]["provider"] == "deepseek"


async def test_get_source_status_pinned_call() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ready"})

    client = _client(handler)
    status = await client.get_source_status(source_id="src_456")

    assert status == "ready"
    assert seen["method"] == "GET"
    assert seen["path"] == f"/api/{OPEN_NOTEBOOK_API_VERSION}/sources/src_456"


async def test_run_transformation_pinned_call() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"analysis_ref": "analysis_789"})

    client = _client(handler)
    ref = await client.run_transformation(
        source_id="src_456", provider_config={"provider": "deepseek"}
    )

    assert ref == "analysis_789"
    assert seen["method"] == "POST"
    assert seen["path"] == f"/api/{OPEN_NOTEBOOK_API_VERSION}/sources/src_456/transformations"


async def test_failed_status_is_parsed_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "failed"})

    client = _client(handler)
    assert await client.get_source_status(source_id="src_456") == "failed"
