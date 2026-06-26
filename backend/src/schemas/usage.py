"""Usage + audit API schemas (admin)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class RollupOut(BaseModel):
    generations: int
    tokens_in: int
    tokens_out: int
    cost_estimate: Decimal


class UserUsageOut(RollupOut):
    user_id: uuid.UUID | None
    email: str | None


class QuotaOut(BaseModel):
    monthly_limit: int  # 0 = unlimited
    used_this_month: int
    remaining: int | None


class UsageResponse(BaseModel):
    from_: datetime
    to: datetime
    tenant: RollupOut
    quota: QuotaOut
    per_user: list[UserUsageOut]


class AuditEventOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    resource: dict[str, Any]
    created_at: datetime
