"""Tenant-scoped repositories for Project and Source."""

from __future__ import annotations

import uuid

from ..models import Project, Source
from ..tenancy.repository import TenantScopedRepository


class ProjectRepository(TenantScopedRepository[Project]):
    model = Project


class SourceRepository(TenantScopedRepository[Source]):
    model = Source

    def list_by_project(self, project_id: uuid.UUID) -> list[Source]:
        rows = (
            self.db.execute(self._scoped().where(Source.project_id == project_id))
            .scalars()
            .all()
        )
        return list(rows)
