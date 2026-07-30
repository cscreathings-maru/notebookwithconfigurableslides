"""Repairing a template whose engine registration failed.

Registration ran only at creation, so every template created before T-1.3 -- when the
request omitted two fields the engine declares required -- was permanently stuck with
`registration_status = fallback` and no engine template behind it. The operator's only
route was re-uploading the same deck under a new name, repeatedly.

The PPTX is already in object storage, so re-registration needs nothing from the browser.
"""

from __future__ import annotations

import json

import pytest

from src.api import deps as api_deps
from src.main import app
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
        "data": {"name": name, "brand_tokens": json.dumps({"primary": "#0C57C2"})},
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
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_a_failed_registration_can_be_repaired(client, seed: Fixtures, store) -> None:
    # Arrange -- created while the engine was failing, as every pre-T-1.3 template was
    broken = FakePresenton(register_error=ENGINE_DOWN)
    _wire(broken, store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")
    assert created["registration_status"] == "fallback"
    assert created["preview_url"] is None

    # Act -- engine now healthy; retry from the stored PPTX
    _wire(FakePresenton(), store)
    repaired = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    )

    # Assert
    assert repaired.status_code == 200, repaired.text
    body = repaired.json()
    assert body["registration_status"] == "registered"
    assert body["registration_error"] is None
    assert body["preview_url"] is not None


def test_repair_reuses_the_stored_pptx_without_a_re_upload(
    client, seed: Fixtures, store
) -> None:
    # Arrange
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")

    healthy = FakePresenton()
    _wire(healthy, store)

    # Act
    client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    )

    # Assert -- the engine received a filename, meaning bytes were read back from storage
    assert healthy.registered, "engine was never called"
    assert healthy.registered[-1]["pptx_filename"] == "brand.pptx"


def test_repair_does_not_create_a_new_version(client, seed: Fixtures, store) -> None:
    """The template's content is unchanged; only the engine ref was wrong."""
    # Arrange
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")

    # Act
    _wire(FakePresenton(), store)
    repaired = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    ).json()

    # Assert
    assert repaired["version"] == created["version"]
    assert repaired["id"] == created["id"]


def test_a_still_failing_repair_reports_the_engine_reason(
    client, seed: Fixtures, store
) -> None:
    """A retry that fails again must stay legible, not silently look repaired."""
    # Arrange
    _wire(FakePresenton(register_error=ENGINE_DOWN), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")

    # Act -- engine still broken
    repaired = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_a_sub)
    ).json()

    # Assert
    assert repaired["registration_status"] == "fallback"
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


def test_repair_cannot_reach_another_tenants_template(
    client, seed: Fixtures, store
) -> None:
    # Arrange
    _wire(FakePresenton(), store)
    created = _create(client, seed.admin_a_sub, "BRI Deck")

    # Act -- tenant B's admin
    resp = client.post(
        f"/api/v1/templates/{created['id']}/reregister", headers=auth(seed.admin_b_sub)
    )

    # Assert -- 404, never 403: a 403 would confirm the resource exists
    assert resp.status_code == 404
