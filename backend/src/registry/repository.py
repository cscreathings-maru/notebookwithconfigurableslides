"""Versioned, tenant-scoped repositories for the registry.

Rows are immutable versions keyed by a stable `logical_id` + incrementing `version`.
Every query is filtered by tenant (inherited from TenantScopedRepository), so the
registry is strictly tenant-scoped. `usage` checks the Generation table to enforce
"a version referenced by any Generation is immutable".
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import func, select

from ..models import Generation, StakeholderProfile, Template
from ..models.base import Base
from ..tenancy.repository import TenantScopedRepository

VersionedT = TypeVar("VersionedT", StakeholderProfile, Template)


class _VersionedRepository(TenantScopedRepository[VersionedT], Generic[VersionedT]):
    def latest(self, logical_id: uuid.UUID) -> VersionedT | None:
        """The highest version for a logical id within this tenant."""
        return self.db.execute(
            self._scoped()
            .where(self.model.logical_id == logical_id)
            .order_by(self.model.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_version(self, logical_id: uuid.UUID, version: int) -> VersionedT | None:
        return self.db.execute(
            self._scoped()
            .where(self.model.logical_id == logical_id)
            .where(self.model.version == version)
        ).scalar_one_or_none()

    def next_version(self, logical_id: uuid.UUID) -> int:
        current = self.db.execute(
            select(func.max(self.model.version))
            .where(self.model.tenant_id == self.tenant_id)
            .where(self.model.logical_id == logical_id)
        ).scalar_one_or_none()
        return (current or 0) + 1

    def list_all(self) -> list[VersionedT]:
        rows = (
            self.db.execute(
                self._scoped().order_by(self.model.logical_id, self.model.version.desc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def latest_approved(self, logical_id: uuid.UUID) -> VersionedT | None:
        from ..models import RegistryStatus

        return self.db.execute(
            self._scoped()
            .where(self.model.logical_id == logical_id)
            .where(self.model.status == RegistryStatus.approved)
            .order_by(self.model.version.desc())
            .limit(1)
        ).scalar_one_or_none()


class ProfileRepository(_VersionedRepository[StakeholderProfile]):
    model = StakeholderProfile


class TemplateRepository(_VersionedRepository[Template]):
    model = Template


class RegistryUsage:
    """Reads the Generation table to decide whether a version is frozen."""

    def __init__(self, db, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def _exists(self, *conditions) -> bool:
        stmt = select(Generation.id).where(Generation.tenant_id == self.tenant_id, *conditions)
        return self.db.execute(stmt.limit(1)).first() is not None

    def profile_version_in_use(self, logical_id: uuid.UUID, version: int) -> bool:
        return self._exists(
            Generation.profile_id == logical_id, Generation.profile_version == version
        )

    def template_version_in_use(self, logical_id: uuid.UUID, version: int) -> bool:
        return self._exists(
            Generation.template_id == logical_id, Generation.template_version == version
        )


# Re-export Base for type checkers that resolve the TypeVar bound indirectly.
__all__ = [
    "ProfileRepository",
    "TemplateRepository",
    "RegistryUsage",
    "Base",
]
