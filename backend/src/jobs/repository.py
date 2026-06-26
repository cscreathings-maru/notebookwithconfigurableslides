"""Tenant-scoped Job repository."""

from __future__ import annotations

from sqlalchemy import select

from ..models import Job
from ..tenancy.repository import TenantScopedRepository


class JobRepository(TenantScopedRepository[Job]):
    model = Job

    def find_by_idempotency_key(self, key: str) -> Job | None:
        """Return an existing job for this tenant + idempotency key, if any."""
        return self.db.execute(
            self._scoped().where(Job.idempotency_key == key)
        ).scalar_one_or_none()
