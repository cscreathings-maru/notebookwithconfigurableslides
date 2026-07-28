"""T-1.6: a template that fell back to the stock theme must say so.

`register_template` deliberately does not fail template creation when the engine
rejects or is unreachable -- but the previous code returned the bare ref `"default"`
from two independent handlers, so the row was indistinguishable from a healthy one.
A user uploaded branded PPTX, saw "Template created", and silently got stock slides
forever. These tests pin the outcome to the API response.
"""

from __future__ import annotations

import json

import pytest

from src.api import deps as api_deps
from src.main import app
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
        data={"name": name, "brand_tokens": json.dumps({"primary": "#FF00FF"})},
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


def test_successful_registration_is_reported_as_registered(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton())

    # Act
    body = _create_template(client, seed.admin_a_sub, "Healthy")

    # Assert
    assert body["registration_status"] == "registered"
    assert body["registration_error"] is None


def test_failed_registration_still_creates_the_template(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton(register_error=_ENGINE_DOWN))

    # Act -- creation must not hard-fail; the fallback is intentional
    body = _create_template(client, seed.admin_a_sub, "Degraded")

    # Assert
    assert body["status"] == "draft"
    assert body["name"] == "Degraded"


def test_failed_registration_is_visible_in_the_api(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton(register_error=_ENGINE_DOWN))

    # Act
    body = _create_template(client, seed.admin_a_sub, "Degraded")

    # Assert -- the reason survives to the client, not just the log
    assert body["registration_status"] == "fallback"
    assert body["registration_error"] == _ENGINE_DOWN


def test_fallback_status_survives_a_list_read(client, seed: Fixtures) -> None:
    # Arrange
    _wire(FakePresenton(register_error=_ENGINE_DOWN))
    created = _create_template(client, seed.admin_a_sub, "Degraded")

    # Act
    listed = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()

    # Assert
    row = next(t for t in listed if t["id"] == created["id"])
    assert row["registration_status"] == "fallback"


def test_engine_ref_still_never_reaches_the_client(client, seed: Fixtures) -> None:
    """The new field exposes the outcome, not the engine handle."""
    # Arrange
    _wire(FakePresenton())

    # Act
    body = _create_template(client, seed.admin_a_sub, "Healthy")

    # Assert
    assert "presenton_template_ref" not in body
    assert "source_pptx_uri" not in body
