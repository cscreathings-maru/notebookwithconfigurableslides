"""Auth router — GET /api/v1/auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_principal
from ..auth.principal import Principal
from ..core.db import get_db
from ..core.errors import NotFoundError
from ..models import Tenant
from ..schemas.auth import MeResponse, TenantInfo, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
def me(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> MeResponse:
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    return MeResponse(
        user=UserInfo(
            id=principal.user_id,
            email=principal.email,
            role=principal.role,
            status="active",  # principal only exists for active users
        ),
        tenant=TenantInfo(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            status=tenant.status,
            region=tenant.region,
        ),
        role=principal.role,
    )
