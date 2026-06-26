"""Source — an uploaded document/URL and its analysis state, scoped to a project."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UuidPkMixin


class SourceKind(str, enum.Enum):
    pdf = "pdf"
    office = "office"
    csv = "csv"
    text = "text"
    url = "url"


class SourceStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Source(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "source"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=False, index=True
    )
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind, name="source_kind"), nullable=False)
    # MinIO key (tenant-prefixed) for files, or the URL for url sources.
    original_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Engine-internal reference — never exposed to clients.
    on_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status"),
        default=SourceStatus.queued,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Pointer to the derived summary/insights (engine-internal ref).
    analysis_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source {self.kind.value} {self.status.value}>"
