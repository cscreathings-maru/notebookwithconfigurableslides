"""Seed the lite-mode default tenant + admin user.

Lite mode runs single-tenant with no auth: every request resolves to a fixed
default admin principal whose ids are DERIVED (uuid5) from the configured slug/email
in `src.core.lite`. This script inserts the matching Tenant + User rows so the
foreign keys downstream (projects, sources, outlines, generations, usage records)
resolve. It is idempotent — safe to run on every deploy/startup.

Usage:
    python -m scripts.seed_lite

Reads DEFAULT_TENANT_SLUG / DEFAULT_TENANT_NAME / DEFAULT_USER_EMAIL from the
environment (see deploy/.env). No arguments needed.
"""

from __future__ import annotations

from src.core.config import get_settings
from src.core.db import SessionLocal
from src.core.lite import default_tenant_id, default_user_id
from src.models import Tenant, TenantStatus, User, UserRole, UserStatus


def seed_lite() -> int:
    settings = get_settings()
    slug = settings.default_tenant_slug
    name = settings.default_tenant_name
    email = settings.default_user_email

    tenant_id = default_tenant_id(slug)
    user_id = default_user_id(email)

    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            tenant = Tenant(
                id=tenant_id,
                name=name,
                slug=slug,
                status=TenantStatus.active,
                quota_monthly_generations=0,  # 0 = unlimited
            )
            db.add(tenant)
            db.flush()
            print(f"Created default tenant '{name}' ({tenant_id}).")
        else:
            print(f"Default tenant already present ({tenant_id}); skipping.")

        user = db.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                tenant_id=tenant_id,
                email=email,
                oidc_subject=email,  # unused in lite mode, kept for the SaaS path
                role=UserRole.admin,
                status=UserStatus.active,
            )
            db.add(user)
            print(f"Created default admin user '{email}' ({user_id}).")
        else:
            print(f"Default admin user already present ({user_id}); skipping.")

        db.commit()

    print("Lite seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(seed_lite())
