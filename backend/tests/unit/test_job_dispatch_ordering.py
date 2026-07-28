"""T-1.4 regression: a job must be committed before it is enqueued.

`get_db()` commits at dependency teardown, after the handler returns. Enqueuing
inside the handler publishes the job to workers before its row exists. A worker that
dequeues first finds nothing, and because `dispatch()` passes the idempotency key as
Arq's `_job_id`, Arq refuses to re-enqueue it for `keep_result` seconds -- so the
generation stays `queued` forever, with no error and no retry.

These tests pin both halves of the fix: the ordering, and the worker's refusal to
fail quietly.
"""

from __future__ import annotations

import uuid

import pytest

from src.core.db import SessionLocal
from src.jobs.repository import JobRepository
from src.jobs.service import JobService
from src.models import Job, JobType
from src.workers.tasks import JobRowMissing, _require_job


class VisibilityProbeEnqueuer:
    """Fake Arq pool that answers: was the row committed when we enqueued?

    A real worker dequeues on its own connection, so the probe uses a separate
    session -- exactly what the racing worker would see.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str | None]] = []
        self.job_visible_at_enqueue: bool | None = None

    async def enqueue_job(
        self, task_name: str, job_id: str, tenant_id: str, *, _job_id: str | None = None
    ) -> None:
        with SessionLocal() as probe:
            self.job_visible_at_enqueue = probe.get(Job, uuid.UUID(job_id)) is not None
        self.calls.append((task_name, job_id, tenant_id, _job_id))


def _new_job(db, tenant_id: uuid.UUID, enqueuer: VisibilityProbeEnqueuer):
    service = JobService(JobRepository(db, tenant_id), enqueuer)
    job, _ = service.create(
        job_type=JobType.generate,
        idempotency_key=f"generate:{uuid.uuid4()}",
        ref_id=uuid.uuid4(),
    )
    return service, job


@pytest.mark.asyncio
async def test_commit_and_dispatch_makes_the_job_visible_before_enqueue(seed) -> None:
    # Arrange
    enqueuer = VisibilityProbeEnqueuer()

    # Act
    with SessionLocal() as db:
        service, job = _new_job(db, seed.tenant_a, enqueuer)
        await service.commit_and_dispatch(job)

    # Assert
    assert enqueuer.job_visible_at_enqueue is True, (
        "worker dequeuing at enqueue time must be able to load the job row"
    )
    assert len(enqueuer.calls) == 1


@pytest.mark.asyncio
async def test_bare_dispatch_enqueues_a_row_no_worker_can_see(seed) -> None:
    """Documents the defect. `dispatch()` alone reproduces the original race."""
    # Arrange
    enqueuer = VisibilityProbeEnqueuer()

    # Act
    with SessionLocal() as db:
        service, job = _new_job(db, seed.tenant_a, enqueuer)
        await service.dispatch(job)

    # Assert
    assert enqueuer.job_visible_at_enqueue is False, (
        "if this passes, the uncommitted-enqueue race is no longer reproducible "
        "and this test has stopped being a regression guard"
    )


def test_worker_raises_when_the_dispatched_row_is_absent(seed) -> None:
    # Arrange
    absent_job_id = uuid.uuid4()

    # Act / Assert -- must raise so Arq retries, not return silently
    with SessionLocal() as db:
        with pytest.raises(JobRowMissing):
            _require_job(db, absent_job_id, seed.tenant_a)


def test_worker_raises_when_the_row_belongs_to_another_tenant(seed) -> None:
    # Arrange -- seed.job_b_id belongs to tenant B
    # Act / Assert
    with SessionLocal() as db:
        with pytest.raises(JobRowMissing):
            _require_job(db, seed.job_b_id, seed.tenant_a)
