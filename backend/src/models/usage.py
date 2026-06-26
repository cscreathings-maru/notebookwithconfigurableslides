"""UsageRecord — per-tenant metering + audit trail of who did what."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Integer, JSON, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPkMixin, utcnow


class UsageRecord(UuidPkMixin, Base):
    __tablename__ = "usage_record"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_estimate: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
