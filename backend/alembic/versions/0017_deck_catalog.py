"""LD-3: LLM template cataloguing (deck/catalog.py) -- new columns, new job type.

Purely additive: `template_catalog_status` is a brand-new enum (not a
narrowing of an existing one), so this needs none of 0013/0014's
rename/recreate dance -- just `CREATE TYPE` and `ADD COLUMN`. `job_type`
gains `catalog_template` the same way 0016 widened `generation_status`:
`ADD VALUE` on a live enum, additive, no data to migrate.

Every new Template column is nullable or has a safe default, so existing
rows land at `catalog_status = 'no_source'` -- honest, since no cataloguing
has ever run for them; an admin (or a `recatalog` call) can produce their
first catalog going forward. `TemplateStatus`/`inspection_status` and
`layout_catalog` are UNTOUCHED here -- they remain the active render path
until `PLAN-LLM-DECK-PLANNING.md`'s Phase C cutover.

Revision ID: 0017_deck_catalog
Revises: 0016_gen_awaiting_review
Create Date: 2026-08-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_deck_catalog"
down_revision: Union[str, None] = "0016_gen_awaiting_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATALOG_STATUS_ENUM = "template_catalog_status"
_CATALOG_STATUS_VALUES = ("no_source", "cataloguing", "ready", "failed")


def upgrade() -> None:
    sa.Enum(*_CATALOG_STATUS_VALUES, name=_CATALOG_STATUS_ENUM).create(op.get_bind(), checkfirst=True)

    op.add_column("template", sa.Column("slide_catalog", sa.JSON(), nullable=True))
    op.add_column(
        "template",
        sa.Column(
            "catalog_status",
            sa.Enum(*_CATALOG_STATUS_VALUES, name=_CATALOG_STATUS_ENUM),
            nullable=False,
            server_default="no_source",
        ),
    )
    op.add_column("template", sa.Column("catalog_error", sa.String(1024), nullable=True))
    op.add_column("template", sa.Column("catalog_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("template", sa.Column("catalog_reviewed_by", sa.Uuid(as_uuid=True), nullable=True))

    # A pre-existing template with a stored .pptx has something to catalogue;
    # say so honestly rather than leaving it silently indistinguishable from
    # a template with no source at all -- an operator re-running `recatalog`
    # against every `no_source` row would waste calls on rows that never had
    # a .pptx to begin with.
    op.execute(
        "UPDATE template SET catalog_status = 'no_source' WHERE source_pptx_uri IS NULL"
    )

    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'catalog_template'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value (job_type keeps
    # 'catalog_template' harmlessly, same posture as 0016's downgrade note --
    # a job row still queued with this type would make a narrowing fail
    # outright, which is correct: it was never processed).
    op.drop_column("template", "catalog_reviewed_by")
    op.drop_column("template", "catalog_reviewed_at")
    op.drop_column("template", "catalog_error")
    op.drop_column("template", "catalog_status")
    op.drop_column("template", "slide_catalog")
    op.execute(f"DROP TYPE {_CATALOG_STATUS_ENUM}")
