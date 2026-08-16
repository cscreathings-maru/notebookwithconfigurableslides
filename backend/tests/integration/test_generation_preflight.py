"""T-2.2: both generation paths must pass the same quota gate and be metered.

The freeform (Studio) path called neither `QuotaService.enforce` nor
`MeteringService.record`. Since the rollups count `action == "generation.created"`
and Studio is the primary user path, `/usage` reported zero generations for the way
people actually use the product -- and quota could be bypassed entirely by choosing
the Studio path.

These tests fail against the pre-T-2.2 freeform service.

RM-11: every generation renders from a real, inspected template now -- there is
no engine-side stock theme to fall back to (D2), so freeform generation requires
selecting one.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.main import app
from src.models import Tenant
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, catalog_and_approve, usable_pptx_bytes

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}


class CapturingAlertSink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


@pytest.fixture
def alert_sink() -> CapturingAlertSink:
    return CapturingAlertSink()


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture(autouse=True)
def _wire(alert_sink, store):
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: FakeOpenNotebook()
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    app.dependency_overrides[api_deps.get_alert_sink] = lambda: alert_sink
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put(
        "/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub)
    )
    assert resp.status_code == 200, resp.text


def _project(client, sub: str) -> str:
    return client.post(
        "/api/v1/projects", json={"name": "Studio"}, headers=auth(sub)
    ).json()["id"]


async def _approved_template_id(client, seed: Fixtures) -> str:
    resp = client.post(
        "/api/v1/templates",
        data={"name": "Brand", "brand_tokens": json.dumps({})},
        files={
            "file": (
                "brand.pptx",
                usable_pptx_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 201, resp.text
    template = resp.json()
    approved = await catalog_and_approve(
        tenant_id=seed.tenant_a,
        template_logical_id=template["id"],
        client=client,
        headers=auth(seed.admin_a_sub),
    )
    return approved["id"]


def _freeform(client, sub: str, project_id: str, template_id: str):
    return client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={
            "content_source": "custom",
            "custom_markdown": "## Findings\n\nRevenue grew.",
            "tone": "professional",
            "density": "standard",
            "n_slides": 5,
            "template_id": template_id,
        },
        headers=auth(sub),
    )


def _usage(client, seed: Fixtures) -> dict:
    resp = client.get("/api/v1/usage", headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_quota(tenant_id: uuid.UUID, limit: int) -> None:
    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        tenant.quota_monthly_generations = limit
        db.add(tenant)
        db.commit()


async def test_freeform_generation_is_counted_in_usage(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    template_id = await _approved_template_id(client, seed)
    before = _usage(client, seed)["tenant"]["generations"]

    # Act
    assert _freeform(client, seed.author_a_sub, project_id, template_id).status_code == 202

    # Assert -- the dashboard can see the path users actually use
    assert _usage(client, seed)["tenant"]["generations"] == before + 1


async def test_freeform_usage_record_identifies_the_path(client, seed: Fixtures) -> None:
    """Both paths emit the same action, so the resource has to say which ran."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    template_id = await _approved_template_id(client, seed)

    # Act
    _freeform(client, seed.author_a_sub, project_id, template_id)

    # Assert
    audit = client.get("/api/v1/audit", headers=auth(seed.admin_a_sub)).json()
    created = [e for e in audit if e["action"] == "generation.created"]
    assert created, "freeform generation emitted no usage record"
    assert created[0]["resource"]["path"] == "freeform"


async def test_freeform_is_blocked_when_quota_is_exhausted(client, seed: Fixtures) -> None:
    # Arrange -- one generation allowed
    _set_byok(client, seed)
    _set_quota(seed.tenant_a, 1)
    project_id = _project(client, seed.author_a_sub)
    template_id = await _approved_template_id(client, seed)

    # Act
    first = _freeform(client, seed.author_a_sub, project_id, template_id)
    second = _freeform(client, seed.author_a_sub, project_id, template_id)

    # Assert
    assert first.status_code == 202
    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "quota_exceeded"


async def test_blocked_freeform_attempt_writes_no_generation(client, seed: Fixtures) -> None:
    """Quota runs before any row is written, so a rejected attempt leaves nothing."""
    # Arrange
    _set_byok(client, seed)
    _set_quota(seed.tenant_a, 1)
    project_id = _project(client, seed.author_a_sub)
    template_id = await _approved_template_id(client, seed)
    _freeform(client, seed.author_a_sub, project_id, template_id)

    # Act
    assert _freeform(client, seed.author_a_sub, project_id, template_id).status_code == 429

    # Assert -- still exactly the one generation that was allowed
    listed = client.get(
        f"/api/v1/projects/{project_id}/generations", headers=auth(seed.author_a_sub)
    ).json()
    assert len(listed) == 1


async def test_quota_breach_on_the_freeform_path_alerts(client, seed: Fixtures, alert_sink) -> None:
    # Arrange
    _set_byok(client, seed)
    _set_quota(seed.tenant_a, 1)
    project_id = _project(client, seed.author_a_sub)
    template_id = await _approved_template_id(client, seed)

    # Act
    _freeform(client, seed.author_a_sub, project_id, template_id)
    _freeform(client, seed.author_a_sub, project_id, template_id)

    # Assert
    assert any(e.get("type") == "quota_exceeded" for e in alert_sink.events)


def test_generation_without_a_template_is_refused_with_a_clear_code(client, seed: Fixtures) -> None:
    """RM-11: there is no default theme -- a template is mandatory. The refusal
    has to say so, and say who can fix it, since a non-admin cannot upload one."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act -- no template_id at all
    resp = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"content_source": "custom", "custom_markdown": "## X\n\nY"},
        headers=auth(seed.author_a_sub),
    )

    # Assert
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "template_required"
    assert "admin" in body["message"].lower()


def test_generation_against_an_unusable_template_names_the_template(client, seed: Fixtures) -> None:
    """A rejected template must not be silently swapped for something else --
    the whole point of D2 is that the chosen template is what renders."""
    # Arrange -- a template with no .pptx never gets a layout catalog
    created = client.post(
        "/api/v1/templates",
        data={"name": "Empty Brand", "brand_tokens": "{}"},
        headers=auth(seed.admin_a_sub),
    )
    assert created.status_code == 201, created.text
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act
    resp = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={
            "content_source": "custom",
            "custom_markdown": "## X\n\nY",
            "template_id": created.json()["id"],
        },
        headers=auth(seed.author_a_sub),
    )

    # Assert
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "template_not_usable"
    assert "Empty Brand" in body["message"]


def test_missing_template_is_refused_before_any_llm_call(client, seed: Fixtures) -> None:
    """The check is hoisted above content resolution on purpose: resolving
    `content_source="notebook"` makes an LLM call, and billing a user for a
    request that was never going to succeed is the defect this guards."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    llm = FakeLlm()
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm

    # Act
    resp = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"content_source": "notebook"},
        headers=auth(seed.author_a_sub),
    )

    # Assert -- refused, and nothing was sent to the provider
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "template_required"
    assert llm.calls == []
