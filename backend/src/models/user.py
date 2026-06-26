"""User — scoped to a tenant, mapped from the OIDC subject."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UuidPkMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    author = "author"
    viewer = "viewer"


class UserStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class User(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "user_account"  # "user" is reserved in PostgreSQL
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        UniqueConstraint("oidc_subject", name="uq_user_oidc_subject"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    oidc_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.viewer, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.active, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} role={self.role.value}>"
