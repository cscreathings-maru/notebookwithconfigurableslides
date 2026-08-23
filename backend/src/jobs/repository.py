"""Tenant-scoped Job repository."""

from __future__ import annotations

import uuid
from datetime import timedelta

from ..models import Job, JobStatus, JobType
from ..models.base import utcnow
from ..tenancy.repository import TenantScopedRepository

# Beyond this, a `running` job is presumed dead rather than slow, and a caller
# asking for the same work again gets a fresh attempt instead of being told to
# wait on a corpse. Mirrors `workers/reconcile._RUNNING_STALE_AFTER`, which
# re-enqueues such jobs on worker start -- the two must agree, or a job could
# be judged dead here while the reconciler still considers it alive.
_LIVE_JOB_MAX_AGE = timedelta(minutes=30)


class JobRepository(TenantScopedRepository[Job]):
    model = Job

    def find_by_idempotency_key(self, key: str) -> Job | None:
        """Return an existing job for this tenant + idempotency key, if any."""
        return self.db.execute(
            self._scoped().where(Job.idempotency_key == key)
        ).scalar_one_or_none()

    def find_live(self, *, job_type: JobType, ref_id: uuid.UUID) -> Job | None:
        """A job of this type for this ref that is genuinely still in flight.

        Lets a caller distinguish "already being worked on" from "was worked
        on once and died", which an idempotency key alone cannot: a key that
        never changes blocks every retry forever, and a key that always
        changes stacks a duplicate run per click. Both were shipped and both
        caused real damage (2026-08-17 permanently unretryable; 2026-08-23
        four full catalogue runs for two templates).
        """
        cutoff = utcnow() - _LIVE_JOB_MAX_AGE
        return self.db.execute(
            self._scoped()
            .where(Job.type == job_type)
            .where(Job.ref_id == ref_id)
            .where(Job.status.in_((JobStatus.queued, JobStatus.running)))
            # Age gates BOTH statuses, not just `running`. A `queued` job can
            # be just as stranded -- a lost Redis entry leaves one sitting
            # forever, which is the whole reason `workers/reconcile.py`
            # exists. Exempting `queued` here would let one stranded row
            # block every future retry, reintroducing the permanently
            # unretryable template this method was written to prevent.
            .where(Job.updated_at > cutoff)
            .order_by(Job.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
