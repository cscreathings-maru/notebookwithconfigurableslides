"""Repairing a template whose engine registration failed.

Registration ran only at creation, so every template created before T-1.3 -- when the
request omitted two fields the engine declares required -- was permanently stuck with
a failed registration and no engine template behind it. The operator's only route was
re-uploading the same deck under a new name, repeatedly.

The PPTX is already in object storage, so re-registration needs nothing from the
browser. TM-2: reregister is now async too -- it resets to `pending` and returns
immediately, the same as creation; the caller drives (or, in the app, polls) the
worker to see the repaired outcome.
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

ENGINE_DOWN = "ConnectError: engine unreachable"


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


def _wire(presenton: FakePresenton, store: FakeObjectStore) -> None:
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: presenton
    app.dependency_overrides[api_deps.get_object_store] = lambda: store


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _create(client, sub: str, name: str, *, with_pptx: bool = True) -> dict:
    kwargs: dict = {
        "data": {"name": name, "brand_tokens": "{}"},
        "headers": auth(sub),
    }
    if with_pptx:
        kwargs["files"] = {
            "file": (
                "brand.pptx",
                b"PK\x03\x04 fake pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        }
    resp = client.post("/api/v1/templates", **kwargs)
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _drive(seed: Fixtures, store: FakeObjectStore, template_id: str, presenton: FakePresenton) -> None:
    with SessionLocal() as db:
        row = TemplateRepository(db, seed.tenant_a).latest(uuid.UUID(template_id))
        await run_template_registration(
            db=db,
            template_row_id=row.id,
            tenant_id=seed.tenant_a,
            presenton=presenton,
            object_store=store,
        )
        db.commit()


def _get(client, sub: str, template_id: str) -> dict:
    listed = client.get("/api/v1/templates", headers=auth(sub)).json()
    return next(t for t in listed if t["id"] == template_id)


async def test_a_failed_registration_can_be_repaired(client, seed: Fixtures, store) -> None:
    # Arrange -- created while the engine was failing, as every pre-T-1.3 template was
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")
    await _drive(seed, store, created["id"], FakePresenton(register_error=ENGINE_DOWN))
    broken = _get(client, seed.admin_a_sub, created["id"])
    assert broken["registration_status"] == "failed"
    assert broken["preview_url"] is None

    # Act -- retry request, engine now healthy for the retry
    reregister = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    )
    assert reregister.status_code == 200, reregister.text
    assert reregister.json()["registration_status"] == "pending"  # TM-2: async
    await _drive(seed, store, created["id"], FakePresenton())

    # Assert
    repaired = _get(client, seed.admin_a_sub, created["id"])
    assert repaired["registration_status"] == "registered"
    assert repaired["registration_error"] is None
    assert repaired["preview_url"] is not None
    assert repaired["status"] == "approved"  # TM-4


async def test_repair_reuses_the_stored_pptx_without_a_re_upload(
    client, seed: Fixtures, store
) -> None:
    # Arrange
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")
    await _drive(seed, store, created["id"], FakePresenton(register_error=ENGINE_DOWN))

    healthy = FakePresenton()
    client.post(f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub))

    # Act
    await _drive(seed, store, created["id"], healthy)

    # Assert -- the engine received a filename, meaning bytes were read back from storage
    assert healthy.registered, "engine was never called"
    assert healthy.registered[-1]["pptx_filename"] == "brand.pptx"


async def test_repair_does_not_create_a_new_version(client, seed: Fixtures, store) -> None:
    """The template's content is unchanged; only the engine ref was wrong."""
    # Arrange
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")
    await _drive(seed, store, created["id"], FakePresenton(register_error=ENGINE_DOWN))

    # Act
    client.post(f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub))
    await _drive(seed, store, created["id"], FakePresenton())
    repaired = _get(client, seed.admin_a_sub, created["id"])

    # Assert
    assert repaired["version"] == created["version"]
    assert repaired["id"] == created["id"]


async def test_a_still_failing_repair_reports_the_engine_reason(
    client, seed: Fixtures, store
) -> None:
    """A retry that fails again must stay legible, not silently look repaired."""
    # Arrange
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")
    await _drive(seed, store, created["id"], FakePresenton(register_error=ENGINE_DOWN))

    # Act -- engine still broken on the retry
    client.post(f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub))
    await _drive(seed, store, created["id"], FakePresenton(register_error=ENGINE_DOWN))
    repaired = _get(client, seed.admin_a_sub, created["id"])

    # Assert
    assert repaired["registration_status"] == "failed"
    assert repaired["registration_error"] == ENGINE_DOWN
    assert repaired["preview_url"] is None


def test_a_template_with_no_pptx_is_rejected_with_a_reason(
    client, seed: Fixtures, store
) -> None:
    """Colour pickers alone cannot brand a deck -- the engine has no parameter for them."""
    # Arrange
    _wire(FakePresenton(), store)
    created = _create(client, seed.admin_a_sub, "No Deck", with_pptx=False)

    # Act
    resp = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    )

    # Assert
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "no_source_pptx"


def test_repair_requires_admin(client, seed: Fixtures, store) -> None:
    # Arrange
    _wire(FakePresenton(), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")

    # Act
    resp = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.author_a_sub)
    )

    # Assert
    assert resp.status_code == 403


def test_repair_cannot_reach_another_tenants_template(client, seed: Fixtures, store) -> None:
    # Arrange
    _wire(FakePresenton(), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")

    # Act -- tenant B's admin
    resp = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_b_sub)
    )

    # Assert -- 404, never 403: a 403 would confirm the resource exists
    assert resp.status_code == 404
