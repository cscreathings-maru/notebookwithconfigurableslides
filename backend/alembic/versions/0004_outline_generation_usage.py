"""outline + usage_record tables; expand generation with artifacts/provenance

Revision ID: 0004_outline_generation_usage
Revises: 0003_registry_generation
Create Date: 2026-06-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_outline_generation_usage"
down_revision: Union[str, None] = "0003_registry_generation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outline",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outline_tenant_id", "outline", ["tenant_id"])
    op.create_index("ix_outline_project_id", "outline", ["project_id"])

    op.create_table(
        "usage_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource", sa.JSON(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("cost_estimate", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_record_tenant_id", "usage_record", ["tenant_id"])

    # Expand generation with Slice 3 artifacts + provenance.
    with op.batch_alter_table("generation") as batch:
        batch.add_column(sa.Column("source_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("params", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("presenton_presentation_id", sa.String(length=255), nullable=True)
        )
        batch.add_column(sa.Column("pptx_uri", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("pdf_uri", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("consistency_report", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("error", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation") as batch:
        for col in (
            "error",
            "consistency_report",
            "pdf_uri",
            "pptx_uri",
            "presenton_presentation_id",
            "params",
            "source_ids",
        ):
            batch.drop_column(col)
    op.drop_table("usage_record")
    op.drop_table("outline")
