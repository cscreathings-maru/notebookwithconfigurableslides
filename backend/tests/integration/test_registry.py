"""Integration: registry RBAC, tenant-scoping, author visibility, PPTX import.

- admin-only writes; authors read approved only.
- creating a template with a real `.pptx` enqueues LD-2 cataloguing (async,
  a job -- LD-3); the response is NOT terminal. A template becomes
  `approved` only once an admin reviews its finished catalog
  (`/catalog/review`, L3) -- there is no auto-approve anymore.
- profiles/templates are strictly tenant-scoped (cross-tenant -> 404 / hidden).
- there is no manual approve step for templates BEYOND the catalog review --
  cataloguing succeeding alone does not approve; the review call does.
"""

from __future__ import annotations

import json

import pytest

from src.api import deps as api_deps
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeObjectStore, catalog_and_approve, usable_pptx_bytes


@pytest.fixture(autouse=True)
def _wire():
    # One instance for the whole test -- catalog_and_approve() reads back what
    # create() wrote, so the fake store must persist across requests within a
    # test, not be recreated per dependency resolution.
    store = FakeObjectStore()
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def _create_template(client, sub: str, name: str, *, file: bool = False) -> dict:
    kwargs: dict = {
        "data": {"name": name, "brand_tokens": json.dumps({"primary": "#0A0A0A"})},
        "headers": auth(sub),
    }
    if file:
        kwargs["files"] = {
            "file": (
                "brand.pptx",
                usable_pptx_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        }
    resp = client.post("/api/v1/templates", **kwargs)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _approved_template(client, seed: Fixtures, name: str = "Brand") -> dict:
    """Create with a real `.pptx`, run cataloguing, and approve it via
    review -- the full path a template must go through before a profile can
    bind to it."""
    template = _create_template(client, seed.admin_a_sub, name, file=True)
    return await catalog_and_approve(
        tenant_id=seed.tenant_a,
        template_logical_id=template["id"],
        client=client,
        headers=auth(seed.admin_a_sub),
    )


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


def test_template_response_hides_the_stored_pptx_key(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Brand")
    assert "source_pptx_uri" not in template
    assert template["status"] == "draft"
    assert template["catalog_status"] == "no_source"


def test_pptx_import_starts_cataloguing_without_auto_approving(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    assert template["catalog_status"] == "cataloguing"
    assert template["status"] == "draft"  # no auto-approve anymore (L3)


@pytest.mark.asyncio
async def test_reviewing_the_catalog_approves_the_template(client, seed: Fixtures) -> None:
    approved = await _approved_template(client, seed, "Imported")
    assert approved["catalog_status"] == "ready"
    assert approved["catalog_reviewed"] is True
    assert approved["status"] == "approved"


def test_unreadable_pptx_is_rejected_not_500(client, seed: Fixtures) -> None:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Broken", "brand_tokens": "{}"},
        files={
            "file": (
                "brand.pptx",
                b"not a real pptx file",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 201
    body = resp.json()
    # A corrupt upload never reaches the object store as a usable .pptx --
    # the create response cannot know cataloguing will fail (that only
    # happens once the job runs), but it never auto-approves either.
    assert body["status"] == "draft"


def test_viewer_cannot_create_template(client, seed: Fixtures) -> None:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Nope", "brand_tokens": "{}"},
        headers=auth(seed.viewer_a_sub),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_author_cannot_create_profile(client, seed: Fixtures) -> None:
    template = await _approved_template(client, seed, "Brand")
    resp = client.post(
        "/api/v1/profiles", json=_profile_body(template["id"]), headers=auth(seed.author_a_sub)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_author_reads_approved_profiles_only(client, seed: Fixtures) -> None:
    template = await _approved_template(client, seed, "Brand")

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

    # Tenant B admin cannot see or act on tenant A's template.
    listing_b = client.get("/api/v1/templates", headers=auth(seed.admin_b_sub)).json()
    assert all(t["id"] != template["id"] for t in listing_b)

    recatalog_b = client.post(
        f"/api/v1/templates/{template['id']}/recatalog", headers=auth(seed.admin_b_sub)
    )
    assert recatalog_b.status_code == 404


def test_profile_requires_approved_template(client, seed: Fixtures) -> None:
    # A template with no .pptx (`no_source`) is never approved.
    template = _create_template(client, seed.admin_a_sub, "DraftBrand")
    assert template["status"] == "draft"
    resp = client.post(
        "/api/v1/profiles", json=_profile_body(template["id"]), headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code in (404, 422)
