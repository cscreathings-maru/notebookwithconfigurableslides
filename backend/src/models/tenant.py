"""Tenant — the organization and root of isolation (the only table without tenant_id)."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UpdatedAtMixin, UuidPkMixin


class TenantStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class Tenant(UuidPkMixin, TimestampMixin, UpdatedAtMixin, Base):
    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"),
        default=TenantStatus.active,
        nullable=False,
    )

    # BYOK: provider name in clear, full config encrypted at rest.
    llm_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_config_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quota_monthly_generations: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False  # 0 = unlimited
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tenant {self.slug}>"
