"""notebook_guide + chat_message tables; relax generation profile/template NOT NULL

Adds the NotebookLM-style guide and chat models, and makes the governed
provenance columns on `generation` nullable so freeform decks (no profile) can be
stored in the same table.

Revision ID: 0005_guide_chat_freeform
Revises: 0004_outline_generation_usage
Create Date: 2026-07-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_guide_chat_freeform"
down_revision: Union[str, None] = "0004_outline_generation_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notebook_guide",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("suggested_questions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", name="uq_guide_tenant_project"),
    )
    op.create_index("ix_notebook_guide_tenant_id", "notebook_guide", ["tenant_id"])
    op.create_index("ix_notebook_guide_project_id", "notebook_guide", ["project_id"])

    op.create_table(
        "chat_message",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_message_tenant_id", "chat_message", ["tenant_id"])
    op.create_index("ix_chat_message_project_id", "chat_message", ["project_id"])

    # Freeform decks have no governing profile/template — relax the NOT NULLs.
    with op.batch_alter_table("generation") as batch:
        batch.alter_column("profile_id", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column("profile_version", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("template_id", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column("template_version", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("generation") as batch:
        batch.alter_column("template_version", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("template_id", existing_type=sa.Uuid(), nullable=False)
        batch.alter_column("profile_version", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("profile_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("chat_message")
    op.drop_table("notebook_guide")
