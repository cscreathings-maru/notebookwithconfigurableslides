"""Contract: registry versioning + immutability invariant.

Per the data model: editing a profile creates a NEW version, and any version
referenced by a Generation is immutable. For profiles that still means "status
cannot transition" (manual approve, unchanged). For templates (TM-4: no manual
approve anymore -- registration success auto-approves) the immutability
invariant that matters is TM-5's delete guard: a template version in use by a
Generation cannot be deleted, which is the same protection `VersionInUseError`
already gave profiles/templates before, just enforced at a different verb now
that there is nothing left to "transition" on a template.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.main import app
from src.models import Generation, GenerationStatus
from src.registry.registration import run_template_registration
from src.registry.repository import TemplateRepository
from tests.conftest import Fixtures, auth
from tests.fakes import FakeObjectStore, FakePresenton


@pytest.fixture(autouse=True)
def _wire_presenton():
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: FakePresenton()
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
    yield
    app.dependency_overrides.clear()


async def _approved_template(client, seed: Fixtures, sub: str, name: str = "Brand") -> dict:
    resp = client.post(
        "/api/v1/templates",
        data={"name": name, "brand_tokens": json.dumps({"primary": "#101010"})},
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
    created = resp.json()
    with SessionLocal() as db:
        row = TemplateRepository(db, seed.tenant_a).latest(uuid.UUID(created["id"]))
        await run_template_registration(
            db=db,
            template_row_id=row.id,
            tenant_id=seed.tenant_a,
            presenton=FakePresenton(),
            object_store=FakeObjectStore(),
        )
        db.commit()
    listed = client.get("/api/v1/templates", headers=auth(sub)).json()
    template = next(t for t in listed if t["id"] == created["id"])
    assert template["status"] == "approved"  # TM-4
    return template


def _create_profile(client, sub: str, template_id: str, name: str = "Group Management") -> dict:
    body = {
        "name": name,
        "audience": "executive leadership",
        "template_id": template_id,
        "tone": "professional",
        "verbosity": "standard",
        "slide_min": 8,
        "slide_max": 12,
        "language": "en",
        "section_structure": [{"title": "Introduction"}, {"title": "Results"}],
        "prompt_config": {"system": "Be concise and on-brand."},
    }
    resp = client.post("/api/v1/profiles", json=body, headers=auth(sub))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _mark_profile_used(
    tenant_id: uuid.UUID, profile_id: str, version: int, template_id: str, template_version: int
) -> None:
    with SessionLocal() as db:
        db.add(
            Generation(
                tenant_id=tenant_id,
                profile_id=uuid.UUID(profile_id),
                profile_version=version,
                template_id=uuid.UUID(template_id),
                template_version=template_version,
                status=GenerationStatus.ready,
            )
        )
        db.commit()


async def test_edit_creates_new_version_and_original_is_unchanged(client, seed: Fixtures) -> None:
    template = await _approved_template(client, seed, seed.admin_a_sub)
    profile = _create_profile(client, seed.admin_a_sub, template["id"])
    assert profile["version"] == 1

    client.post(f"/api/v1/profiles/{profile['id']}/approve", headers=auth(seed.admin_a_sub))
    _mark_profile_used(
        seed.tenant_a, profile["id"], 1, template["id"], profile["template_version"]
    )

    edited = client.put(
        f"/api/v1/profiles/{profile['id']}",
        json={
            "name": "Group Management (revised)",
            "audience": "board",
            "template_id": template["id"],
            "tone": "casual",
            "verbosity": "concise",
            "slide_min": 5,
            "slide_max": 7,
            "language": "en",
            "section_structure": [],
            "prompt_config": {},
        },
        headers=auth(seed.admin_a_sub),
    )
    assert edited.status_code == 201, edited.text
    assert edited.json()["version"] == 2
    assert edited.json()["status"] == "draft"

    # The used v1 is untouched: same name, tone, and approved status.
    listing = client.get("/api/v1/profiles", headers=auth(seed.admin_a_sub)).json()
    v1 = next(x for x in listing if x["id"] == profile["id"] and x["version"] == 1)
    assert v1["name"] == "Group Management"
    assert v1["tone"] == "professional"
    assert v1["status"] == "approved"


async def test_used_profile_version_cannot_be_mutated(client, seed: Fixtures) -> None:
    template = await _approved_template(client, seed, seed.admin_a_sub)
    profile = _create_profile(client, seed.admin_a_sub, template["id"])  # draft v1
    _mark_profile_used(
        seed.tenant_a, profile["id"], 1, template["id"], profile["template_version"]
    )

    resp = client.post(
        f"/api/v1/profiles/{profile['id']}/approve", headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "version_in_use"


async def test_unused_draft_profile_can_be_approved(client, seed: Fixtures) -> None:
    template = await _approved_template(client, seed, seed.admin_a_sub)
    profile = _create_profile(client, seed.admin_a_sub, template["id"])
    resp = client.post(
        f"/api/v1/profiles/{profile['id']}/approve", headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_used_template_cannot_be_deleted(client, seed: Fixtures) -> None:
    """TM-5's version of the old "cannot mutate an in-use version" invariant --
    templates have nothing left to transition (TM-4 removed manual approve), so
    the immutability guard now lives on delete instead."""
    template = await _approved_template(client, seed, seed.admin_a_sub, "Locked")
    with SessionLocal() as db:
        db.add(
            Generation(
                tenant_id=seed.tenant_a,
                profile_id=uuid.uuid4(),
                profile_version=1,
                template_id=uuid.UUID(template["id"]),
                template_version=template["version"],
                status=GenerationStatus.ready,
            )
        )
        db.commit()

    delete = client.delete(
        f"/api/v1/templates/{template['id']}", headers=auth(seed.admin_a_sub)
    )
    assert delete.status_code == 409
    assert delete.json()["error"]["code"] == "version_in_use"

    # And it's still there -- a 409 must mean nothing was touched.
    listing = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    assert any(t["id"] == template["id"] for t in listing)


async def test_unused_template_can_be_deleted(client, seed: Fixtures) -> None:
    template = await _approved_template(client, seed, seed.admin_a_sub, "Removable")

    delete = client.delete(
        f"/api/v1/templates/{template['id']}", headers=auth(seed.admin_a_sub)
    )
    assert delete.status_code == 204

    listing = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    assert all(t["id"] != template["id"] for t in listing)
