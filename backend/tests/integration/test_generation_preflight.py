"""T-2.2: both generation paths must pass the same quota gate and be metered.

The freeform (Studio) path called neither `QuotaService.enforce` nor
`MeteringService.record`. Since the rollups count `action == "generation.created"`
and Studio is the primary user path, `/usage` reported zero generations for the way
people actually use the product -- and quota could be bypassed entirely by choosing
the Studio path.

These tests fail against the pre-T-2.2 freeform service.
"""

from __future__ import annotations

import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.main import app
from src.models import Tenant
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, FakePresenton

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}

FREEFORM_PAYLOAD = {
    "content_source": "custom",
    "custom_markdown": "## Findings\n\nRevenue grew.",
    "tone": "professional",
    "density": "standard",
    "n_slides": 5,
}


class CapturingAlertSink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


@pytest.fixture
def alert_sink() -> CapturingAlertSink:
    return CapturingAlertSink()


@pytest.fixture(autouse=True)
def _wire(alert_sink):
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: FakePresenton()
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
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


def _freeform(client, sub: str, project_id: str):
    return client.post(
        f"/api/v1/projects/{project_id}/generations",
        json=FREEFORM_PAYLOAD,
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


def test_freeform_generation_is_counted_in_usage(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    before = _usage(client, seed)["tenant"]["generations"]

    # Act
    assert _freeform(client, seed.author_a_sub, project_id).status_code == 202

    # Assert -- the dashboard can see the path users actually use
    assert _usage(client, seed)["tenant"]["generations"] == before + 1


def test_freeform_usage_record_identifies_the_path(client, seed: Fixtures) -> None:
    """Both paths emit the same action, so the resource has to say which ran."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act
    _freeform(client, seed.author_a_sub, project_id)

    # Assert
    audit = client.get("/api/v1/audit", headers=auth(seed.admin_a_sub)).json()
    created = [e for e in audit if e["action"] == "generation.created"]
    assert created, "freeform generation emitted no usage record"
    assert created[0]["resource"]["path"] == "freeform"


def test_freeform_is_blocked_when_quota_is_exhausted(client, seed: Fixtures) -> None:
    # Arrange -- one generation allowed
    _set_byok(client, seed)
    _set_quota(seed.tenant_a, 1)
    project_id = _project(client, seed.author_a_sub)

    # Act
    first = _freeform(client, seed.author_a_sub, project_id)
    second = _freeform(client, seed.author_a_sub, project_id)

    # Assert
    assert first.status_code == 202
    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "quota_exceeded"


def test_blocked_freeform_attempt_writes_no_generation(client, seed: Fixtures) -> None:
    """Quota runs before any row is written, so a rejected attempt leaves nothing."""
    # Arrange
    _set_byok(client, seed)
    _set_quota(seed.tenant_a, 1)
    project_id = _project(client, seed.author_a_sub)
    _freeform(client, seed.author_a_sub, project_id)

    # Act
    assert _freeform(client, seed.author_a_sub, project_id).status_code == 429

    # Assert -- still exactly the one generation that was allowed
    listed = client.get(
        f"/api/v1/projects/{project_id}/generations", headers=auth(seed.author_a_sub)
    ).json()
    assert len(listed) == 1


def test_quota_breach_on_the_freeform_path_alerts(client, seed: Fixtures, alert_sink) -> None:
    # Arrange
    _set_byok(client, seed)
    _set_quota(seed.tenant_a, 1)
    project_id = _project(client, seed.author_a_sub)

    # Act
    _freeform(client, seed.author_a_sub, project_id)
    _freeform(client, seed.author_a_sub, project_id)

    # Assert
    assert any(e.get("type") == "quota_exceeded" for e in alert_sink.events)
