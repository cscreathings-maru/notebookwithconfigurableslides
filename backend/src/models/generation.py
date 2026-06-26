"""Generation — the presentation build, with full provenance.

Introduced in Slice 2 for the registry immutability invariant; expanded in Slice 3
with the outline link, sources used, params sent to Presenton, artifact URIs, the
engine presentation id, and the consistency report.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPkMixin, utcnow


class GenerationStatus(str, enum.Enum):
    queued = "queued"
    analyzing = "analyzing"
    building_outline = "building_outline"
    generating = "generating"
    validating = "validating"
    ready = "ready"
    failed = "failed"


class Generation(UuidPkMixin, Base):
    __tablename__ = "generation"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=True
    )
    outline_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # Provenance: the exact registry versions this generation pinned.
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)

    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Sources used + the exact params sent to Presenton (server-side provenance;
    # params carries the engine template ref and is never exposed to clients).
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Engine-internal id + MinIO artifact keys (never exposed to clients).
    presenton_presentation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pptx_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    consistency_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, name="generation_status"),
        default=GenerationStatus.queued,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
