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

**2026-08-17**: a second, distinct way to strand a job showed up in production — a
`catalog_template` job sat at `status=running` indefinitely after its worker re-raised
instead of recording a terminal state. `running` was outside this module's search, so
nothing recovered it and nothing surfaced it; the template showed a permanent
"cataloguing…" spinner. Stale `running` rows are now reconciled too (`_RUNNING_STALE_AFTER`).

Runs on worker startup, which is exactly when a Redis restart — or the crash that killed
the previous worker mid-job — is most likely to have just happened. Idempotent: Arq's
`_job_id` is the job's idempotency key, so re-enqueuing a job that *is* still queued is a
no-op rather than a duplicate.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select

from ..core.db import SessionLocal
from ..core.logging import get_logger
from ..models import Job, JobStatus, JobType
from ..models.base import utcnow

logger = get_logger("orchestrator.worker")

# Same mapping as JobService; duplicated deliberately rather than importing the service,
# which would pull the whole repository/tenancy stack into worker startup.
_TASK_BY_TYPE: dict[JobType, str] = {
    JobType.ingest: "run_ingest",
    JobType.generate: "run_generate",
    JobType.catalog_template: "run_catalog_template",
}

# A job that has never been attempted and is still `queued` has no Redis entry to lose —
# either it was just created (and the enqueue is moments away) or the queue dropped it.
# Re-enqueuing is safe in both cases because the idempotency key deduplicates.
_STRANDED_STATUS = JobStatus.queued

# How long a job may sit at `running` before it is presumed dead (2026-08-17).
#
# `running` means "a worker claimed this and started it". If that worker then dies
# mid-flight — OOM, SIGKILL, `docker compose up` during a deploy, or (as happened
# here) a task that re-raised instead of recording a terminal state — the row stays
# `running` forever. Nothing retried it, nothing surfaced it, and the template it
# belonged to showed an infinite spinner with no way out but a shell on the box.
#
# Unlike the `queued` case above, age IS the right signal here: a live job is
# indistinguishable from a dead one except by how long it has sat. The threshold is
# far beyond any real task (template cataloguing, the slowest, runs ~95s against a
# 30-slide deck), so a job past it is dead by any reasonable reading — while still
# leaving room for a genuinely long ingest, and for a second worker replica running
# something legitimately, should this ever scale past one.
_RUNNING_STALE_AFTER = timedelta(minutes=30)


async def reenqueue_stranded_jobs(enqueuer) -> int:
    """Re-enqueue every stranded job. Returns how many were pushed.

    Two shapes of stranded, for two different reasons (see the constants above):
    a never-attempted `queued` job whose Redis entry was lost, and a `running` job
    whose worker died holding it.
    """
    if enqueuer is None:
        logger.warning("reconcile_skipped_no_enqueuer")
        return 0

    stale_before = utcnow() - _RUNNING_STALE_AFTER
    with SessionLocal() as db:
        stranded = list(
            db.execute(
                select(Job)
                .where(
                    or_(
                        and_(Job.status == _STRANDED_STATUS, Job.attempts == 0),
                        and_(Job.status == JobStatus.running, Job.updated_at < stale_before),
                    )
                )
                .order_by(Job.created_at)
            ).scalars()
        )

    if not stranded:
        logger.info("reconcile_nothing_stranded")
        return 0

    pushed = 0
    undispatchable: list[uuid.UUID] = []
    for job in stranded:
        task_name = _TASK_BY_TYPE.get(job.type)
        if task_name is None:
            # No task handles this type -- the row can NEVER run. Seen in
            # production 2026-08-17: a `register_template` job left over from
            # before that pipeline was deleted, re-found and re-logged at
            # ERROR on every single worker start. Recording it as terminally
            # failed retires it honestly instead of generating permanent
            # noise that would eventually mask a real error.
            logger.error(
                "reconcile_unknown_job_type",
                extra={"job_id": str(job.id), "type": str(job.type)},
            )
            undispatchable.append(job.id)
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

    if undispatchable:
        with SessionLocal() as db:
            for job_id in undispatchable:
                job = db.get(Job, job_id)
                if job is not None:
                    job.status = JobStatus.failed
                    job.error = f"No worker task handles job type '{job.type.value}'; it can never run."
                    db.add(job)
            db.commit()

    logger.warning(
        "reconcile_reenqueued_stranded_jobs",
        extra={"found": len(stranded), "enqueued": pushed, "retired": len(undispatchable)},
    )
    return pushed
