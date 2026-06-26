"""Usage + audit reporting — tenant-scoped aggregation over UsageRecord.

All queries are filtered by the caller's tenant; there is no cross-tenant rollup.
Rollups sum tokens/cost and count generations (action == 'generation.created') per
user and for the tenant over a date range.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, UsageRecord

GENERATION_ACTION = "generation.created"


@dataclass
class Rollup:
    generations: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_estimate: Decimal = field(default_factory=lambda: Decimal("0"))

    def add(self, record: UsageRecord) -> None:
        self.tokens_in += record.tokens_in
        self.tokens_out += record.tokens_out
        self.cost_estimate += record.cost_estimate or Decimal("0")
        if record.action == GENERATION_ACTION:
            self.generations += 1


@dataclass
class UsageReport:
    tenant: Rollup
    per_user: dict[uuid.UUID | None, Rollup]


class UsageReportService:
    def __init__(self, db: Session, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def _records(self, start: datetime, end: datetime) -> list[UsageRecord]:
        return list(
            self.db.execute(
                select(UsageRecord)
                .where(UsageRecord.tenant_id == self.tenant_id)
                .where(UsageRecord.created_at >= start)
                .where(UsageRecord.created_at <= end)
            )
            .scalars()
            .all()
        )

    def report(self, start: datetime, end: datetime) -> UsageReport:
        tenant = Rollup()
        per_user: dict[uuid.UUID | None, Rollup] = {}
        for record in self._records(start, end):
            tenant.add(record)
            per_user.setdefault(record.actor_user_id, Rollup()).add(record)
        return UsageReport(tenant=tenant, per_user=per_user)

    def audit_events(self, start: datetime, end: datetime, *, limit: int = 500) -> list[UsageRecord]:
        return list(
            self.db.execute(
                select(UsageRecord)
                .where(UsageRecord.tenant_id == self.tenant_id)
                .where(UsageRecord.created_at >= start)
                .where(UsageRecord.created_at <= end)
                .order_by(UsageRecord.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def emails_for(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not user_ids:
            return {}
        rows = self.db.execute(
            select(User.id, User.email)
            .where(User.tenant_id == self.tenant_id)
            .where(User.id.in_(user_ids))
        ).all()
        return {row[0]: row[1] for row in rows}
