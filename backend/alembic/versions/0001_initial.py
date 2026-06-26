"""initial schema: tenant, user_account, job

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", name="tenant_status"),
            nullable=False,
        ),
        sa.Column("llm_provider", sa.String(length=100), nullable=True),
        sa.Column("llm_config_enc", sa.LargeBinary(), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("quota_monthly_generations", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )
    op.create_index("ix_tenant_slug", "tenant", ["slug"])

    op.create_table(
        "user_account",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("oidc_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "author", "viewer", name="user_role"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="user_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        sa.UniqueConstraint("oidc_subject", name="uq_user_oidc_subject"),
    )
    op.create_index("ix_user_account_tenant_id", "user_account", ["tenant_id"])
    op.create_index("ix_user_account_oidc_subject", "user_account", ["oidc_subject"])

    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column(
            "type",
            sa.Enum("ingest", "generate", name="job_type"),
            nullable=False,
        ),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "succeeded", "failed", name="job_status"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_job_tenant_idem"),
    )
    op.create_index("ix_job_tenant_id", "job", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("job")
    op.drop_table("user_account")
    op.drop_table("tenant")
    for enum_name in ("job_status", "job_type", "user_status", "user_role", "tenant_status"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
