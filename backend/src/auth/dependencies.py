"""Authentication dependencies.

`get_current_principal` is the single server-side authority for identity AND tenant:
it validates the token, maps `oidc_subject` -> User, and builds the Principal whose
tenant_id every downstream query is forced to filter on. Clients cannot influence
tenant selection — it is read from the persisted User, not the request.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.errors import UnauthorizedError
from ..models import Tenant, TenantStatus, User, UserStatus
from .oidc import validate_token
from .principal import Principal


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return token


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> Principal:
    token = _extract_bearer(request)
    claims = validate_token(token)
    subject = claims["sub"]

    user = db.execute(
        select(User).where(User.oidc_subject == subject)
    ).scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("No user is provisioned for this identity.")
    if user.status is not UserStatus.active:
        raise UnauthorizedError("User account is disabled.")

    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status is not TenantStatus.active:
        raise UnauthorizedError("Tenant is not active.")

    return Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
