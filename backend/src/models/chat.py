"""ChatMessage — one turn in a project's RAG chat thread.

A single implicit thread per project (NotebookLM-style). Assistant messages carry
citations returned by Open Notebook's ask endpoint. Kept deliberately minimal; a
`session_id` can be added later if multiple threads per project are needed.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, JSON, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UuidPkMixin


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class ChatMessage(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "chat_message"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("project.id"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole, name="chat_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{source_id, snippet}] for assistant turns; empty for user turns.
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChatMessage {self.role.value} project={self.project_id}>"
