"""Track whether an assistant chat turn was cut off by the token cap (F1)

Chat completions were capped at `max_tokens=1000` — the lowest cap in the codebase,
hard-coded, and the only one on a surface producing long prose — and the provider's
own `finish_reason` was discarded, so a cut-off answer rendered identically to a
complete one. This adds `chat_message.truncated`, set from `finish_reason == "length"`
going forward. Existing rows backfill to `false`: their true completeness was never
recorded and cannot be recovered, and `false` is the same silent behaviour those
messages already had, not a new claim about them.

Revision ID: 0008_chat_message_truncated
Revises: 0007_chat_session
Create Date: 2026-08-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_chat_message_truncated"
down_revision: Union[str, None] = "0007_chat_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_message",
        sa.Column(
            "truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_message", "truncated")
