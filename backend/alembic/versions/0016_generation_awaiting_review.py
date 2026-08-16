"""RM-9: add the `awaiting_review` generation status (D5).

A layout plan with a slide the matcher could not confidently place parks here
instead of rendering something the user never saw coming. Plans with no
low-confidence slide skip it entirely and go straight to `queued`.

Widening an enum is additive -- Postgres 12+ takes `ADD VALUE` directly, with
no rename/recreate dance (contrast 0013/0014, which both NARROWED an enum and
needed the full swap). `ADD VALUE` cannot run in the same transaction as a
query against the new value, which is why nothing else happens in this
migration.

Revision ID: 0016_generation_awaiting_review
Revises: 0015_deck_pipeline_generation
Create Date: 2026-08-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0016_gen_awaiting_review"
down_revision: Union[str, None] = "0015_deck_pipeline_generation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE generation_status ADD VALUE IF NOT EXISTS 'awaiting_review'")


def downgrade() -> None:
    # Postgres cannot drop an enum value. A row still parked in review would
    # make any narrowing fail outright -- correct behaviour, but it means the
    # rows must be resolved first rather than silently rewritten. Failing them
    # is the honest move: they were never rendered.
    op.execute(
        "UPDATE generation SET status = 'failed', "
        "error = 'Layout review was pending when the schema was rolled back.' "
        "WHERE status = 'awaiting_review'"
    )
