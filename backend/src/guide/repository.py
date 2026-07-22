"""Tenant-scoped repository for NotebookGuide (one per project)."""

from __future__ import annotations

import uuid

from ..models import NotebookGuide
from ..tenancy.repository import TenantScopedRepository


class GuideRepository(TenantScopedRepository[NotebookGuide]):
    model = NotebookGuide

    def get_by_project(self, project_id: uuid.UUID) -> NotebookGuide | None:
        return self.db.execute(
            self._scoped().where(NotebookGuide.project_id == project_id)
        ).scalar_one_or_none()
