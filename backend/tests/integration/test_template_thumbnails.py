"""DG-3: the engine's slide preview images are persisted and exposed.

`fonts-upload-and-slides-preview` already returns `slide_image_urls` -- discarded
after being forwarded to `init`, ever since T-1.3 shipped. These tests pin that the
values now reach the template row and the API response, and that a failed/no-source
registration reports no thumbnails rather than stale or fabricated ones.
"""

from __future__ import annotations

import json

import pytest

from src.api import deps as api_deps
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeObjectStore, FakePresenton


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _wire(presenton: FakePresenton):
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: presenton
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()


def _create_with_pptx(client, sub: str, name: str) -> dict:
    resp = client.post(
        "/api/v1/templates",
        data={"name": name, "brand_tokens": json.dumps({"primary": "#2563EB"})},
        files={
            "file": (
                "brand.pptx",
                b"PK\x03\x04 fake pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
        headers=auth(sub),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_registered_template_carries_its_thumbnails(client, seed: Fixtures) -> None:
    _wire(FakePresenton())

    body = _create_with_pptx(client, seed.admin_a_sub, "Brand Deck")

    assert body["thumbnail_urls"] == [
        "/app_data/acme__Brand Deck-slide-1.png",
        "/app_data/acme__Brand Deck-slide-2.png",
    ]


def test_no_source_pptx_has_no_thumbnails(client, seed: Fixtures) -> None:
    """No PPTX means nothing for the engine to derive slides from -- empty, not
    fabricated, and distinguishable from a registration that actually produced some."""
    _wire(FakePresenton())

    resp = client.post(
        "/api/v1/templates",
        data={"name": "Tokens Only", "brand_tokens": json.dumps({"primary": "#000000"})},
        headers=auth(seed.admin_a_sub),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["thumbnail_urls"] == []
    assert resp.json()["registration_status"] == "fallback"


def test_fallen_back_registration_has_no_thumbnails(client, seed: Fixtures) -> None:
    _wire(FakePresenton(register_error="preview step returned 500"))

    body = _create_with_pptx(client, seed.admin_a_sub, "Broken")

    assert body["registration_status"] == "fallback"
    assert body["thumbnail_urls"] == []


def test_reregister_refreshes_thumbnails(client, seed: Fixtures) -> None:
    """A reregister is often run to repair a broken registration (T-1.6) -- it
    should refresh thumbnails too, not leave stale/empty ones from the first try."""
    broken = FakePresenton(register_error="engine unreachable")
    _wire(broken)
    created = _create_with_pptx(client, seed.admin_a_sub, "Repairable")
    assert created["thumbnail_urls"] == []

    # The engine recovers; wire a healthy fake for the retry.
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: FakePresenton()

    resp = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["registration_status"] == "registered"
    assert resp.json()["thumbnail_urls"] != []


def test_list_templates_exposes_thumbnails_alongside_registration_status(
    client, seed: Fixtures
) -> None:
    """The frontend picker's filter (DG-3.1: approved AND registered) needs both
    fields on the same list response -- pins that list, not just create, carries them."""
    _wire(FakePresenton())
    _create_with_pptx(client, seed.admin_a_sub, "Listed")

    resp = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub))

    assert resp.status_code == 200, resp.text
    template = resp.json()[0]
    assert template["registration_status"] == "registered"
    assert template["thumbnail_urls"]
