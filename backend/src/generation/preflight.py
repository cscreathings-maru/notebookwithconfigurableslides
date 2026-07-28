"""Shared quota + metering pre-flight for every generation path.

Both pipelines must pass the same gate and emit the same usage record. They did not:
the governed path called `QuotaService.enforce` and `MeteringService.record`, the
freeform (Studio) path called neither. Since Studio is the primary user path and the
rollups count `action == "generation.created"`, the `/usage` dashboard was structurally
unable to observe the product it reports on -- it showed zero generations.

Split into two functions rather than one call, because the halves belong at different
points in the transaction:

- `authorize_generation` runs **before any row is written**, so a blocked attempt
  consumes no quota and leaves nothing behind.
- `meter_generation` runs **after** the generation exists, because the usage record
  references its id.

Divergence between the two pipelines is this codebase's recurring failure mode, so
neither service should reimplement either half.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..metering.aggregation import GENERATION_ACTION
from ..metering.alerts import AlertSink
from ..metering.quota import QuotaService
from ..metering.service import MeteringService


def authorize_generation(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    alert_sink: AlertSink,
) -> None:
    """Quota gate. Call before writing any row.

    Raises when the monthly cap is reached (non-lite); records and alerts on breach.
    """
    QuotaService(db, tenant_id).enforce(
        actor_user_id=actor_user_id, alert_sink=alert_sink
    )


def meter_generation(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    resource: dict[str, Any],
) -> None:
    """Usage record for a created generation. Call once the row exists.

    Records **even in lite mode**. `QuotaService.enforce` deliberately short-circuits
    there, but metering must not: the dashboard is the only view of what was generated,
    and skipping the record would leave it blind in exactly the deployment most users run.
    """
    MeteringService(db, tenant_id).record(
        action=GENERATION_ACTION,
        resource=resource,
        actor_user_id=actor_user_id,
    )
