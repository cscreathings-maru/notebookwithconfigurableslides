"""Re-enqueue jobs whose Redis entry was lost.

Postgres is the durable record of a job; Redis only holds the *pending* queue. Those
lifetimes are not the same, and nothing reconciled them:

- `Job` rows survive anything.
- A Redis restart discards the queue. `redis:7` ran with no volume and no persistence,
  so every restart silently emptied it.

The result was a permanently stranded job: `status=queued`, `attempts=0`, no queue entry,
no error, no retry. On the production deployment two ingest jobs sat that way for three
days while the worker reported healthy and idle — sources stuck at "queued" in the UI,
the guide empty, and chat truthfully saying it had no sources.

T-1.4 fixed enqueuing *before* the row was committed. This fixes the opposite end: the
row committed, the queue entry gone.

Runs on worker startup, which is exactly when a Redis restart is most likely to have just
happened. Idempotent: Arq's `_job_id` is the job's idempotency key, so re-enqueuing a job
that *is* still queued is a no-op rather than a duplicate.
"""

from __future__ import annotations

from sqlalchemy import select

from ..core.db import SessionLocal
from ..core.logging import get_logger
from ..models import Job, JobStatus, JobType

logger = get_logger("orchestrator.worker")

# Same mapping as JobService; duplicated deliberately rather than importing the service,
# which would pull the whole repository/tenancy stack into worker startup.
_TASK_BY_TYPE: dict[JobType, str] = {
    JobType.ingest: "run_ingest",
    JobType.generate: "run_generate",
}

# A job that has never been attempted and is still `queued` has no Redis entry to lose —
# either it was just created (and the enqueue is moments away) or the queue dropped it.
# Re-enqueuing is safe in both cases because the idempotency key deduplicates.
_STRANDED_STATUS = JobStatus.queued


async def reenqueue_stranded_jobs(enqueuer) -> int:
    """Re-enqueue every never-attempted queued job. Returns how many were pushed.

    Deliberately not filtered by age. A stranded job is stranded whether it is one minute
    or three days old, and a time window would only add a way to miss one.
    """
    if enqueuer is None:
        logger.warning("reconcile_skipped_no_enqueuer")
        return 0

    with SessionLocal() as db:
        stranded = list(
            db.execute(
                select(Job)
                .where(Job.status == _STRANDED_STATUS)
                .where(Job.attempts == 0)
                .order_by(Job.created_at)
            ).scalars()
        )

    if not stranded:
        logger.info("reconcile_nothing_stranded")
        return 0

    pushed = 0
    for job in stranded:
        task_name = _TASK_BY_TYPE.get(job.type)
        if task_name is None:
            # An unknown type cannot be dispatched; say so rather than skipping quietly.
            logger.error(
                "reconcile_unknown_job_type",
                extra={"job_id": str(job.id), "type": str(job.type)},
            )
            continue
        try:
            await enqueuer.enqueue_job(
                task_name,
                str(job.id),
                str(job.tenant_id),
                _job_id=job.idempotency_key,
            )
            pushed += 1
        except Exception as exc:
            # One bad job must not stop the rest from recovering.
            logger.error(
                "reconcile_enqueue_failed",
                extra={"job_id": str(job.id), "error": f"{type(exc).__name__}: {exc}"},
            )

    logger.warning(
        "reconcile_reenqueued_stranded_jobs",
        extra={"found": len(stranded), "enqueued": pushed},
    )
    return pushed
