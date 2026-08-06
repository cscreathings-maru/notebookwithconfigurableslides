"""Remove the two GenerationStatus values nothing ever assigned (DG-5)

`analyzing` and `building_outline` were declared on the enum from the start
(0003_registry_generation) but no code path ever set either -- confirmed by grep
across `src/` before this migration was written; the only match was the enum
declaration itself. Outline building now happens before a `Generation` row exists
at all (DG-1/DG-2: its own request/response, its own spinner), so these were never
going to become real generation-internal states. Safe to narrow unconditionally:
no existing row can hold either value.

Revision ID: 0009_generation_status_cleanup
Revises: 0008_chat_message_truncated
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_generation_status_cleanup"
down_revision: Union[str, None] = "0008_chat_message_truncated"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "generation_status"
_OLD_VALUES = (
    "queued",
    "analyzing",
    "building_outline",
    "generating",
    "validating",
    "ready",
    "failed",
)
_NEW_VALUES = ("queued", "generating", "validating", "ready", "failed")


def _swap_enum(*, from_values: tuple[str, ...], to_values: tuple[str, ...]) -> None:
    op.execute(f"ALTER TYPE {_ENUM_NAME} RENAME TO {_ENUM_NAME}_old")
    sa.Enum(*to_values, name=_ENUM_NAME).create(op.get_bind(), checkfirst=True)
    op.execute(
        f"ALTER TABLE generation ALTER COLUMN status "
        f"TYPE {_ENUM_NAME} USING status::text::{_ENUM_NAME}"
    )
    op.execute(f"DROP TYPE {_ENUM_NAME}_old")


def upgrade() -> None:
    _swap_enum(from_values=_OLD_VALUES, to_values=_NEW_VALUES)


def downgrade() -> None:
    _swap_enum(from_values=_NEW_VALUES, to_values=_OLD_VALUES)
