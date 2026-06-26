"""Job — generic async work unit (ingest or generate), tenant-scoped."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UpdatedAtMixin, UuidPkMixin


class JobType(str, enum.Enum):
    ingest = "ingest"
    generate = "generate"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Job(UuidPkMixin, TimestampMixin, UpdatedAtMixin, Base):
    __tablename__ = "job"
    __table_args__ = (
        # Idempotency is scoped per tenant: a key dedupes only within its tenant.
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_job_tenant_idem"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    type: Mapped[JobType] = mapped_column(Enum(JobType, name="job_type"), nullable=False)
    # Points at the source_id (ingest) or generation_id (generate); nullable for skeleton.
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.queued, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Job {self.type.value} {self.status.value}>"
