"""Track when a generation's studio was opened, for the download cutover (DG-4)

Editing in Presenton updates only the engine's own copy (TD-24); NoteAI's stored
artifact is produced once, at generation time. Once a user has opened the studio for
a generation, its stored artifact can no longer be trusted to reflect what they see
there, so downloads from NoteAI stop being offered for it (locked decision Q6,
Option C) -- durable and shared across viewers, not a client-only flag that would
reset on reload or not hold for a second person looking at the same generation.

Revision ID: 0012_generation_studio_opened
Revises: 0011_template_thumbnails
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_generation_studio_opened"
down_revision: Union[str, None] = "0011_template_thumbnails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation",
        sa.Column("studio_opened_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation", "studio_opened_at")
