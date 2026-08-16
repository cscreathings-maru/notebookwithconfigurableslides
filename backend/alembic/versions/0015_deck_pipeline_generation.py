"""RM-11: generation carries a DeckSpec + LayoutPlan, not an engine id.

`presenton_presentation_id` drops -- rendering is local now (`deck/renderer.py`),
deterministic from `deck_spec` + `layout_plan` + the pinned template's
`layout_catalog`, so there is no engine-side id to hold and `pptx_uri`
presence is a sufficient resumability key on its own.

`studio_opened_at` drops with it -- it existed to gate NoteAI's own download
once a deck had been opened in Presenton's studio for editing (`TD-24`: the
engine's copy could diverge from the stored artifact). D1 removed the studio
entirely; nothing sets this column anymore, and the column existing while
nothing sets it is worse than not having it, not better.

Both are dropped outright, not migrated -- neither is meaningful data to
carry forward (an engine id for an engine that will no longer be called; a
timestamp gating a feature that no longer exists).

Revision ID: 0015_deck_pipeline_generation
Revises: 0014_template_local_inspection
Create Date: 2026-08-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_deck_pipeline_generation"
down_revision: Union[str, None] = "0014_template_local_inspection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("generation", sa.Column("deck_spec", sa.JSON(), nullable=True))
    op.add_column("generation", sa.Column("layout_plan", sa.JSON(), nullable=True))
    op.drop_column("generation", "presenton_presentation_id")
    op.drop_column("generation", "studio_opened_at")


def downgrade() -> None:
    op.add_column(
        "generation", sa.Column("studio_opened_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "generation", sa.Column("presenton_presentation_id", sa.String(255), nullable=True)
    )
    op.drop_column("generation", "layout_plan")
    op.drop_column("generation", "deck_spec")
