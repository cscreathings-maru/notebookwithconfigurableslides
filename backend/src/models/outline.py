"""Outline — the validated structure contract produced before generation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPkMixin, utcnow


class Outline(UuidPkMixin, Base):
    __tablename__ = "outline"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=False, index=True
    )
    # Pinned profile (logical id + version) used to build this outline.
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
