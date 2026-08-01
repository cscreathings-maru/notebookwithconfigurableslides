"""Split a project's single chat thread into named sessions (Phase C)

`chat_message` carried only `project_id`, so every question a project ever asked
lived in one undifferentiated stream and unrelated topics collided. This adds
`chat_session` and moves messages under it.

Existing messages are preserved: one session is created per (tenant, project) that
has messages, titled from that project's first user question, and every message is
attached to it. Nothing is dropped and no thread is reordered — a user who upgrades
sees exactly their old conversation, now named.

`archived_at` is a soft delete. Undo has to restore the messages, not just the row,
so archiving is what makes the client's undo honest.

Revision ID: 0007_chat_session
Revises: 0006_template_registration
Create Date: 2026-07-31
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_chat_session"
down_revision: Union[str, None] = "0006_template_registration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TITLE_MAX = 200
# Mirrors ChatService._AUTO_TITLE_CHARS so backfilled titles look like new ones.
_AUTO_TITLE_CHARS = 60


def _derive_title(question: str) -> str:
    cleaned = " ".join((question or "").split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= _AUTO_TITLE_CHARS:
        return cleaned[:_TITLE_MAX]
    head = cleaned[:_AUTO_TITLE_CHARS]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return f"{cut}…"[:_TITLE_MAX]


def upgrade() -> None:
    op.create_table(
        "chat_session",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("project.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(_TITLE_MAX), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Nullable first so existing rows survive the add; tightened after the backfill.
    op.add_column(
        "chat_message", sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=True)
    )

    _backfill_sessions()

    with op.batch_alter_table("chat_message") as batch:
        batch.alter_column("session_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)
        batch.create_foreign_key(
            "fk_chat_message_session", "chat_session", ["session_id"], ["id"]
        )
    op.create_index("ix_chat_message_session_id", "chat_message", ["session_id"])


# Typed lightweight tables rather than raw `sa.text()`. Raw SQL binds a Python UUID as
# an opaque object, which SQLite's driver rejects outright ("type 'UUID' is not
# supported") and which no dialect coerces for us. Declaring the column types lets
# SQLAlchemy adapt UUIDs to each backend's representation.
_session_tbl = sa.table(
    "chat_session",
    sa.column("id", sa.Uuid(as_uuid=True)),
    sa.column("tenant_id", sa.Uuid(as_uuid=True)),
    sa.column("project_id", sa.Uuid(as_uuid=True)),
    sa.column("title", sa.String(_TITLE_MAX)),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_message_tbl = sa.table(
    "chat_message",
    sa.column("session_id", sa.Uuid(as_uuid=True)),
    sa.column("tenant_id", sa.Uuid(as_uuid=True)),
    sa.column("project_id", sa.Uuid(as_uuid=True)),
    sa.column("content", sa.Text()),
    sa.column("role", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _as_uuid(value: object) -> uuid.UUID:
    """Ids come back as UUID on Postgres and as text on SQLite; normalise both."""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _backfill_sessions() -> None:
    """One session per (tenant, project) with messages, titled from its first question."""
    bind = op.get_bind()
    groups = bind.execute(
        sa.select(
            _message_tbl.c.tenant_id,
            _message_tbl.c.project_id,
            sa.func.min(_message_tbl.c.created_at).label("first_at"),
            sa.func.max(_message_tbl.c.created_at).label("last_at"),
        ).group_by(_message_tbl.c.tenant_id, _message_tbl.c.project_id)
    ).fetchall()

    for raw_tenant, raw_project, first_at, last_at in groups:
        tenant_id, project_id = _as_uuid(raw_tenant), _as_uuid(raw_project)
        opening = bind.execute(
            sa.select(_message_tbl.c.content)
            .where(_message_tbl.c.tenant_id == tenant_id)
            .where(_message_tbl.c.project_id == project_id)
            .where(_message_tbl.c.role == "user")
            .order_by(_message_tbl.c.created_at.asc())
            .limit(1)
        ).scalar()

        session_id = uuid.uuid4()
        bind.execute(
            _session_tbl.insert().values(
                id=session_id,
                tenant_id=tenant_id,
                project_id=project_id,
                title=_derive_title(opening or "") or None,
                created_at=first_at,
                updated_at=last_at,
            )
        )
        bind.execute(
            _message_tbl.update()
            .where(_message_tbl.c.tenant_id == tenant_id)
            .where(_message_tbl.c.project_id == project_id)
            .values(session_id=session_id)
        )


def downgrade() -> None:
    op.drop_index("ix_chat_message_session_id", table_name="chat_message")
    with op.batch_alter_table("chat_message") as batch:
        batch.drop_constraint("fk_chat_message_session", type_="foreignkey")
        batch.drop_column("session_id")
    op.drop_table("chat_session")
