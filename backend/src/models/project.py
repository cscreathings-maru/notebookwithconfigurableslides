"""Project — a workspace that maps 1:1 to an Open Notebook notebook."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UpdatedAtMixin, UuidPkMixin


class Project(UuidPkMixin, TimestampMixin, UpdatedAtMixin, Base):
    __tablename__ = "project"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Engine-internal reference — never exposed to clients.
    on_notebook_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_account.id"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.name}>"
