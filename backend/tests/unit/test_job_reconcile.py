"""A job whose Redis entry was lost must be recoverable.

Postgres holds the durable `Job`; Redis holds only the pending queue. Nothing reconciled
the two, and `redis:7` ran with no volume and no persistence — so every Redis restart
silently emptied the queue and left rows at `status=queued, attempts=0` forever, with no
error and no retry.

Observed in production: two ingest jobs stranded for three days while the worker reported
healthy and idle. Sources showed "queued" in the UI, the guide stayed empty, and chat
truthfully said it had no sources. Nothing looked broken anywhere.

T-1.4 fixed enqueuing before the row was committed. This is the opposite end: the row
committed, the queue entry gone.
"""

from __future__ import annotations

import uuid

import pytest

from src.core.db import SessionLocal
from src.models import Job, JobStatus, JobType
from src.workers.reconcile import reenqueue_stranded_jobs


# The `seed` fixture creates a queued tenant-B job, which is itself legitimately
# stranded and will be re-enqueued. Assertions therefore target the specific job under
# test rather than absolute counts.
class RecordingEnqueuer:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.fail_on = fail_on

    def enqueued_ids(self) -> set[str]:
        return {call[1] for call in self.calls}

    async def enqueue_job(self, task_name, job_id, tenant_id, *, _job_id=None):
        if self.fail_on is not None and self.fail_on in str(job_id):
            raise RuntimeError("redis unavailable")
        self.calls.append((task_name, str(job_id), _job_id))


def _job(tenant_id: uuid.UUID, *, status=JobStatus.queued, attempts=0, type_=JobType.ingest):
    with SessionLocal() as db:
        job = Job(
            tenant_id=tenant_id,
            type=type_,
            status=status,
            attempts=attempts,
            idempotency_key=f"{type_.value}:{uuid.uuid4()}",
            ref_id=uuid.uuid4(),
            progress={"step": "queued", "percent": 0},
        )
        db.add(job)
        db.commit()
        return job.id


async def test_a_stranded_job_is_re_enqueued(seed) -> None:
    # Arrange -- committed row, no queue entry
    job_id = _job(seed.tenant_a)
    enqueuer = RecordingEnqueuer()

    # Act
    pushed = await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert pushed >= 1
    assert str(job_id) in [c[1] for c in enqueuer.calls]


async def test_re_enqueue_uses_the_idempotency_key(seed) -> None:
    """Arq dedupes on `_job_id`, so a job still queued is a no-op, not a duplicate."""
    # Arrange
    _job(seed.tenant_a)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert all(call[2] for call in enqueuer.calls), "an unkeyed enqueue could duplicate work"


async def test_the_right_task_is_dispatched_per_type(seed) -> None:
    # Arrange
    _job(seed.tenant_a, type_=JobType.ingest)
    _job(seed.tenant_a, type_=JobType.generate)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    names = {call[0] for call in enqueuer.calls}
    assert names == {"run_ingest", "run_generate"}


async def test_jobs_already_being_worked_are_left_alone(seed) -> None:
    """attempts > 0 means a worker has it; re-enqueuing would duplicate in-flight work."""
    # Arrange
    in_flight = _job(seed.tenant_a, attempts=2)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert str(in_flight) not in enqueuer.enqueued_ids()


@pytest.mark.parametrize("status", [JobStatus.succeeded, JobStatus.failed, JobStatus.running])
async def test_only_queued_jobs_are_reconciled(seed, status) -> None:
    # Arrange
    terminal = _job(seed.tenant_a, status=status)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert str(terminal) not in enqueuer.enqueued_ids()


async def test_reconciliation_returns_a_count_not_an_error(seed) -> None:
    """The common case on a healthy restart: it runs and reports, never raises."""
    # Act
    pushed = await reenqueue_stranded_jobs(RecordingEnqueuer())

    # Assert
    assert isinstance(pushed, int) and pushed >= 0


async def test_no_enqueuer_is_survivable(seed) -> None:
    """Reconciliation must never stop the worker from starting."""
    # Arrange
    _job(seed.tenant_a)

    # Act / Assert
    assert await reenqueue_stranded_jobs(None) == 0


async def test_one_failing_enqueue_does_not_abandon_the_rest(seed) -> None:
    # Arrange -- three stranded jobs, one of which will fail to enqueue
    doomed = _job(seed.tenant_a)
    survivor_a = _job(seed.tenant_a)
    survivor_b = _job(seed.tenant_a)
    enqueuer = RecordingEnqueuer(fail_on=str(doomed))

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert -- one bad job must not strand the others a second time
    enqueued = enqueuer.enqueued_ids()
    assert str(doomed) not in enqueued
    assert {str(survivor_a), str(survivor_b)} <= enqueued
