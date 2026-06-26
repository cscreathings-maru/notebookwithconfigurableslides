"""Seed a tenant and its first admin user.

Usage (per quickstart.md):
    python -m scripts.seed_tenant --name "Acme" --admin you@acme.id

The admin's oidc_subject defaults to the email; once SSO is wired, set it to the
real IdP subject with --subject so login maps correctly.
"""

from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import select

from src.core.db import SessionLocal
from src.models import Tenant, TenantStatus, User, UserRole, UserStatus


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "tenant"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a tenant + admin user.")
    parser.add_argument("--name", required=True, help="Tenant display name")
    parser.add_argument("--admin", required=True, help="Admin email")
    parser.add_argument("--slug", help="Override the generated slug")
    parser.add_argument("--subject", help="OIDC subject (defaults to the admin email)")
    args = parser.parse_args(argv)

    slug = args.slug or _slugify(args.name)
    subject = args.subject or args.admin

    with SessionLocal() as db:
        existing = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
        if existing is not None:
            print(f"Tenant with slug '{slug}' already exists ({existing.id}).", file=sys.stderr)
            return 1

        tenant = Tenant(name=args.name, slug=slug, status=TenantStatus.active)
        db.add(tenant)
        db.flush()

        admin = User(
            tenant_id=tenant.id,
            email=args.admin,
            oidc_subject=subject,
            role=UserRole.admin,
            status=UserStatus.active,
        )
        db.add(admin)
        db.commit()

        print(f"Seeded tenant '{tenant.name}' ({tenant.id}) with admin {admin.email} ({admin.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
