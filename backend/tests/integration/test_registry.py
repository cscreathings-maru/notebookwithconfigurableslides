"""Integration: registry RBAC, tenant-scoping, author visibility, PPTX import.

- admin-only writes; authors read approved only.
- profiles/templates are strictly tenant-scoped (cross-tenant -> 404 / hidden).
- creating a template with a PPTX imports it via Presenton (tenant-namespaced);
  engine refs and pptx keys never reach the client.
"""

from __future__ import annotations

import json

import pytest

from src.api import deps as api_deps
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeObjectStore, FakePresenton


@pytest.fixture
def presenton() -> FakePresenton:
    return FakePresenton()


@pytest.fixture(autouse=True)
def _wire(presenton: FakePresenton):
    store = FakeObjectStore()
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: presenton
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def _create_template(client, sub: str, name: str, file: bool = False) -> dict:
    kwargs: dict = {
        "data": {"name": name, "brand_tokens": json.dumps({"primary": "#0A0A0A"})},
        "headers": auth(sub),
    }
    if file:
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


def _approve_template(client, sub: str, template_id: str) -> dict:
    resp = client.post(f"/api/v1/templates/{template_id}/approve", headers=auth(sub))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _profile_body(template_id: str, name: str = "Group Management") -> dict:
    return {
        "name": name,
        "audience": "execs",
        "template_id": template_id,
        "tone": "professional",
        "verbosity": "text-heavy",
        "slide_min": 6,
        "slide_max": 10,
        "language": "en",
        "section_structure": [{"title": "Overview"}],
        "prompt_config": {"system": "stay on brand"},
    }


def test_template_response_hides_engine_ref_and_pptx(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Brand")
    assert "presenton_template_ref" not in template
    assert "source_pptx_uri" not in template
    assert template["status"] == "draft"


def test_pptx_import_calls_presenton_namespaced(
    client, seed: Fixtures, presenton: FakePresenton
) -> None:
    _create_template(client, seed.admin_a_sub, "Imported", file=True)
    last = presenton.registered[-1]
    assert last["source_pptx_path"] is not None  # PPTX was handed to the engine
    assert last["name"].startswith("acme__")  # tenant-namespaced


def test_viewer_cannot_create_template(client, seed: Fixtures) -> None:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Nope", "brand_tokens": "{}"},
        headers=auth(seed.viewer_a_sub),
    )
    assert resp.status_code == 403


def test_author_cannot_create_profile(client, seed: Fixtures) -> None:
    template = _approve_template(
        client, seed.admin_a_sub, _create_template(client, seed.admin_a_sub, "Brand")["id"]
    )
    resp = client.post(
        "/api/v1/profiles", json=_profile_body(template["id"]), headers=auth(seed.author_a_sub)
    )
    assert resp.status_code == 403


def test_author_reads_approved_profiles_only(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Brand")
    _approve_template(client, seed.admin_a_sub, template["id"])

    # One draft profile, one approved profile.
    draft = client.post(
        "/api/v1/profiles",
        json=_profile_body(template["id"], name="Draft Profile"),
        headers=auth(seed.admin_a_sub),
    ).json()
    approved = client.post(
        "/api/v1/profiles",
        json=_profile_body(template["id"], name="Approved Profile"),
        headers=auth(seed.admin_a_sub),
    ).json()
    client.post(f"/api/v1/profiles/{approved['id']}/approve", headers=auth(seed.admin_a_sub))

    listing = client.get("/api/v1/profiles", headers=auth(seed.author_a_sub)).json()
    statuses = {p["status"] for p in listing}
    assert statuses == {"approved"}
    assert all(p["id"] != draft["id"] for p in listing)


def test_templates_are_tenant_scoped(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Brand")

    # Tenant B admin cannot see or approve tenant A's template.
    listing_b = client.get("/api/v1/templates", headers=auth(seed.admin_b_sub)).json()
    assert all(t["id"] != template["id"] for t in listing_b)

    approve_b = client.post(
        f"/api/v1/templates/{template['id']}/approve", headers=auth(seed.admin_b_sub)
    )
    assert approve_b.status_code == 404


def test_profile_requires_approved_template(client, seed: Fixtures) -> None:
    # Draft (unapproved) template cannot back a profile.
    template = _create_template(client, seed.admin_a_sub, "DraftBrand")
    resp = client.post(
        "/api/v1/profiles", json=_profile_body(template["id"]), headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code in (404, 422)
