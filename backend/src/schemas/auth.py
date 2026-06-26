"""Auth response schemas. Only orchestrator UUIDs and safe fields are exposed."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from ..models import TenantStatus, UserRole, UserStatus


class TenantInfo(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: TenantStatus
    region: str | None = None


class UserInfo(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    status: UserStatus


class MeResponse(BaseModel):
    """GET /api/v1/auth/me — current user, tenant, and role."""

    user: UserInfo
    tenant: TenantInfo
    role: UserRole
