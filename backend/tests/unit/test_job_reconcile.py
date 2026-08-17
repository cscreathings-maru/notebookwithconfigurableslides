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
from datetime import timedelta

import pytest

from src.core.db import SessionLocal
from src.models import Job, JobStatus, JobType
from src.models.base import utcnow
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


def _job(
    tenant_id: uuid.UUID,
    *,
    status=JobStatus.queued,
    attempts=0,
    type_=JobType.ingest,
    updated_at=None,
):
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
        if updated_at is not None:
            # Backdate the row to simulate a worker that claimed this job and
            # then died holding it. `default`/`onupdate` only fire when the
            # attribute is unset, so an explicit value survives the insert.
            job.updated_at = updated_at
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


@pytest.mark.parametrize("status", [JobStatus.succeeded, JobStatus.failed])
async def test_finished_jobs_are_never_reconciled(seed, status) -> None:
    # Arrange
    terminal = _job(seed.tenant_a, status=status)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert str(terminal) not in enqueuer.enqueued_ids()


# --------------------------------------------------------------------------
# Stale `running` jobs (2026-08-17). A worker that dies mid-flight leaves the
# row at `running` forever: nothing retried it, nothing surfaced it, and the
# template it belonged to showed a permanent "cataloguing…" spinner whose only
# escape was a shell on the server.
# --------------------------------------------------------------------------


async def test_a_freshly_running_job_is_left_alone(seed) -> None:
    """A worker is holding it RIGHT NOW -- re-enqueuing would double-run it."""
    # Arrange
    live = _job(seed.tenant_a, status=JobStatus.running, attempts=1)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert str(live) not in enqueuer.enqueued_ids()


async def test_a_long_dead_running_job_is_recovered(seed) -> None:
    """The production failure: `status=running` since yesterday, no worker
    holds it, nothing was ever going to move it again."""
    # Arrange
    dead = _job(
        seed.tenant_a,
        status=JobStatus.running,
        attempts=1,
        type_=JobType.catalog_template,
        updated_at=utcnow() - timedelta(hours=6),
    )
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert str(dead) in enqueuer.enqueued_ids()
    assert ("run_catalog_template", str(dead)) in [(c[0], c[1]) for c in enqueuer.calls]


async def test_a_job_no_task_can_run_is_retired_instead_of_re_logged_forever(seed) -> None:
    """`register_template` jobs outlived the pipeline that handled them. Each
    worker start re-found them and logged ERROR again -- permanent noise that
    would eventually mask a real failure (seen in production 2026-08-17).
    They can never run, so they are recorded as failed and stop coming back."""
    # Arrange
    orphan = _job(seed.tenant_a, type_=JobType.register_template)
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert -- never dispatched...
    assert str(orphan) not in enqueuer.enqueued_ids()
    # ...and now terminal, with a reason, so the next run does not see it
    with SessionLocal() as db:
        row = db.get(Job, orphan)
        assert row.status == JobStatus.failed
        assert "can never run" in row.error

    # Act again -- the second pass must find nothing to complain about
    second = RecordingEnqueuer()
    await reenqueue_stranded_jobs(second)
    assert str(orphan) not in second.enqueued_ids()


async def test_a_running_job_just_inside_the_threshold_is_left_alone(seed) -> None:
    """Guards the boundary in the safe direction: when in doubt, assume the
    job is alive and let it finish rather than risk running it twice."""
    # Arrange -- 29 minutes old, threshold is 30
    borderline = _job(
        seed.tenant_a,
        status=JobStatus.running,
        attempts=1,
        updated_at=utcnow() - timedelta(minutes=29),
    )
    enqueuer = RecordingEnqueuer()

    # Act
    await reenqueue_stranded_jobs(enqueuer)

    # Assert
    assert str(borderline) not in enqueuer.enqueued_ids()


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
