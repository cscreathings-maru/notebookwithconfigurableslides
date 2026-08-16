"""LD-9/LD-11 cutover: drop the geometric inspection columns, deck_spec/
layout_plan become deck_plan.

`deck/inspect.py`, `deck/roles.py`, `deck/preview.py`, `deck/matcher.py` and
the old `deck/planner.py`/`deck/spec.py` are deleted (LD-11) -- nothing reads
`layout_catalog`/`inspection_report`/`inspection_status`/`inspection_error`
or `generation.deck_spec`/`generation.layout_plan` anymore. `TemplateStatus`
(the Postgres enum `template_inspection_status`) is dropped with its column.

Dropped outright, not migrated: none of this is meaningful data to carry
forward under the new pipeline (a geometric layout read for a renderer that
no longer builds from layouts; a `DeckSpec`/`LayoutPlan` pair for a plan
shape that no longer exists) -- same posture 0015 took dropping
`presenton_presentation_id`/`studio_opened_at`.

A pre-existing `Template` row loses its inspection state and lands at
`catalog_status = 'no_source'` (0017's default) if it hasn't already been
catalogued -- an admin uploads (or the row already has a `.pptx` and can be
`recatalog`ued) and reviews it, the same path any template takes now.

Revision ID: 0018_deck_plan_cutover
Revises: 0017_deck_catalog
Create Date: 2026-08-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_deck_plan_cutover"
down_revision: Union[str, None] = "0017_deck_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INSPECTION_STATUS_ENUM = "template_inspection_status"
_INSPECTION_STATUS_VALUES = ("ready", "no_source", "rejected")


def upgrade() -> None:
    op.drop_column("template", "layout_catalog")
    op.drop_column("template", "inspection_report")
    op.drop_column("template", "inspection_status")
    op.drop_column("template", "inspection_error")
    op.execute(f"DROP TYPE {_INSPECTION_STATUS_ENUM}")

    op.add_column("generation", sa.Column("deck_plan", sa.JSON(), nullable=True))
    op.drop_column("generation", "deck_spec")
    op.drop_column("generation", "layout_plan")


def downgrade() -> None:
    sa.Enum(*_INSPECTION_STATUS_VALUES, name=_INSPECTION_STATUS_ENUM).create(op.get_bind(), checkfirst=True)
    op.add_column("template", sa.Column("layout_catalog", sa.JSON(), nullable=True))
    op.add_column("template", sa.Column("inspection_report", sa.JSON(), nullable=True))
    op.add_column(
        "template",
        sa.Column(
            "inspection_status",
            sa.Enum(*_INSPECTION_STATUS_VALUES, name=_INSPECTION_STATUS_ENUM),
            nullable=False,
            server_default="no_source",
        ),
    )
    op.add_column("template", sa.Column("inspection_error", sa.String(1024), nullable=True))

    op.add_column("generation", sa.Column("deck_spec", sa.JSON(), nullable=True))
    op.add_column("generation", sa.Column("layout_plan", sa.JSON(), nullable=True))
    op.drop_column("generation", "deck_plan")
