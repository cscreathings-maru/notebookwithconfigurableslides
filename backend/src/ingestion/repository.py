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

    def engine_source_refs(self, project_id: uuid.UUID) -> set[str]:
        """Engine source ids for this project — the allow-set for RAG grounding.

        Open Notebook's search index is global, so this set is what keeps one project's
        retrieval out of another's documents. It is built from `_scoped()`, which cannot
        be issued without a tenant filter, so a cross-tenant id cannot enter it.

        Sources still indexing have no `on_source_id` yet and are simply absent; grounding
        widens as they become ready.
        """
        rows = self.db.execute(
            self._scoped()
            .where(Source.project_id == project_id)
            .where(Source.on_source_id.is_not(None))
        ).scalars()
        return {row.on_source_id for row in rows if row.on_source_id}
