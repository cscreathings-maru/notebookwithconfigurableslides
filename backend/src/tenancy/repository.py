"""Tenant-scoped repository base — the enforcement point for tenant isolation.

Every read/write goes through a query that is unconditionally filtered by the
principal's tenant_id. A row belonging to another tenant is simply not found, so
cross-tenant access surfaces as 404 (NotFoundError) — never a 403 that would leak
the resource's existence. There is no API to bypass the tenant filter.
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantScopedRepository(Generic[ModelT]):
    """Base repository bound to a single tenant for the lifetime of a request."""

    model: type[ModelT]

    def __init__(self, db: Session, tenant_id: uuid.UUID):
        if not hasattr(self.model, "tenant_id"):
            raise TypeError(
                f"{self.model.__name__} has no tenant_id; it cannot be tenant-scoped."
            )
        self.db = db
        self.tenant_id = tenant_id

    def _scoped(self):
        """A SELECT pre-filtered to this tenant — the only way rows are fetched."""
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    def get(self, entity_id: uuid.UUID) -> ModelT:
        """Fetch by id within the tenant, or raise NotFoundError (-> 404)."""
        obj = self.db.execute(
            self._scoped().where(self.model.id == entity_id)
        ).scalar_one_or_none()
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} not found.")
        return obj

    def get_or_none(self, entity_id: uuid.UUID) -> ModelT | None:
        return self.db.execute(
            self._scoped().where(self.model.id == entity_id)
        ).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        rows = self.db.execute(self._scoped().limit(limit).offset(offset)).scalars().all()
        return list(rows)

    def add(self, obj: ModelT) -> ModelT:
        """Persist a new row, forcing its tenant_id to this tenant."""
        setattr(obj, "tenant_id", self.tenant_id)
        self.db.add(obj)
        self.db.flush()
        return obj
