"""RM-3: template inspection moves in-process; drop the engine-registration columns.

Registration never once succeeded in this codebase's history (TD-32: every
attempt 404'd until the TM-1..6 fix landed, and even then needed a live VPS
deploy to prove out) -- there is no engine-side state worth preserving.
`presenton_template_ref` and `slide_image_urls` are dropped outright, not
migrated.

`registration_status` (pending/registered/no_source/failed) becomes
`inspection_status` (ready/no_source/rejected) -- `pending` has no meaning
anymore (inspection is a synchronous local parse, not an engine round trip
to be mid-flight on), so existing rows are re-mapped on the one signal that
still applies:

  registered -> ready       (an engine accepted it once; still needs a real
                              `reinspect` to get a `layout_catalog`, but
                              `ready` is the closer starting point than
                              `rejected`)
  failed     -> rejected    (the engine said no; the reason is preserved in
                              inspection_error/registration_error)
  pending    -> rejected    (never resolved under the old async flow; the
                              honest state is "needs a `reinspect` run", not
                              a status that pretends it succeeded)
  no_source  -> no_source   (unchanged; still the correct disposition)

None of these rows get a `layout_catalog` from this migration -- it can only
be produced by actually running `deck/inspect.py` against the stored
`.pptx`. `ready` rows without one need a `reinspect` call before they can be
used in a generation; `RM-11`'s worker wiring must check for that rather
than assume `ready` implies a populated catalog.

Revision ID: 0014_template_local_inspection
Revises: 0013_template_reg_states
Create Date: 2026-08-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_template_local_inspection"
down_revision: Union[str, None] = "0013_template_reg_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = "template_registration_status"
_NEW_ENUM = "template_inspection_status"
_OLD_VALUES = ("pending", "registered", "no_source", "failed")
_NEW_VALUES = ("ready", "no_source", "rejected")


def upgrade() -> None:
    # New JSON columns first -- additive, no data to move.
    op.add_column("template", sa.Column("layout_catalog", sa.JSON(), nullable=True))
    op.add_column("template", sa.Column("inspection_report", sa.JSON(), nullable=True))

    # registration_status -> inspection_status: narrowing needs the
    # rename/recreate/swap dance (0013's pattern), because `pending` folds
    # into `rejected` and `registered` renames to `ready`.
    sa.Enum(*_NEW_VALUES, name=_NEW_ENUM).create(op.get_bind(), checkfirst=True)
    op.add_column(
        "template",
        sa.Column(
            "inspection_status",
            sa.Enum(*_NEW_VALUES, name=_NEW_ENUM),
            nullable=False,
            server_default="no_source",
        ),
    )
    op.execute("UPDATE template SET inspection_status = 'ready' WHERE registration_status = 'registered'")
    op.execute(
        "UPDATE template SET inspection_status = 'rejected' "
        "WHERE registration_status IN ('failed', 'pending')"
    )
    op.execute("UPDATE template SET inspection_status = 'no_source' WHERE registration_status = 'no_source'")

    op.alter_column("template", "registration_error", new_column_name="inspection_error")

    op.drop_column("template", "registration_status")
    op.drop_column("template", "presenton_template_ref")
    op.drop_column("template", "slide_image_urls")

    op.execute(f"DROP TYPE {_OLD_ENUM}")


def downgrade() -> None:
    sa.Enum(*_OLD_VALUES, name=_OLD_ENUM).create(op.get_bind(), checkfirst=True)
    op.add_column(
        "template",
        sa.Column(
            "registration_status",
            sa.Enum(*_OLD_VALUES, name=_OLD_ENUM),
            nullable=False,
            server_default="pending",
        ),
    )
    op.execute("UPDATE template SET registration_status = 'registered' WHERE inspection_status = 'ready'")
    op.execute("UPDATE template SET registration_status = 'failed' WHERE inspection_status = 'rejected'")
    op.execute("UPDATE template SET registration_status = 'no_source' WHERE inspection_status = 'no_source'")

    op.alter_column("template", "inspection_error", new_column_name="registration_error")

    op.add_column("template", sa.Column("presenton_template_ref", sa.String(255), nullable=True))
    op.add_column(
        "template", sa.Column("slide_image_urls", sa.JSON(), nullable=False, server_default="[]")
    )

    op.drop_column("template", "inspection_status")
    op.drop_column("template", "layout_catalog")
    op.drop_column("template", "inspection_report")

    op.execute(f"DROP TYPE {_NEW_ENUM}")
