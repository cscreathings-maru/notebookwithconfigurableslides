"""Record whether the slide engine accepted a template (T-1.6)

Template registration falls back to Presenton's stock theme when the engine rejects
or cannot be reached. That fallback was previously invisible: the row looked identical
to a healthy one, so a user whose branding never applied had nothing to inspect.

Existing rows backfill to `registered`. That is the optimistic reading -- their true
outcome was never recorded and cannot be recovered. Templates that actually fell back
will keep rendering with the stock theme; re-uploading re-registers and records the
real status.

Revision ID: 0006_template_registration
Revises: 0005_guide_chat_freeform
Create Date: 2026-07-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_template_registration"
down_revision: Union[str, None] = "0005_guide_chat_freeform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REGISTRATION_STATUS = ("registered", "fallback", "failed")
_ENUM_NAME = "template_registration_status"


def upgrade() -> None:
    registration_status = sa.Enum(*_REGISTRATION_STATUS, name=_ENUM_NAME)
    registration_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "template",
        sa.Column(
            "registration_status",
            registration_status,
            nullable=False,
            server_default="registered",
        ),
    )
    op.add_column(
        "template",
        sa.Column("registration_error", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("template", "registration_error")
    op.drop_column("template", "registration_status")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
