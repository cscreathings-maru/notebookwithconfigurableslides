"""Seed a complete QA fixture: tenants, users (all roles), BYOK config, and quotas.

Idempotent — safe to re-run. It provisions exactly the accounts referenced by
`specs/001-presentation-notebook-llm/QA-TEST-CASES.md` so a QA team can sign in (dev
token) and exercise every flow: RBAC, cross-tenant isolation, quota enforcement, the
"no provider configured" failure path, and a disabled account.

Usage:
    # Set the BYOK provider once (used for tenants that need real generation):
    export QA_LLM_BASE_URL="https://api.deepseek.com/v1"
    export QA_LLM_MODEL="deepseek-chat"
    export QA_LLM_API_KEY="sk-..."      # omit to skip BYOK (generation will fail by design)

    docker compose exec orchestrator python -m scripts.seed_qa
    # or locally:
    python -m scripts.seed_qa

Each user's oidc_subject is its email, so a dev token's `sub` is simply the email.
Mint a token with:  python -m scripts.mint_dev_token --sub author@qa-acme.test
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from sqlalchemy import select

from src.core.db import SessionLocal
from src.models import Tenant, TenantStatus, User, UserRole, UserStatus
from src.tenancy.llm_config import TenantLlmConfigService


@dataclass(frozen=True)
class UserSpec:
    email: str
    role: UserRole
    status: UserStatus = UserStatus.active


@dataclass(frozen=True)
class TenantSpec:
    name: str
    slug: str
    quota_monthly_generations: int
    byok: bool
    users: tuple[UserSpec, ...]


# The QA fixture. Keep in sync with QA-TEST-CASES.md.
TENANTS: tuple[TenantSpec, ...] = (
    TenantSpec(
        name="QA Acme",
        slug="qa-acme",
        quota_monthly_generations=0,  # unlimited — primary happy-path tenant
        byok=True,
        users=(
            UserSpec("admin@qa-acme.test", UserRole.admin),
            UserSpec("author@qa-acme.test", UserRole.author),
            UserSpec("viewer@qa-acme.test", UserRole.viewer),
            UserSpec("disabled@qa-acme.test", UserRole.author, UserStatus.disabled),
        ),
    ),
    TenantSpec(
        name="QA Globex",
        slug="qa-globex",
        quota_monthly_generations=0,
        byok=True,
        users=(
            UserSpec("admin@qa-globex.test", UserRole.admin),
            UserSpec("author@qa-globex.test", UserRole.author),
        ),
    ),
    TenantSpec(
        name="QA Quota",
        slug="qa-quota",
        quota_monthly_generations=2,  # low cap — for quota-enforcement cases
        byok=True,
        users=(
            UserSpec("admin@qa-quota.test", UserRole.admin),
            UserSpec("author@qa-quota.test", UserRole.author),
        ),
    ),
    TenantSpec(
        name="QA NoKey",
        slug="qa-nokey",
        quota_monthly_generations=0,
        byok=False,  # intentionally NO provider — ingestion must fail cleanly
        users=(UserSpec("author@qa-nokey.test", UserRole.author),),
    ),
)


def _provider_config() -> dict[str, str] | None:
    api_key = os.environ.get("QA_LLM_API_KEY")
    if not api_key:
        return None
    return {
        "provider": os.environ.get("QA_LLM_PROVIDER", "deepseek"),
        "base_url": os.environ.get("QA_LLM_BASE_URL", "https://api.deepseek.com/v1"),
        "model": os.environ.get("QA_LLM_MODEL", "deepseek-chat"),
        "api_key": api_key,
    }


def _upsert_tenant(db, spec: TenantSpec) -> Tenant:
    tenant = db.execute(select(Tenant).where(Tenant.slug == spec.slug)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=spec.name, slug=spec.slug, status=TenantStatus.active)
        db.add(tenant)
    tenant.name = spec.name
    tenant.status = TenantStatus.active
    tenant.quota_monthly_generations = spec.quota_monthly_generations
    db.flush()
    return tenant


def _upsert_user(db, tenant: Tenant, spec: UserSpec) -> str:
    user = db.execute(
        select(User).where(User.oidc_subject == spec.email)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            tenant_id=tenant.id,
            email=spec.email,
            oidc_subject=spec.email,  # subject == email keeps dev tokens trivial
            role=spec.role,
            status=spec.status,
        )
        db.add(user)
    else:
        user.tenant_id = tenant.id
        user.role = spec.role
        user.status = spec.status
    db.flush()
    return spec.email


def main() -> int:
    provider = _provider_config()
    created: list[str] = []

    with SessionLocal() as db:
        for spec in TENANTS:
            tenant = _upsert_tenant(db, spec)
            if spec.byok:
                if provider is not None:
                    TenantLlmConfigService(db, tenant.id).set_config(
                        provider=provider["provider"], config=provider
                    )
                else:
                    print(
                        f"  ! {spec.slug}: QA_LLM_API_KEY unset — BYOK NOT configured; "
                        "ingestion/generation will fail until set.",
                        file=sys.stderr,
                    )
            for user_spec in spec.users:
                created.append(_upsert_user(db, tenant, user_spec))
            print(
                f"  ✓ tenant '{spec.name}' ({spec.slug}) "
                f"quota={spec.quota_monthly_generations or 'unlimited'} "
                f"byok={'yes' if spec.byok and provider else 'no'}"
            )
        db.commit()

    print(f"\nSeeded {len(created)} users across {len(TENANTS)} tenants.")
    print("Mint a token:  python -m scripts.mint_dev_token --sub <email>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
