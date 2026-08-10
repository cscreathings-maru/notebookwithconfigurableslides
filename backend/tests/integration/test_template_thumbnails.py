"""DG-3/TM-2: the engine's slide preview images are persisted and exposed.

`fonts-upload-and-slides-preview` returns `slide_image_urls` -- discarded after
being forwarded to `init`, ever since T-1.3 shipped, and unreachable at all until
TM-1 fixed the plural/singular URL defect. These tests pin that the values now
reach the template row and the API response once registration (now an async job,
TM-2) actually completes, and that a failed/no-source registration reports no
thumbnails rather than stale or fabricated ones.
"""

from __future__ import annotations

import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.main import app
from src.registry.registration import run_template_registration
from src.registry.repository import TemplateRepository
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
        data={"name": name, "brand_tokens": "{}"},
        files={
            "file": (
                "brand.pptx",
                b"PK\x03\x04 fake pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
        headers=auth(sub),
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _drive(seed: Fixtures, template_id: str, presenton: FakePresenton) -> dict:
    with SessionLocal() as db:
        row = TemplateRepository(db, seed.tenant_a).latest(uuid.UUID(template_id))
        await run_template_registration(
            db=db,
            template_row_id=row.id,
            tenant_id=seed.tenant_a,
            presenton=presenton,
            object_store=FakeObjectStore(),
        )
        db.commit()
    return row


async def test_registered_template_carries_its_thumbnails(client, seed: Fixtures) -> None:
    _wire(FakePresenton())
    created = _create_with_pptx(client, seed.admin_a_sub, "Brand Deck")

    await _drive(seed, created["id"], FakePresenton())

    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    body = next(t for t in listed if t["id"] == created["id"])
    assert body["thumbnail_urls"] == [
        "/app_data/acme__Brand Deck-slide-1.png",
        "/app_data/acme__Brand Deck-slide-2.png",
    ]


async def test_no_source_pptx_has_no_thumbnails(client, seed: Fixtures) -> None:
    """No PPTX means nothing for the engine to derive slides from -- empty, not
    fabricated, and distinguishable from a registration that actually produced some."""
    _wire(FakePresenton())
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Tokens Only", "brand_tokens": "{}"},
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 202, resp.text
    created = resp.json()

    await _drive(seed, created["id"], FakePresenton())

    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    body = next(t for t in listed if t["id"] == created["id"])
    assert body["thumbnail_urls"] == []
    assert body["registration_status"] == "no_source"


async def test_failed_registration_has_no_thumbnails(client, seed: Fixtures) -> None:
    _wire(FakePresenton())
    created = _create_with_pptx(client, seed.admin_a_sub, "Broken")

    await _drive(seed, created["id"], FakePresenton(register_error="preview step returned 500"))

    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    body = next(t for t in listed if t["id"] == created["id"])
    assert body["registration_status"] == "failed"
    assert body["thumbnail_urls"] == []


async def test_reregister_refreshes_thumbnails(client, seed: Fixtures) -> None:
    """A reregister is often run to repair a broken registration (T-1.6) -- it
    should refresh thumbnails too, not leave stale/empty ones from the first try."""
    _wire(FakePresenton(register_error="engine unreachable"))
    created = _create_with_pptx(client, seed.admin_a_sub, "Repairable")
    await _drive(seed, created["id"], FakePresenton(register_error="engine unreachable"))
    broken = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    assert next(t for t in broken if t["id"] == created["id"])["thumbnail_urls"] == []

    # The engine recovers; retry.
    client.post(f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub))
    await _drive(seed, created["id"], FakePresenton())

    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    body = next(t for t in listed if t["id"] == created["id"])
    assert body["registration_status"] == "registered"
    assert body["thumbnail_urls"] != []


async def test_list_templates_exposes_thumbnails_alongside_registration_status(
    client, seed: Fixtures
) -> None:
    """The frontend picker's filter (DG-3.1: approved AND registered) needs both
    fields on the same list response -- pins that list carries them once
    registration (now async, TM-2) actually finishes."""
    _wire(FakePresenton())
    created = _create_with_pptx(client, seed.admin_a_sub, "Listed")
    await _drive(seed, created["id"], FakePresenton())

    resp = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub))

    assert resp.status_code == 200, resp.text
    template = next(t for t in resp.json() if t["id"] == created["id"])
    assert template["registration_status"] == "registered"
    assert template["thumbnail_urls"]
