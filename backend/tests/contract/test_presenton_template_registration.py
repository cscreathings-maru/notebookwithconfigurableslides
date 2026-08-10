"""TM-1: template registration must call the paths the engine actually serves.

**This is the test that should have caught the bug it's named after, and didn't.**
The previous version of this file asserted `/api/v1/ppt/templates/...` (plural) as
the *expected* path -- it was testing the client's behaviour against itself, not
against the engine's declared routes, so it passed while every real registration
404'd. Every uploaded template silently rendered the stock theme (TD-32).

Root cause, confirmed against the deployed engine's `openapi.json` 2026-08-06:

    404 /api/v1/ppt/templates/fonts-upload-and-slides-preview   (what the client called)
    422 /api/v1/ppt/template/fonts-upload-and-slides-preview    (what the engine serves)

`TEMPLATE_ROUTER` declares `prefix="/template"` (singular). A 422 on the singular
path is the proof it exists: the route was reached and rejected an empty body.

Second, independent defect stacked behind it: `POST /template/init` returns a
template with `layouts: null` -- a skeleton, not something renderable. The complete
path is `POST /template/async`, confirmed present on the live engine, which returns
an `AsyncTaskModel` to poll via `GET /async-tasks/status/{id}` (outside `/ppt`,
confirmed by the same dump) rather than a finished template synchronously.

`CreateTemplateRequest`'s exact fields (`pptx_url`, `slide_image_urls` required;
`fonts`/`name` optional) and `AsyncTaskModel`'s shape (`id`, `error`, `data`, no
confirmed `status` enum values) are pinned here from that dump, not guessed.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.engines.presenton import PresentonClient
from src.models import RegistrationStatus

BASE = "http://presenton.test"
PPTX = b"PK\x03\x04 fake pptx bytes"

PREVIEW_OK = {
    "slide_image_urls": ["/app_data/preview/1.png", "/app_data/preview/2.png"],
    "pptx_url": "/app_data/uploads/brand.pptx",
    "modified_pptx_url": "/app_data/uploads/brand-modified.pptx",
    "fonts": {"Inter": "/app_data/fonts/Inter.ttf"},
}

# The literal, confirmed-correct routes. Any change to these two strings should
# fail a test loudly -- that is the whole point of this file.
_PREVIEW_PATH = "/api/v1/ppt/template/fonts-upload-and-slides-preview"
_ASYNC_PATH = "/api/v1/ppt/template/async"
_TASK_STATUS_PATH = "/api/v1/async-tasks/status/task_xyz"


def _client(handler) -> PresentonClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)
    return PresentonClient(client=http)


def _happy_path(
    *,
    preview_status: int = 200,
    async_status: int = 201,
    task_body: dict | None = None,
):
    """Handler covering preview -> async create -> one status poll that is
    already terminal. Records every request seen, keyed by which call it was."""
    seen: dict = {}
    default_task = {
        "id": "task_xyz",
        "type": "template_creation",
        "status": "completed",
        "message": None,
        "error": None,
        "data": {"template_id": "template_abc123"},
        "created_at": "2026-08-06T00:00:00Z",
        "updated_at": "2026-08-06T00:00:01Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "fonts-upload-and-slides-preview" in path:
            seen["preview_path"] = path
            seen["preview_content_type"] = request.headers.get("content-type", "")
            seen["preview_body"] = request.content
            return httpx.Response(preview_status, json=PREVIEW_OK)
        if path.endswith("/template/async"):
            seen["async_path"] = path
            seen["async_body"] = json.loads(request.content)
            return httpx.Response(async_status, json={"id": "task_xyz"})
        if "async-tasks/status/" in path:
            seen["status_path"] = path
            return httpx.Response(200, json=task_body if task_body is not None else default_task)
        raise AssertionError(f"unexpected request: {request.method} {path}")

    return handler, seen


async def test_registration_calls_the_singular_template_prefix_the_engine_serves() -> None:
    """The regression test. `/templates/...` (plural) 404s on the real engine;
    `/template/...` (singular) is what TEMPLATE_ROUTER actually declares."""
    # Arrange
    handler, seen = _happy_path()

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert -- literal paths, not a substring/pattern that plural would also match
    assert seen["preview_path"] == _PREVIEW_PATH
    assert seen["async_path"] == _ASYNC_PATH
    assert seen["status_path"] == _TASK_STATUS_PATH
    assert result.status is RegistrationStatus.registered
    assert result.ref == "template_abc123"


async def test_the_pptx_is_uploaded_as_multipart_not_a_url() -> None:
    """The async/init step cannot accept a file; the preview step is a real upload."""
    # Arrange
    handler, seen = _happy_path()

    # Act
    await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert "multipart/form-data" in seen["preview_content_type"]
    assert PPTX in seen["preview_body"]


async def test_async_create_sends_every_field_the_engine_declares_required() -> None:
    """CreateTemplateRequest requires pptx_url and slide_image_urls (TM-0)."""
    # Arrange
    handler, seen = _happy_path()

    # Act
    await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    body = seen["async_body"]
    assert body["pptx_url"] == PREVIEW_OK["pptx_url"]
    assert body["slide_image_urls"] == PREVIEW_OK["slide_image_urls"]
    assert body["name"] == "acme__Brand"
    # The field an even earlier client version sent (T-1.3), which the engine has
    # never declared.
    assert "source_pptx_url" not in body


async def test_fonts_from_the_preview_are_carried_into_the_async_create() -> None:
    """Typography is part of the brand and is discovered during the upload step."""
    # Arrange
    handler, seen = _happy_path()

    # Act
    await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert seen["async_body"]["fonts"] == PREVIEW_OK["fonts"]


async def test_polls_until_the_task_reports_a_result() -> None:
    """A task that isn't terminal yet (error AND data both null) must be polled
    again, not treated as done. Terminal-ness is `error`/`data` presence, not a
    specific `status` string -- AsyncTaskStatus's enum values were not part of
    TM-0's confirmed contract."""
    # Arrange
    polls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "fonts-upload-and-slides-preview" in path:
            return httpx.Response(200, json=PREVIEW_OK)
        if path.endswith("/template/async"):
            return httpx.Response(201, json={"id": "task_xyz"})
        polls.append(path)
        if len(polls) < 3:
            return httpx.Response(
                200,
                json={
                    "id": "task_xyz", "type": "t", "status": "running",
                    "message": None, "error": None, "data": None,
                    "created_at": "x", "updated_at": "x",
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "task_xyz", "type": "t", "status": "completed",
                "message": None, "error": None,
                "data": {"template_id": "template_abc123"},
                "created_at": "x", "updated_at": "x",
            },
        )

    async def no_sleep(_seconds: float) -> None:
        return None

    import src.engines.presenton as presenton_module

    original_sleep = presenton_module.asyncio.sleep
    presenton_module.asyncio.sleep = no_sleep  # type: ignore[assignment]
    try:
        result = await _client(handler).register_template(
            name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
        )
    finally:
        presenton_module.asyncio.sleep = original_sleep  # type: ignore[assignment]

    # Assert -- polled more than once, and the eventual result won
    assert len(polls) == 3
    assert result.status is RegistrationStatus.registered
    assert result.ref == "template_abc123"


