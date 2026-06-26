"""Tenant administration — BYOK LLM provider config (admin only).

This is the slice's representative mutating, role-gated, tenant-scoped surface:
- tenant resolved server-side from the token,
- admin role required (viewer/author get 403),
- secret stored encrypted at rest and never returned to the client.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth.principal import Principal
from ..core.db import get_db
from ..metering.service import MeteringService
from ..schemas.tenant import LlmConfigPublic, LlmConfigUpdate
from ..tenancy.llm_config import TenantLlmConfigService
from ..tenancy.rbac import require_admin

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.put("/llm-config", response_model=LlmConfigPublic, status_code=status.HTTP_200_OK)
def set_llm_config(
    payload: LlmConfigUpdate,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LlmConfigPublic:
    service = TenantLlmConfigService(db, principal.tenant_id)
    service.set_config(
        provider=payload.provider,
        config={
            "base_url": payload.base_url,
            "model": payload.model,
            "api_key": payload.api_key,
        },
    )
    # Audit the admin action — the api_key is deliberately NOT recorded.
    MeteringService(db, principal.tenant_id).audit(
        action="tenant.llm_config.updated",
        resource={"provider": payload.provider, "model": payload.model},
        actor_user_id=principal.user_id,
    )
    return LlmConfigPublic(
        provider=payload.provider, base_url=payload.base_url, model=payload.model
    )


@router.get("/llm-config", response_model=LlmConfigPublic)
def get_llm_config(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LlmConfigPublic:
    service = TenantLlmConfigService(db, principal.tenant_id)
    public = service.get_public_config()
    return LlmConfigPublic(**public)
