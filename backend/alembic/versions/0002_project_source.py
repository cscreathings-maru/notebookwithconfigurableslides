"""project + source tables (ingestion)

Revision ID: 0002_project_source
Revises: 0001_initial
Create Date: 2026-06-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_project_source"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("on_notebook_id", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_tenant_id", "project", ["tenant_id"])

    op.create_table(
        "source",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("pdf", "office", "csv", "text", "url", name="source_kind"),
            nullable=False,
        ),
        sa.Column("original_uri", sa.String(length=1024), nullable=False),
        sa.Column("on_source_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("queued", "processing", "ready", "failed", name="source_status"),
            nullable=False,
        ),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("analysis_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_tenant_id", "source", ["tenant_id"])
    op.create_index("ix_source_project_id", "source", ["project_id"])


def downgrade() -> None:
    op.drop_table("source")
    op.drop_table("project")
    for enum_name in ("source_status", "source_kind"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
