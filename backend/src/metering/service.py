"""Metering + audit — write a UsageRecord per LLM-backed or admin action.

The same table is the audit trail (who did what, when, to which resource) and the
metering ledger (tokens + estimated cost). Cost is derived from the tenant's
provider/model pricing (BYOK config may carry input/output rates); otherwise the
configured defaults apply. Secrets are never placed in the resource payload.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..models import UsageRecord
from ..tenancy.llm_config import TenantLlmConfigService

logger = get_logger("orchestrator.metering")


def _tenant_rates(db: Session, tenant_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    """(input_per_1k, output_per_1k) from the tenant's pricing config or defaults."""
    settings = get_settings()
    in_rate = Decimal(str(settings.default_input_cost_per_1k))
    out_rate = Decimal(str(settings.default_output_cost_per_1k))
    # Lite mode has no per-tenant pricing; use the configured defaults and skip the
    # provider-config lookup entirely so cost estimation never depends on BYOK.
    if settings.lite_mode:
        return in_rate, out_rate
    try:
        config = TenantLlmConfigService(db, tenant_id).get_config()
    except Exception:  # no provider configured yet -> defaults
        return in_rate, out_rate
    if "input_cost_per_1k" in config:
        in_rate = Decimal(str(config["input_cost_per_1k"]))
    if "output_cost_per_1k" in config:
        out_rate = Decimal(str(config["output_cost_per_1k"]))
    return in_rate, out_rate


def estimate_cost(
    db: Session, tenant_id: uuid.UUID, *, tokens_in: int, tokens_out: int
) -> Decimal:
    in_rate, out_rate = _tenant_rates(db, tenant_id)
    return (Decimal(tokens_in) / 1000) * in_rate + (Decimal(tokens_out) / 1000) * out_rate


class MeteringService:
    def __init__(self, db: Session, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def record(
        self,
        *,
        action: str,
        resource: dict[str, Any],
        actor_user_id: uuid.UUID | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> UsageRecord:
        cost = estimate_cost(
            self.db, self.tenant_id, tokens_in=tokens_in, tokens_out=tokens_out
        )
        record = UsageRecord(
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource=resource,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate=cost,
        )
        self.db.add(record)
        self.db.flush()
        return record

    # Audit is the same ledger with zero tokens; a thin alias documents intent.
    def audit(
        self,
        *,
        action: str,
        resource: dict[str, Any],
        actor_user_id: uuid.UUID | None = None,
    ) -> UsageRecord:
        return self.record(action=action, resource=resource, actor_user_id=actor_user_id)
