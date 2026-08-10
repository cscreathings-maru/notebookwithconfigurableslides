"""Integration: registry RBAC, tenant-scoping, author visibility, PPTX import.

- admin-only writes; authors read approved only.
- profiles/templates are strictly tenant-scoped (cross-tenant -> 404 / hidden).
- creating a template with a PPTX queues registration via Presenton (TM-2, async;
  tenant-namespaced); engine refs and pptx keys never reach the client.
- TM-4: there is no manual approve step for templates anymore -- a successful
  registration auto-approves. Governance (approved-template-required) is proven
  by a template that hasn't finished registering yet, not by withholding approval.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.main import app
from src.registry.registration import run_template_registration
from src.registry.repository import TemplateRepository
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
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _registered_template(
    client, seed: Fixtures, sub: str, name: str, *, presenton: FakePresenton | None = None
) -> dict:
    """Create WITH a pptx and drive registration to completion. TM-4 auto-approves
    on success, so this is also "an approved template" -- the only kind there is
    now."""
    created = _create_template(client, sub, name, file=True)
    with SessionLocal() as db:
        row = TemplateRepository(db, seed.tenant_a).latest(uuid.UUID(created["id"]))
        await run_template_registration(
            db=db,
            template_row_id=row.id,
            tenant_id=seed.tenant_a,
            presenton=presenton or FakePresenton(),
            object_store=FakeObjectStore(),
        )
        db.commit()
    listed = client.get("/api/v1/templates", headers=auth(sub)).json()
    return next(t for t in listed if t["id"] == created["id"])


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
    assert template["registration_status"] == "pending"


async def test_pptx_import_calls_presenton_namespaced(
    client, seed: Fixtures, presenton: FakePresenton
) -> None:
    body = await _registered_template(
        client, seed, seed.admin_a_sub, "Imported", presenton=presenton
    )
    last = presenton.registered[-1]
    # T-1.3/TM-1: the PPTX reaches the engine as bytes, because the engine derives
    # the brand from the deck itself. Two different broken request shapes have
    # each caused every registration to fall through to `failed` in the past
    # (a wrong field name, then a wrong URL) -- this pins the outcome, not the
    # transport, so either regression fails it the same way.
    assert last["pptx_filename"] == "brand.pptx"
    assert last["name"].startswith("acme__")  # tenant-namespaced
    assert body["registration_status"] == "registered"
    assert body["status"] == "approved"  # TM-4: auto-approved on success


def test_viewer_cannot_create_template(client, seed: Fixtures) -> None:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Nope", "brand_tokens": "{}"},
        headers=auth(seed.viewer_a_sub),
    )
    assert resp.status_code == 403


async def test_author_cannot_create_profile(client, seed: Fixtures) -> None:
    template = await _registered_template(client, seed, seed.admin_a_sub, "Brand")
    resp = client.post(
        "/api/v1/profiles", json=_profile_body(template["id"]), headers=auth(seed.author_a_sub)
    )
    assert resp.status_code == 403


async def test_author_reads_approved_profiles_only(client, seed: Fixtures) -> None:
    template = await _registered_template(client, seed, seed.admin_a_sub, "Brand")

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

    reregister_b = client.post(
        f"/api/v1/templates/{template['id']}/reregister", headers=auth(seed.admin_b_sub)
    )
    assert reregister_b.status_code == 404


def test_profile_requires_approved_template(client, seed: Fixtures) -> None:
    # A template still `pending` (registration never run) cannot back a profile --
    # TM-4 only auto-approves a template once registration actually succeeds.
    template = _create_template(client, seed.admin_a_sub, "DraftBrand")
    assert template["status"] == "draft"
    resp = client.post(
        "/api/v1/profiles", json=_profile_body(template["id"]), headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code in (404, 422)
