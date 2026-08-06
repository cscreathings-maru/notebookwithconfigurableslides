"""Make Outline.profile_id/profile_version nullable for the freeform path (DG-1)

The governed path pins a profile version to every outline it builds; the new
freeform path (the LLM proposes structure itself, no `StakeholderProfile`
required) has none. Mirrors `Generation.profile_id` already being nullable for
its own freeform path (0003_registry_generation). Additive only -- existing
governed-path rows are untouched, and the column stays NOT NULL in practice for
every row this migration doesn't touch.

Revision ID: 0010_freeform_outline
Revises: 0009_generation_status_cleanup
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Integer, Uuid

revision: str = "0010_freeform_outline"
down_revision: Union[str, None] = "0009_generation_status_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("outline", "profile_id", existing_type=Uuid(), nullable=True)
    op.alter_column("outline", "profile_version", existing_type=Integer(), nullable=True)


def downgrade() -> None:
    # Any freeform (profile_id IS NULL) row created since upgrade cannot satisfy
    # NOT NULL again -- this is a data-destructive downgrade by necessity, same as
    # any nullable->required column reversal. Delete them first if this ever runs
    # against a database that has freeform outlines.
    op.execute("DELETE FROM outline WHERE profile_id IS NULL")
    op.alter_column("outline", "profile_version", existing_type=Integer(), nullable=False)
    op.alter_column("outline", "profile_id", existing_type=Uuid(), nullable=False)