async def test_a_task_that_reports_an_error_is_a_failed_registration_not_success() -> None:
    # Arrange
    handler, _seen = _happy_path(
        task_body={
            "id": "task_xyz", "type": "t", "status": "failed",
            "message": None, "error": {"detail": "invalid pptx structure"},
            "data": None, "created_at": "x", "updated_at": "x",
        }
    )

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert result.status is RegistrationStatus.failed
    assert "invalid pptx structure" in (result.error or "")


async def test_no_pptx_reports_no_source_without_calling_the_engine() -> None:
    """Colour pickers alone cannot brand a deck -- the engine has no parameter for
    them. `no_source`, not `failed`: nothing went wrong, there is nothing to
    retry (TM-3)."""
    # Arrange
    handler, seen = _happy_path()

    # Act
    result = await _client(handler).register_template(name="acme__NoDeck")

    # Assert
    assert result.status is RegistrationStatus.no_source
    assert "pptx" in (result.error or "").lower()
    assert seen == {}, "no request should be issued when there is nothing to upload"


@pytest.mark.parametrize(
    ("preview_status", "async_status"), [(422, 201), (500, 201), (200, 422)]
)
async def test_either_step_failing_reports_failed_not_success(
    preview_status: int, async_status: int
) -> None:
    # Arrange
    handler, _seen = _happy_path(preview_status=preview_status, async_status=async_status)

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert -- creation still succeeds, but the degradation is recorded (T-1.6)
    assert result.status is RegistrationStatus.failed
    assert result.ref == "default"
    assert result.error


async def test_a_preview_without_a_pptx_url_is_not_treated_as_success() -> None:
    # Arrange -- engine answered 200 but did not give us what the async step needs
    def handler(request: httpx.Request) -> httpx.Response:
        if "preview" in request.url.path:
            return httpx.Response(200, json={"slide_image_urls": [], "fonts": {}})
        raise AssertionError("should not reach the async step without a pptx_url")

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert result.status is RegistrationStatus.failed


async def test_an_async_create_with_no_task_id_is_not_treated_as_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        if "fonts-upload-and-slides-preview" in request.url.path:
            return httpx.Response(200, json=PREVIEW_OK)
        if request.url.path.endswith("/template/async"):
            return httpx.Response(201, json={"type": "template_creation"})  # no id
        raise AssertionError("should not poll without a task id")

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert result.status is RegistrationStatus.failed
