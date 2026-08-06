"""Persist the slide thumbnails the engine already returns at registration (DG-3)

`POST /templates/fonts-upload-and-slides-preview` returns `slide_image_urls`
alongside `pptx_url`/`fonts` -- forwarded to `init` and then discarded ever since
T-1.3 shipped. A template picker needs something to show; this stops throwing that
away. Additive only.

Revision ID: 0011_template_thumbnails
Revises: 0010_freeform_outline
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_template_thumbnails"
down_revision: Union[str, None] = "0010_freeform_outline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "template",
        sa.Column("slide_image_urls", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("template", "slide_image_urls")
