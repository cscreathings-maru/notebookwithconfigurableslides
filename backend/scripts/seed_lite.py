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
from src.registry.house_template import seed_house_template
from src.storage.object_store import get_object_store


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

        # RM-15: a template is mandatory to generate anything, so a fresh
        # install without one is a dead end. Seeded after the tenant exists
        # (it needs the tenant_id) and inside the same transaction.
        #
        # Never fatal: this runs as the `init` container that gates the whole
        # stack's startup. Failing the boot over an optional convenience
        # template -- most likely because MinIO is not up yet -- would be a
        # worse outcome than the empty picker it exists to prevent.
        try:
            template = seed_house_template(
                db=db, tenant_id=tenant_id, object_store=get_object_store(), created_by=user_id
            )
            if template is not None:
                print(
                    f"Seeded house template '{template.name}' "
                    f"(catalog_status={template.catalog_status.value}; "
                    "an admin must review its catalog before it can be planned against)."
                )
            else:
                print("House template already present or unavailable; skipping.")
        except Exception as exc:  # noqa: BLE001 -- see the comment above
            print(f"WARNING: could not seed the house template ({type(exc).__name__}: {exc}).")
            print("         Upload a .pptx on the Templates page before generating.")

        db.commit()

    print("Lite seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(seed_lite())
