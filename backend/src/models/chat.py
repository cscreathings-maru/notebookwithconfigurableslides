"""Chat sessions and the turns inside them.

A project holds many named sessions so unrelated lines of enquiry stay apart —
onboarding questions and pricing questions no longer share one undifferentiated
stream. Assistant messages carry citations returned by Open Notebook's search.

Deletion is soft (`archived_at`). Undo has to restore the *messages*, not just the
row, so a hard delete would make the undo a lie; archiving keeps the thread intact
and makes restore a single field write.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UpdatedAtMixin, UuidPkMixin

# Titles are auto-derived from the first question, so they need room for a sentence
# but not a paragraph. Enforced here and in the schema.
TITLE_MAX_CHARS = 200


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class ChatSession(UuidPkMixin, TimestampMixin, UpdatedAtMixin, Base):
    """One named conversation thread within a project."""

    __tablename__ = "chat_session"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=False, index=True
    )
    # Null until the first question arrives, at which point it is derived from that
    # question. A session the user renamed keeps its title; deriving only when null
    # is what stops an explicit rename being overwritten by the next message.
    title: Mapped[str | None] = mapped_column(String(TITLE_MAX_CHARS), nullable=True)
    # Soft delete. Non-null means hidden from listings but fully restorable.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChatSession {self.id} project={self.project_id}>"


class ChatMessage(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "chat_message"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_session.id"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole, name="chat_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{source_ref, snippet}] for assistant turns; empty for user turns.
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChatMessage {self.role.value} session={self.session_id}>"
