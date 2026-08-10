"""T-1.6 / TM-2 / TM-3: a template's registration outcome must be honest and visible.

`register_template` deliberately does not fail template creation when the engine
rejects or is unreachable -- the outcome is recorded instead. TM-2 made registration
an async job (`POST /templates` returns `pending` immediately; the worker drives it
to a terminal state), and TM-3 split the old single `fallback` value into
`pending`/`registered`/`failed`/`no_source` so "still working" and "the engine said
no" stop looking identical.
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

_ENGINE_DOWN = "ConnectError: engine unreachable"


def _wire(presenton: FakePresenton):
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: presenton
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _create_template(client, sub: str, name: str) -> dict:
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


async def _drive_to_terminal(seed: Fixtures, template_id: str, presenton: FakePresenton) -> None:
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


def test_creation_starts_pending_not_a_guess_at_the_outcome(client, seed: Fixtures) -> None:
    """TM-2: the row can't claim an outcome the job hasn't produced yet."""
    # Arrange
    _wire(FakePresenton())

    # Act
    body = _create_template(client, seed.admin_a_sub, "Healthy")

    # Assert
    assert body["registration_status"] == "pending"
    assert body["status"] == "draft"


async def test_successful_registration_is_reported_as_registered(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton())
    created = _create_template(client, seed.admin_a_sub, "Healthy")

    # Act
    await _drive_to_terminal(seed, created["id"], FakePresenton())

    # Assert
    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    row = next(t for t in listed if t["id"] == created["id"])
    assert row["registration_status"] == "registered"
    assert row["registration_error"] is None
    assert row["status"] == "approved"  # TM-4: auto-approved


async def test_failed_registration_still_keeps_the_template(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton())
    created = _create_template(client, seed.admin_a_sub, "Degraded")

    # Act -- the engine is down when the job actually runs
    await _drive_to_terminal(seed, created["id"], FakePresenton(register_error=_ENGINE_DOWN))

    # Assert -- registration failing must not delete or hide the row
    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    row = next(t for t in listed if t["id"] == created["id"])
    assert row["name"] == "Degraded"
    assert row["status"] == "draft"  # never auto-approved


async def test_failed_registration_is_visible_in_the_api(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton())
    created = _create_template(client, seed.admin_a_sub, "Degraded")

    # Act
    await _drive_to_terminal(seed, created["id"], FakePresenton(register_error=_ENGINE_DOWN))

    # Assert -- the reason survives to the client, not just the log
    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    row = next(t for t in listed if t["id"] == created["id"])
    assert row["registration_status"] == "failed"
    assert row["registration_error"] == _ENGINE_DOWN


async def test_no_pptx_is_no_source_not_failed(client, seed: Fixtures) -> None:
    """TM-3: nothing went wrong, there's just nothing to register -- distinct from
    an engine rejection, and distinct from still being in flight."""
    # Arrange
    _wire(FakePresenton())
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Tokens Only", "brand_tokens": "{}"},
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 202, resp.text
    created = resp.json()

    # Act
    await _drive_to_terminal(seed, created["id"], FakePresenton())

    # Assert
    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    row = next(t for t in listed if t["id"] == created["id"])
    assert row["registration_status"] == "no_source"
    assert row["status"] == "draft"


async def test_engine_ref_still_never_reaches_the_client(client, seed: Fixtures) -> None:
    """The status field exposes the outcome, not the engine handle."""
    # Arrange
    _wire(FakePresenton())
    created = _create_template(client, seed.admin_a_sub, "Healthy")

    # Act
    await _drive_to_terminal(seed, created["id"], FakePresenton())

    # Assert
    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    row = next(t for t in listed if t["id"] == created["id"])
    assert "presenton_template_ref" not in row
    assert "source_pptx_uri" not in row
