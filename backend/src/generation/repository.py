"""Tenant-scoped Generation repository."""

from __future__ import annotations

import uuid

from ..models import Generation
from ..tenancy.repository import TenantScopedRepository


class GenerationRepository(TenantScopedRepository[Generation]):
    model = Generation

    def list_by_project(self, project_id: uuid.UUID) -> list[Generation]:
        rows = (
            self.db.execute(
                self._scoped()
                .where(Generation.project_id == project_id)
                .order_by(Generation.created_at.desc())
            )
            .scalars()
            .all()
        )
        return list(rows)
