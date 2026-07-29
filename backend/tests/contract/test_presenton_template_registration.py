"""T-1.3: template registration must satisfy the engine's declared request model.

**This is why branding never reached a deck.** The old client sent
`{"name", "source_pptx_url"}` to `POST /api/v1/ppt/templates/init`. The engine's
`InitTemplateRequest` declares:

    pptx_url: str                    # required
    slide_image_urls: list[str]      # required
    fonts / name / description / icon_type   # optional

There is no `source_pptx_url` field, and neither required field was supplied — so
every call failed validation with a 422, took the `>= 400` branch, and fell back to
the stock theme. The configured brand tokens were never the problem; the request was.

Registration is therefore two steps, and **the uploaded PPTX *is* the brand** — `init`
accepts no colour or font parameters and derives layouts, palette and typography from
the deck itself.

Verified against `ghcr.io/presenton/presenton:latest`,
`api/v1/ppt/endpoints/template.py` (`InitTemplateRequest` at :81, `/init` at :988) and
`templates/fonts_and_slides_preview.py` (`FontsUploadAndSlidesPreviewResponse` at :69).
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


def _client(handler) -> PresentonClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)
    return PresentonClient(client=http)


def _two_step(preview_status: int = 200, init_status: int = 201, init_body=None):
    """Handler covering both registration calls, recording each request."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "fonts-upload-and-slides-preview" in request.url.path:
            seen["preview_path"] = request.url.path
            seen["preview_content_type"] = request.headers.get("content-type", "")
            seen["preview_body"] = request.content
            return httpx.Response(preview_status, json=PREVIEW_OK)
        seen["init_path"] = request.url.path
        seen["init_body"] = json.loads(request.content)
        body = "template_abc123" if init_body is None else init_body
        return httpx.Response(init_status, json=body)

    return handler, seen


async def test_registration_uploads_the_pptx_then_initialises() -> None:
    # Arrange
    handler, seen = _two_step()

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert -- both steps ran, in order
    assert seen["preview_path"] == "/api/v1/ppt/templates/fonts-upload-and-slides-preview"
    assert seen["init_path"] == "/api/v1/ppt/templates/init"
    assert result.status is RegistrationStatus.registered
    assert result.ref == "template_abc123"


async def test_the_pptx_is_uploaded_as_multipart_not_a_url() -> None:
    """`init` cannot accept a file; the preview step is a real upload."""
    # Arrange
    handler, seen = _two_step()

    # Act
    await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert "multipart/form-data" in seen["preview_content_type"]
    assert PPTX in seen["preview_body"]


async def test_init_sends_every_field_the_engine_declares_required() -> None:
    """The exact regression: both required fields were previously absent."""
    # Arrange
    handler, seen = _two_step()

    # Act
    await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    body = seen["init_body"]
    assert body["pptx_url"] == PREVIEW_OK["pptx_url"]
    assert body["slide_image_urls"] == PREVIEW_OK["slide_image_urls"]
    assert body["name"] == "acme__Brand"
    # The field the old client sent, which the engine does not declare at all.
    assert "source_pptx_url" not in body


async def test_fonts_from_the_preview_are_carried_into_init() -> None:
    """Typography is part of the brand and is discovered during the upload step."""
    # Arrange
    handler, seen = _two_step()

    # Act
    await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert seen["init_body"]["fonts"] == PREVIEW_OK["fonts"]


async def test_a_bare_string_id_is_accepted() -> None:
    """`/init` is declared `response_model=str`, so the body is not an object."""
    # Arrange
    handler, _seen = _two_step(init_body="just_the_id")

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert result.ref == "just_the_id"
    assert result.status is RegistrationStatus.registered


async def test_no_pptx_reports_fallback_without_calling_the_engine() -> None:
    """Colour pickers alone cannot brand a deck -- the engine has no parameter for them."""
    # Arrange
    handler, seen = _two_step()

    # Act
    result = await _client(handler).register_template(name="acme__NoDeck")

    # Assert
    assert result.status is RegistrationStatus.fallback
    assert "pptx" in (result.error or "").lower()
    assert seen == {}, "no request should be issued when there is nothing to upload"


@pytest.mark.parametrize(
    ("preview_status", "init_status"), [(422, 201), (500, 201), (200, 422)]
)
async def test_either_step_failing_reports_fallback_not_success(
    preview_status: int, init_status: int
) -> None:
    # Arrange
    handler, _seen = _two_step(preview_status=preview_status, init_status=init_status)

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert -- creation still succeeds, but the degradation is recorded (T-1.6)
    assert result.status is RegistrationStatus.fallback
    assert result.ref == "default"
    assert result.error


async def test_a_preview_without_a_pptx_url_is_not_treated_as_success() -> None:
    # Arrange -- engine answered 200 but did not give us what init needs
    def handler(request: httpx.Request) -> httpx.Response:
        if "preview" in request.url.path:
            return httpx.Response(200, json={"slide_image_urls": [], "fonts": {}})
        return httpx.Response(201, json="unreachable")

    # Act
    result = await _client(handler).register_template(
        name="acme__Brand", pptx_bytes=PPTX, pptx_filename="brand.pptx"
    )

    # Assert
    assert result.status is RegistrationStatus.fallback
