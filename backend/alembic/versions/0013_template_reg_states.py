"""TM-3/TM-2: split `fallback` into pending/failed/no_source; add register_template job type

`fallback` collapsed four situations into one badge: still registering, no PPTX
uploaded, engine rejected the deck, engine unreachable. Existing rows are mapped on
the one signal that distinguishes them -- whether a PPTX was ever stored:

  fallback + source_pptx_uri IS NOT NULL  -> failed     (something was attempted and didn't work)
  fallback + source_pptx_uri IS NULL      -> no_source  (nothing to register, not an error)
  registered / failed                     -> unchanged

New rows default to `pending`: registration is now dispatched as an Arq job (TM-2)
rather than run inline in the create request, so a freshly-created template starts
in-flight, not silently `registered`.

`job_type` gains `register_template`. Postgres allows adding an enum value directly
(no rename/recreate needed the way narrowing does) -- but that ALTER TYPE ADD VALUE
cannot be used in the same transaction as a query against the new value, so it is
its own migration step, run before anything could reference it.

Revision ID: 0013_template_reg_states
Revises: 0012_generation_studio_opened
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_template_reg_states"
down_revision: Union[str, None] = "0012_generation_studio_opened"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "template_registration_status"
_OLD_VALUES = ("registered", "fallback", "failed")
_NEW_VALUES = ("pending", "registered", "no_source", "failed")


def upgrade() -> None:
    # job_type: adding a value is a one-liner, no rebuild -- Postgres 12+.
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'register_template'")

    # template_registration_status: narrowing needs the rename/recreate/swap dance
    # (same shape as 0009_generation_status_cleanup), because `fallback` disappears
    # and existing rows need to be re-mapped onto the two states that replace it.
    op.execute(f"ALTER TYPE {_ENUM_NAME} RENAME TO {_ENUM_NAME}_old")
    sa.Enum(*_NEW_VALUES, name=_ENUM_NAME).create(op.get_bind(), checkfirst=True)

    op.execute(f"ALTER TABLE template ALTER COLUMN registration_status DROP DEFAULT")
    op.execute(
        f"ALTER TABLE template ALTER COLUMN registration_status "
        f"TYPE text USING registration_status::text"
    )
    op.execute(
        "UPDATE template SET registration_status = 'failed' "
        "WHERE registration_status = 'fallback' AND source_pptx_uri IS NOT NULL"
    )
    op.execute(
        "UPDATE template SET registration_status = 'no_source' "
        "WHERE registration_status = 'fallback' AND source_pptx_uri IS NULL"
    )
    op.execute(
        f"ALTER TABLE template ALTER COLUMN registration_status "
        f"TYPE {_ENUM_NAME} USING registration_status::{_ENUM_NAME}"
    )
    op.execute(
        f"ALTER TABLE template ALTER COLUMN registration_status SET DEFAULT 'pending'"
    )
    op.execute(f"DROP TYPE {_ENUM_NAME}_old")


def downgrade() -> None:
    # `pending` and `no_source` have no representation in the old 3-value enum.
    # Downgrade folds both onto `fallback`, the closest old meaning for each --
    # this loses the pending/no_source distinction, same class of lossy downgrade
    # as any enum-narrowing reversal.
    op.execute(f"ALTER TYPE {_ENUM_NAME} RENAME TO {_ENUM_NAME}_new")
    sa.Enum(*_OLD_VALUES, name=_ENUM_NAME).create(op.get_bind(), checkfirst=True)

    op.execute(f"ALTER TABLE template ALTER COLUMN registration_status DROP DEFAULT")
    op.execute(
        f"ALTER TABLE template ALTER COLUMN registration_status "
        f"TYPE text USING registration_status::text"
    )
    op.execute(
        "UPDATE template SET registration_status = 'fallback' "
        "WHERE registration_status IN ('pending', 'no_source')"
    )
    op.execute(
        f"ALTER TABLE template ALTER COLUMN registration_status "
        f"TYPE {_ENUM_NAME} USING registration_status::{_ENUM_NAME}"
    )
    op.execute(
        f"ALTER TABLE template ALTER COLUMN registration_status SET DEFAULT 'registered'"
    )
    op.execute(f"DROP TYPE {_ENUM_NAME}_new")

    # job_type: Postgres cannot drop an enum value at all; a row using
    # 'register_template' would make this downgrade fail outright, which is the
    # correct behaviour -- silently orphaning it would be worse.
    op.execute(
        "DELETE FROM job WHERE type = 'register_template'"
    )
