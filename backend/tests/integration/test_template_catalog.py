"""Integration: LD-3 template cataloguing lifecycle + LD-4 admin review.

`create_template` enqueues an LD-2 cataloguing job rather than running it
inline (an LLM call belongs in a job, not a request/response cycle) -- these
tests never rely on a real Arq worker being up (none is, in this harness).
Instead, `_run_catalog_job` plays the worker's role directly against
`deck/catalog.py::catalog_template` + `FakeLlm`, exactly the way
`test_ingestion.py::_run_ingest` calls `ingest_source` directly rather than
spinning up Arq -- proving the SERVICE logic, not the queue plumbing.
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from pptx import Presentation

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.core.errors import EngineError
from src.deck.catalog import catalog_template
from src.deck.dump import dump_presentation
from src.main import app
from src.models import Job, JobStatus, JobType, Template
from src.registry.repository import TemplateRepository
from src.registry.service import apply_catalog_result
from src.registry.house_template import HOUSE_TEMPLATE_PATH
from src.workers.tasks import run_catalog_template
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore

PROVIDER = {
    "provider": "openrouter",
    "base_url": "https://api.openrouter.ai/v1",
    "model": "moonshotai/kimi-k3",
    "api_key": "sk-or-test",
}


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


@pytest.fixture(autouse=True)
def _wire():
    store = FakeObjectStore()
    app.dependency_overrides[api_deps.get_object_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def _bri_bytes() -> bytes:
    if not HOUSE_TEMPLATE_PATH.exists():
        pytest.fail(f"House template missing: {HOUSE_TEMPLATE_PATH}")
    return HOUSE_TEMPLATE_PATH.read_bytes()


def _empty_pptx_bytes() -> bytes:
    buf = io.BytesIO()
    Presentation().save(buf)
    return buf.getvalue()


def _create_template(client, sub: str, name: str, *, file: bool = False) -> dict:
    kwargs: dict = {
        "data": {"name": name, "brand_tokens": json.dumps({})},
        "headers": auth(sub),
    }
    if file:
        kwargs["files"] = {
            "file": (
                "bri.pptx",
                _bri_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        }
    resp = client.post("/api/v1/templates", **kwargs)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _row_id(logical_id: uuid.UUID) -> uuid.UUID:
    with SessionLocal() as db:
        return db.query(Template).filter(Template.logical_id == logical_id).one().id


def _catalog_job(tenant_id: uuid.UUID, template_row_id: uuid.UUID) -> Job:
    with SessionLocal() as db:
        job = (
            db.query(Job)
            .filter(
                Job.tenant_id == tenant_id,
                Job.type == JobType.catalog_template,
                Job.ref_id == template_row_id,
            )
            .one()
        )
        return job


async def _run_catalog_job(tenant_id: uuid.UUID, template_row_id: uuid.UUID, *, llm=None) -> None:
    """Plays `workers/tasks.py::run_catalog_template`'s role without Arq --
    loads the template, dumps + catalogues it, and applies the result."""
    with SessionLocal() as db:
        template = TemplateRepository(db, tenant_id).get(template_row_id)
        pptx_bytes = FakeObjectStore().get_bytes(key=template.source_pptx_uri)
        dumps = dump_presentation(pptx_bytes)
        catalog, _usage = await catalog_template(dumps=dumps, llm=llm or FakeLlm(), provider_config={})
        apply_catalog_result(template, catalog=catalog, error=None)
        db.add(template)
        db.commit()


def test_create_with_pptx_starts_cataloguing_without_blocking_the_request(
    client, seed: Fixtures
) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    # Cataloguing does not block: the response is 201 before any LLM call runs.
    assert template["catalog_status"] == "cataloguing"
    assert template["catalog_reviewed"] is False


def test_create_without_pptx_never_starts_cataloguing(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Blank")
    assert template["catalog_status"] == "no_source"


def test_create_enqueues_a_catalog_template_job(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    job = _catalog_job(seed.tenant_a, row_id)
    assert job.status == JobStatus.queued
    assert job.type == JobType.catalog_template


@pytest.mark.asyncio
async def test_catalog_becomes_ready_after_the_job_runs(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    with SessionLocal() as db:
        row = db.query(Template).filter(Template.logical_id == uuid.UUID(template["id"])).one()
        row_id = row.id

    await _run_catalog_job(seed.tenant_a, row_id)

    resp = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub))
    updated = next(t for t in resp.json() if t["id"] == template["id"])
    assert updated["catalog_status"] == "ready"
    assert updated["catalog_reviewed"] is False


@pytest.mark.asyncio
async def test_admin_can_read_the_catalog_after_cataloguing(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    await _run_catalog_job(seed.tenant_a, row_id)

    resp = client.get(f"/api/v1/templates/{template['id']}/catalog", headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["designs"]) == 30
    assert any(d["usable"] for d in body["designs"])


def test_catalog_not_ready_before_the_job_runs(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    resp = client.get(f"/api/v1/templates/{template['id']}/catalog", headers=auth(seed.admin_a_sub))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "catalog_not_ready"


def test_viewer_cannot_read_the_catalog(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    resp = client.get(f"/api/v1/templates/{template['id']}/catalog", headers=auth(seed.author_a_sub))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_review_marks_the_catalog_reviewed(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    await _run_catalog_job(seed.tenant_a, row_id)

    resp = client.post(
        f"/api/v1/templates/{template['id']}/catalog/review",
        json={},
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["catalog_reviewed"] is True


@pytest.mark.asyncio
async def test_review_can_correct_the_catalog(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    await _run_catalog_job(seed.tenant_a, row_id)

    original = client.get(
        f"/api/v1/templates/{template['id']}/catalog", headers=auth(seed.admin_a_sub)
    ).json()
    corrected_designs = original["designs"]
    corrected_designs[0]["role"] = "cover_corrected_by_admin"

    resp = client.post(
        f"/api/v1/templates/{template['id']}/catalog/review",
        json={"designs": corrected_designs},
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 200, resp.text

    reread = client.get(
        f"/api/v1/templates/{template['id']}/catalog", headers=auth(seed.admin_a_sub)
    ).json()
    assert reread["designs"][0]["role"] == "cover_corrected_by_admin"


def test_review_before_ready_is_rejected(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    resp = client.post(
        f"/api/v1/templates/{template['id']}/catalog/review",
        json={},
        headers=auth(seed.admin_a_sub),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "catalog_not_ready"


@pytest.mark.asyncio
async def test_recatalog_resets_review_state(client, seed: Fixtures) -> None:
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    await _run_catalog_job(seed.tenant_a, row_id)
    client.post(
        f"/api/v1/templates/{template['id']}/catalog/review", json={}, headers=auth(seed.admin_a_sub)
    )

    resp = client.post(f"/api/v1/templates/{template['id']}/recatalog", headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text
    assert resp.json()["catalog_status"] == "cataloguing"

    await _run_catalog_job(seed.tenant_a, row_id)
    listing = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    updated = next(t for t in listing if t["id"] == template["id"])
    assert updated["catalog_reviewed"] is False  # LD-3: a fresh catalog is unreviewed again


@pytest.mark.asyncio
async def test_terminal_failure_never_leaves_the_job_row_silently_stuck(client, seed: Fixtures) -> None:
    """The template with no slides at all (python-pptx's bundled default, 0
    slides) exercises `catalog_template`'s terminal ValidationError path
    end-to-end through `apply_catalog_result` -- the row must land at
    `failed` with a reason, never stay silently at `cataloguing` forever."""
    from src.core.errors import ValidationError

    resp = client.post(
        "/api/v1/templates",
        data={"name": "Empty", "brand_tokens": "{}"},
        files={
            "file": (
                "empty.pptx",
                _empty_pptx_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
        headers=auth(seed.admin_a_sub),
    )
    template = resp.json()
    assert template["catalog_status"] == "cataloguing"

    row_id = _row_id(uuid.UUID(template["id"]))
    with SessionLocal() as db:
        row = TemplateRepository(db, seed.tenant_a).get(row_id)
        pptx_bytes = FakeObjectStore().get_bytes(key=row.source_pptx_uri)
        dumps = dump_presentation(pptx_bytes)

        with pytest.raises(ValidationError):
            await catalog_template(dumps=dumps, llm=FakeLlm(), provider_config={})

        apply_catalog_result(row, catalog=None, error="Template has no slides to catalogue.")
        db.add(row)
        db.commit()

    listing = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    updated = next(t for t in listing if t["id"] == template["id"])
    assert updated["catalog_status"] == "failed"
    assert updated["catalog_error"]


class _RaisingLlm:
    """Stands in for a provider whose response has `content: null` -- the
    2026-08-17 production failure. Raises the SAME `EngineError`
    `LlmClient.catalog_template` raises in that case."""

    async def catalog_template(self, **kwargs):
        raise EngineError("LLM returned an unparseable design catalog.")


@pytest.mark.asyncio
async def test_run_catalog_template_marks_job_and_template_failed_on_engine_error(
    client, seed: Fixtures, monkeypatch
) -> None:
    """The exact production bug (2026-08-17): `run_catalog_template` used to
    treat `EngineError` as transient and re-raise it for Arq to retry,
    NEVER calling the code that marks the `Job` row `failed` -- so a
    template whose LLM call kept failing stayed at `catalog_status:
    "cataloguing"` / `Job.status: "running"` forever, invisible to an admin
    and to any UI. Both must now land in a terminal, visible state."""
    _set_byok(client, seed)
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    job = _catalog_job(seed.tenant_a, row_id)

    monkeypatch.setattr("src.engines.llm.LlmClient", _RaisingLlm)
    monkeypatch.setattr("src.workers.tasks.get_object_store", lambda: FakeObjectStore())

    await run_catalog_template({}, str(job.id), str(seed.tenant_a))

    with SessionLocal() as db:
        refreshed_job = db.get(Job, job.id)
        assert refreshed_job.status == JobStatus.failed
        assert refreshed_job.error

    listing = client.get("/api/v1/templates", headers=auth(seed.admin_a_sub)).json()
    updated = next(t for t in listing if t["id"] == template["id"])
    assert updated["catalog_status"] == "failed"
    assert updated["catalog_error"]


@pytest.mark.asyncio
async def test_recatalog_after_a_failure_creates_a_genuinely_new_job(
    client, seed: Fixtures, monkeypatch
) -> None:
    """The exact production bug's other half (2026-08-17): `recatalog`'s
    idempotency key was `catalog_template:{template.id}` -- IDENTICAL to the
    original `create()` call's key, since the template row id never changes.
    `JobService.create()`'s own dedupe then always found the ORIGINAL
    (however old, however permanently failed) job and returned it unchanged
    -- `/recatalog` could click all day and never actually start a new
    attempt. Each call must now produce its own distinct job row."""
    _set_byok(client, seed)
    template = _create_template(client, seed.admin_a_sub, "Imported", file=True)
    row_id = _row_id(uuid.UUID(template["id"]))
    first_job = _catalog_job(seed.tenant_a, row_id)

    monkeypatch.setattr("src.engines.llm.LlmClient", _RaisingLlm)
    monkeypatch.setattr("src.workers.tasks.get_object_store", lambda: FakeObjectStore())
    await run_catalog_template({}, str(first_job.id), str(seed.tenant_a))

    recatalog_resp = client.post(
        f"/api/v1/templates/{template['id']}/recatalog", headers=auth(seed.admin_a_sub)
    )
    assert recatalog_resp.status_code == 200, recatalog_resp.text

    with SessionLocal() as db:
        jobs = (
            db.query(Job)
            .filter(Job.tenant_id == seed.tenant_a, Job.type == JobType.catalog_template, Job.ref_id == row_id)
            .all()
        )
        assert len(jobs) == 2, "recatalog must create a NEW job row, not reuse the failed one"
        assert len({j.idempotency_key for j in jobs}) == 2
        assert any(j.id != first_job.id and j.status == JobStatus.queued for j in jobs)
