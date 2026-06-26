"""Per-tenant monthly generation quota enforcement.

`tenant.quota_monthly_generations` (0 = unlimited) caps generations per calendar
month. On exceed, policy is either "block" (reject) or "flag" (allow but mark); in
both cases a `quota.exceeded` audit event is written and the alert hook fires.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..core.errors import AppError
from ..models import Generation, GenerationStatus, Tenant
from .alerts import AlertSink
from .service import MeteringService


class QuotaExceededError(AppError):
    status_code = 429
    code = "quota_exceeded"


@dataclass(frozen=True)
class QuotaStatus:
    monthly_limit: int  # 0 = unlimited
    used_this_month: int

    @property
    def unlimited(self) -> bool:
        return self.monthly_limit <= 0

    @property
    def remaining(self) -> int | None:
        if self.unlimited:
            return None
        return max(self.monthly_limit - self.used_this_month, 0)


def _month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class QuotaService:
    def __init__(self, db: Session, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def used_this_month(self) -> int:
        # A generation that ultimately failed does not consume quota.
        count = self.db.execute(
            select(func.count(Generation.id))
            .where(Generation.tenant_id == self.tenant_id)
            .where(Generation.created_at >= _month_start())
            .where(Generation.status != GenerationStatus.failed)
        ).scalar_one()
        return int(count or 0)

    def status(self) -> QuotaStatus:
        tenant = self.db.get(Tenant, self.tenant_id)
        limit = tenant.quota_monthly_generations if tenant else 0
        return QuotaStatus(monthly_limit=limit, used_this_month=self.used_this_month())

    def enforce(self, *, actor_user_id: uuid.UUID | None, alert_sink: AlertSink) -> bool:
        """Return True if allowed. Records + alerts (and may raise) when exceeded."""
        status = self.status()
        if status.unlimited or status.used_this_month < status.monthly_limit:
            return True

        # Record the breach in its OWN committed transaction so it survives even when
        # the request is rejected (the request session rolls back on the raised error).
        with SessionLocal() as audit_db:
            MeteringService(audit_db, self.tenant_id).audit(
                action="quota.exceeded",
                resource={
                    "monthly_limit": status.monthly_limit,
                    "used_this_month": status.used_this_month,
                },
                actor_user_id=actor_user_id,
            )
            audit_db.commit()

        alert_sink.emit(
            {
                "type": "quota_exceeded",
                "tenant_id": str(self.tenant_id),
                "monthly_limit": status.monthly_limit,
                "used_this_month": status.used_this_month,
            }
        )

        if get_settings().quota_policy == "flag":
            return False  # allow but flagged
        raise QuotaExceededError(
            f"Monthly generation quota ({status.monthly_limit}) reached."
        )
