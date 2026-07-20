"""Lite-mode default identity.

In lite mode the platform runs single-tenant with no auth: a fixed default tenant
and admin user stand in for the SaaS OIDC/tenant resolution. The ids are DERIVED
deterministically (uuid5) from the configured slug/email so that the seed step
(Phase 5) and the request-time principal (Phase 2) always agree without hardcoding
magic UUIDs. Multi-tenant SaaS code is untouched and re-activates when LITE_MODE is
off.
"""

from __future__ import annotations

import uuid

from ..auth.principal import Principal
from ..models import UserRole

# Fixed namespace for all lite-mode derived ids. Never change it: doing so would
# orphan any data seeded under the previous default tenant.
LITE_NAMESPACE = uuid.UUID("6f8d2c1e-0a3b-5e47-9c21-7b4a1f0e9d33")


def default_tenant_id(slug: str) -> uuid.UUID:
    """Deterministic tenant id for the lite default tenant."""
    return uuid.uuid5(LITE_NAMESPACE, f"tenant:{slug}")


def default_user_id(email: str) -> uuid.UUID:
    """Deterministic user id for the lite default admin user."""
    return uuid.uuid5(LITE_NAMESPACE, f"user:{email}")


def build_default_principal(*, tenant_slug: str, user_email: str) -> Principal:
    """The single principal every lite-mode request runs as (admin, no token)."""
    return Principal(
        user_id=default_user_id(user_email),
        tenant_id=default_tenant_id(tenant_slug),
        role=UserRole.admin,
        email=user_email,
    )
