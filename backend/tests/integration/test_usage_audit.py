"""Integration: usage rollups, quota enforcement, and the audit trail.

- Generating several decks produces correct per-user and per-tenant rollups
  (counts, tokens, cost), with no cross-tenant aggregation.
- A tenant at its monthly quota is blocked, the quota event is recorded, and the
  alert hook fires.
- Mutating/admin actions land in the audit log.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.generation.worker import generate_presentation
from src.ingestion.service import ingest_source
from src.main import app
from src.models import Tenant, UsageRecord
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, FakePresenton

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
def presenton() -> FakePresenton:
    return FakePresenton()


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture
def on_client() -> FakeOpenNotebook:
    return FakeOpenNotebook(notebook_id="nb_acme", source_id="src_1")


@pytest.fixture
def alert_sink() -> CapturingAlertSink:
    return CapturingAlertSink()


@pytest.fixture(autouse=True)
def _wire(presenton, store, on_client, alert_sink):
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: presenton
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: on_client
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    app.dependency_overrides[api_deps.get_alert_sink] = lambda: alert_sink
    yield
    app.dependency_overrides.clear()


# --- helpers -------------------------------------------------------------


def _set_byok(client, seed: Fixtures) -> None:
    assert (
        client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub)).status_code
        == 200
    )


def _approved_profile(client, seed: Fixtures) -> str:
    t = client.post(
        "/api/v1/templates",
        data={"name": "Brand", "brand_tokens": json.dumps({"primary": "#101010"})},
        headers=auth(seed.admin_a_sub),
    ).json()
    client.post(f"/api/v1/templates/{t['id']}/approve", headers=auth(seed.admin_a_sub))
    body = {
        "name": "GM",
        "audience": "execs",
        "template_id": t["id"],
        "tone": "professional",
        "verbosity": "standard",
        "slide_min": 4,
        "slide_max": 12,
        "language": "en",
        "section_structure": [{"title": "Summary"}, {"title": "Results"}],
        "prompt_config": {"system": "x"},
    }
    p = client.post("/api/v1/profiles", json=body, headers=auth(seed.admin_a_sub)).json()
    client.post(f"/api/v1/profiles/{p['id']}/approve", headers=auth(seed.admin_a_sub))
    return p["id"]


async def _project_with_outline(client, seed: Fixtures, sub: str, profile_id: str, on_client) -> tuple[str, str]:
    project = client.post("/api/v1/projects", json={"name": "P"}, headers=auth(sub)).json()
    source = client.post(
        f"/api/v1/projects/{project['id']}/sources",
        files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
        headers=auth(sub),
    ).json()
    with SessionLocal() as db:
        await ingest_source(
            db=db,
            source_id=uuid.UUID(source["id"]),
            tenant_id=seed.tenant_a,
            on_client=on_client,
            object_store=FakeObjectStore(),
            provider_config=PROVIDER,
        )
        db.commit()
    outline = client.post(
        f"/api/v1/projects/{project['id']}/outline",
        json={"profile_id": profile_id},
        headers=auth(sub),
    ).json()
    return project["id"], outline["id"]


async def _generate(client, seed: Fixtures, sub: str, project_id: str, outline_id: str, presenton, store):
    resp = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"outline_id": outline_id},
        headers=auth(sub),
    )
    if resp.status_code != 202:
        return resp
    gen = resp.json()
    with SessionLocal() as db:
        await generate_presentation(
            db=db,
            generation_id=uuid.UUID(gen["id"]),
            tenant_id=seed.tenant_a,
            presenton=presenton,
            object_store=store,
        )
        db.commit()
    return resp


# --- tests ---------------------------------------------------------------


async def test_usage_rollups_per_user_and_tenant(
    client, seed: Fixtures, presenton, store, on_client
) -> None:
    _set_byok(client, seed)
    profile_id = _approved_profile(client, seed)

    # author_a: one outline + two generations; admin_a: one outline + one generation.
    pa, oa = await _project_with_outline(client, seed, seed.author_a_sub, profile_id, on_client)
    await _generate(client, seed, seed.author_a_sub, pa, oa, presenton, store)
    await _generate(client, seed, seed.author_a_sub, pa, oa, presenton, store)

    pb, ob = await _project_with_outline(client, seed, seed.admin_a_sub, profile_id, on_client)
    await _generate(client, seed, seed.admin_a_sub, pb, ob, presenton, store)

    # Cross-tenant noise that must NOT be aggregated into tenant A.
    with SessionLocal() as db:
        db.add(
            UsageRecord(
                tenant_id=seed.tenant_b,
                actor_user_id=None,
                action="generation.created",
                resource={},
                tokens_in=9999,
                tokens_out=9999,
            )
        )
        db.commit()

    usage = client.get("/api/v1/usage", headers=auth(seed.admin_a_sub))
    assert usage.status_code == 200, usage.text
    body = usage.json()

    assert body["tenant"]["generations"] == 3
    # Each outline build meters 120 in / 80 out (FakeLlm); two outlines were built.
    assert body["tenant"]["tokens_in"] == 240
    assert body["tenant"]["tokens_out"] == 160
    assert float(body["tenant"]["cost_estimate"]) > 0

    by_user = {u["user_id"]: u for u in body["per_user"]}
    me_author = client.get("/api/v1/auth/me", headers=auth(seed.author_a_sub)).json()["user"]["id"]
    me_admin = client.get("/api/v1/auth/me", headers=auth(seed.admin_a_sub)).json()["user"]["id"]

    assert by_user[me_author]["generations"] == 2
    assert by_user[me_author]["tokens_in"] == 120
    assert by_user[me_admin]["generations"] == 1
    assert by_user[me_admin]["tokens_in"] == 120

    # Per-user costs sum to the tenant cost (no cross-tenant leakage).
    summed = sum(float(u["cost_estimate"]) for u in body["per_user"])
    assert abs(summed - float(body["tenant"]["cost_estimate"])) < 1e-9

    # Quota status surfaced.
    assert body["quota"]["used_this_month"] == 3


async def test_tenant_at_quota_is_blocked_and_recorded(
    client, seed: Fixtures, presenton, store, on_client, alert_sink
) -> None:
    _set_byok(client, seed)
    profile_id = _approved_profile(client, seed)

    with SessionLocal() as db:
        tenant = db.get(Tenant, seed.tenant_a)
        tenant.quota_monthly_generations = 1
        db.add(tenant)
        db.commit()

    pa, oa = await _project_with_outline(client, seed, seed.author_a_sub, profile_id, on_client)

    first = await _generate(client, seed, seed.author_a_sub, pa, oa, presenton, store)
    assert first.status_code == 202

    second = client.post(
        f"/api/v1/projects/{pa}/generations",
        json={"outline_id": oa},
        headers=auth(seed.author_a_sub),
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "quota_exceeded"

    # The alert hook fired.
    assert any(e.get("type") == "quota_exceeded" for e in alert_sink.events)

    # The event is in the audit log.
    audit = client.get("/api/v1/audit", headers=auth(seed.admin_a_sub)).json()
    assert any(e["action"] == "quota.exceeded" for e in audit)


def test_audit_records_admin_actions_without_secrets(client, seed: Fixtures) -> None:
    # An admin action (BYOK config) must be audited, but the api_key must not appear.
    client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))

    audit = client.get("/api/v1/audit", headers=auth(seed.admin_a_sub))
    assert audit.status_code == 200
    rows = audit.json()
    config_events = [e for e in rows if e["action"] == "tenant.llm_config.updated"]
    assert config_events, "BYOK update should be audited"
    serialized = json.dumps(rows)
    assert "sk-x" not in serialized  # secret never logged


def test_usage_and_audit_require_admin(client, seed: Fixtures) -> None:
    assert client.get("/api/v1/usage", headers=auth(seed.author_a_sub)).status_code == 403
    assert client.get("/api/v1/audit", headers=auth(seed.viewer_a_sub)).status_code == 403
