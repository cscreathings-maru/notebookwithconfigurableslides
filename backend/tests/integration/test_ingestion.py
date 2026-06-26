"""Integration: project creation + source upload + ingest pipeline.

Covers the full author flow with the engine and object store faked:
- POST /projects creates a project and an Open Notebook notebook (id hidden).
- POST /projects/{id}/sources stores the file and queues an ingest job.
- the ingest service drives a source to `ready` and records analysis.
- a corrupt/unsupported source is flagged `failed` without breaking the project
  or other sources.
"""

from __future__ import annotations

import uuid

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.ingestion.service import ingest_source
from src.main import app
from src.models import Source, SourceStatus
from tests.conftest import Fixtures, auth
from tests.fakes import FakeObjectStore, FakeOpenNotebook

PROVIDER = {"provider": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-x"}


@pytest.fixture
def fake_on() -> FakeOpenNotebook:
    return FakeOpenNotebook(notebook_id="nb_acme", source_id="src_1")


@pytest.fixture
def fake_store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture(autouse=True)
def _wire(fake_on: FakeOpenNotebook, fake_store: FakeObjectStore):
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: fake_on
    app.dependency_overrides[api_deps.get_object_store] = lambda: fake_store
    yield
    app.dependency_overrides.clear()


def _create_project(client, sub: str, name: str = "Q3 Board Deck") -> dict:
    resp = client.post("/api/v1/projects", json={"name": name}, headers=auth(sub))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_file(client, sub: str, project_id: str, filename: str = "doc.pdf") -> dict:
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        files={"file": (filename, b"%PDF-1.4 fake", "application/pdf")},
        headers=auth(sub),
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _run_ingest(source_id: str, tenant_id: uuid.UUID, on_client) -> None:
    with SessionLocal() as db:
        await ingest_source(
            db=db,
            source_id=uuid.UUID(source_id),
            tenant_id=tenant_id,
            on_client=on_client,
            object_store=FakeObjectStore(),
            provider_config=PROVIDER,
        )
        db.commit()


def test_create_project_hides_notebook_id(client, seed: Fixtures) -> None:
    body = _create_project(client, seed.author_a_sub)
    assert "on_notebook_id" not in body
    assert body["name"] == "Q3 Board Deck"


def test_viewer_cannot_create_project(client, seed: Fixtures) -> None:
    resp = client.post(
        "/api/v1/projects", json={"name": "Nope"}, headers=auth(seed.viewer_a_sub)
    )
    assert resp.status_code == 403


async def test_upload_to_ready(client, seed: Fixtures, fake_on: FakeOpenNotebook) -> None:
    project = _create_project(client, seed.author_a_sub)
    source = _upload_file(client, seed.author_a_sub, project["id"])

    # Queued, with engine ids never exposed.
    assert source["status"] == "queued"
    assert "on_source_id" not in source

    await _run_ingest(source["id"], seed.tenant_a, fake_on)

    detail = client.get(f"/api/v1/sources/{source['id']}", headers=auth(seed.author_a_sub))
    assert detail.status_code == 200
    assert detail.json()["status"] == "ready"
    assert "on_source_id" not in detail.json()

    # Engine ids + analysis stored server-side only.
    with SessionLocal() as db:
        row = db.get(Source, uuid.UUID(source["id"]))
        assert row.on_source_id == "src_1"
        assert row.analysis_ref == "analysis_fake"


async def test_corrupt_source_fails_without_breaking_project(
    client, seed: Fixtures
) -> None:
    project = _create_project(client, seed.author_a_sub)

    # Bad source: the engine rejects it during analysis.
    bad = _upload_file(client, seed.author_a_sub, project["id"], filename="corrupt.pdf")
    failing_on = FakeOpenNotebook(notebook_id="nb_acme", status_sequence=["failed"])
    await _run_ingest(bad["id"], seed.tenant_a, failing_on)

    bad_detail = client.get(f"/api/v1/sources/{bad['id']}", headers=auth(seed.author_a_sub))
    assert bad_detail.json()["status"] == "failed"
    assert bad_detail.json()["error"]

    # The project is intact and a healthy source still ingests to ready.
    proj_detail = client.get(
        f"/api/v1/projects/{project['id']}", headers=auth(seed.author_a_sub)
    )
    assert proj_detail.status_code == 200

    good = _upload_file(client, seed.author_a_sub, project["id"], filename="good.pdf")
    good_on = FakeOpenNotebook(notebook_id="nb_acme", source_id="src_good")
    await _run_ingest(good["id"], seed.tenant_a, good_on)
    good_detail = client.get(f"/api/v1/sources/{good['id']}", headers=auth(seed.author_a_sub))
    assert good_detail.json()["status"] == "ready"


def test_cross_tenant_project_returns_404(client, seed: Fixtures) -> None:
    project = _create_project(client, seed.author_a_sub)
    # Tenant B user must not see tenant A's project.
    resp = client.get(f"/api/v1/projects/{project['id']}", headers=auth(seed.user_b_sub))
    assert resp.status_code == 404


async def test_ingest_is_idempotent(client, seed: Fixtures, fake_on: FakeOpenNotebook) -> None:
    project = _create_project(client, seed.author_a_sub)
    source = _upload_file(client, seed.author_a_sub, project["id"])

    await _run_ingest(source["id"], seed.tenant_a, fake_on)
    # Re-running on an already-ready source must not re-add it to the engine.
    calls_before = fake_on.calls.count("add_source")
    await _run_ingest(source["id"], seed.tenant_a, fake_on)
    assert fake_on.calls.count("add_source") == calls_before
