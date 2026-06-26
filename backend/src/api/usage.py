"""Usage + audit router (admin only, strictly tenant-scoped)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth.principal import Principal
from ..core.db import get_db
from ..metering.aggregation import UsageReportService
from ..metering.quota import QuotaService
from ..schemas.usage import (
    AuditEventOut,
    QuotaOut,
    RollupOut,
    UsageResponse,
    UserUsageOut,
)
from ..tenancy.rbac import require_admin

router = APIRouter(tags=["usage"])

_DEFAULT_WINDOW_DAYS = 90


def _range(from_: datetime | None, to: datetime | None) -> tuple[datetime, datetime]:
    end = to or datetime.now(timezone.utc)
    start = from_ or (end - timedelta(days=_DEFAULT_WINDOW_DAYS))
    return start, end


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UsageResponse:
    start, end = _range(from_, to)
    service = UsageReportService(db, principal.tenant_id)
    report = service.report(start, end)

    user_ids = [uid for uid in report.per_user if uid is not None]
    emails = service.emails_for(user_ids)

    per_user = [
        UserUsageOut(
            user_id=uid,
            email=emails.get(uid) if uid else None,
            generations=roll.generations,
            tokens_in=roll.tokens_in,
            tokens_out=roll.tokens_out,
            cost_estimate=roll.cost_estimate,
        )
        for uid, roll in report.per_user.items()
    ]

    quota = QuotaService(db, principal.tenant_id).status()

    return UsageResponse(
        from_=start,
        to=end,
        tenant=RollupOut(
            generations=report.tenant.generations,
            tokens_in=report.tenant.tokens_in,
            tokens_out=report.tenant.tokens_out,
            cost_estimate=report.tenant.cost_estimate,
        ),
        quota=QuotaOut(
            monthly_limit=quota.monthly_limit,
            used_this_month=quota.used_this_month,
            remaining=quota.remaining,
        ),
        per_user=per_user,
    )


@router.get("/audit", response_model=list[AuditEventOut])
def get_audit(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    start, end = _range(from_, to)
    events = UsageReportService(db, principal.tenant_id).audit_events(start, end)
    return [
        AuditEventOut(
            id=e.id,
            actor_user_id=e.actor_user_id,
            action=e.action,
            resource=e.resource,
            created_at=e.created_at,
        )
        for e in events
    ]
