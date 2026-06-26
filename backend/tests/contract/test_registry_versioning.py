"""Contract: registry versioning + immutability invariant.

Per the data model: editing a profile/template creates a NEW version, and any
version referenced by a Generation is immutable (its status can no longer be
transitioned). These tests pin that behavior.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.main import app
from src.models import Generation, GenerationStatus
from tests.conftest import Fixtures, auth
from tests.fakes import FakePresenton


@pytest.fixture(autouse=True)
def _wire_presenton():
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: FakePresenton()
    yield
    app.dependency_overrides.clear()


def _approved_template(client, sub: str, name: str = "Brand") -> dict:
    resp = client.post(
        "/api/v1/templates",
        data={"name": name, "brand_tokens": json.dumps({"primary": "#101010"})},
        headers=auth(sub),
    )
    assert resp.status_code == 201, resp.text
    template = resp.json()
    approved = client.post(f"/api/v1/templates/{template['id']}/approve", headers=auth(sub))
    assert approved.status_code == 200, approved.text
    return approved.json()


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


def test_edit_creates_new_version_and_original_is_unchanged(client, seed: Fixtures) -> None:
    template = _approved_template(client, seed.admin_a_sub)
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


def test_used_profile_version_cannot_be_mutated(client, seed: Fixtures) -> None:
    template = _approved_template(client, seed.admin_a_sub)
    profile = _create_profile(client, seed.admin_a_sub, template["id"])  # draft v1
    _mark_profile_used(
        seed.tenant_a, profile["id"], 1, template["id"], profile["template_version"]
    )

    resp = client.post(
        f"/api/v1/profiles/{profile['id']}/approve", headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "version_in_use"


def test_unused_draft_profile_can_be_approved(client, seed: Fixtures) -> None:
    template = _approved_template(client, seed.admin_a_sub)
    profile = _create_profile(client, seed.admin_a_sub, template["id"])
    resp = client.post(
        f"/api/v1/profiles/{profile['id']}/approve", headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_used_template_version_cannot_be_mutated(client, seed: Fixtures) -> None:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Locked", "brand_tokens": json.dumps({})},
        headers=auth(seed.admin_a_sub),
    )
    template = resp.json()
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

    approve = client.post(
        f"/api/v1/templates/{template['id']}/approve", headers=auth(seed.admin_a_sub)
    )
    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == "version_in_use"
