"""Tenant-scoped repositories for chat sessions and their messages."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from ..models import ChatMessage, ChatRole, ChatSession
from ..models.base import utcnow
from ..tenancy.repository import TenantScopedRepository

# A thread renders newest-last; this caps the first paint. Older turns load on demand.
DEFAULT_MESSAGE_LIMIT = 50
MAX_MESSAGE_LIMIT = 200


class ChatSessionRepository(TenantScopedRepository[ChatSession]):
    model = ChatSession

    def list_by_project(self, project_id: uuid.UUID) -> list[ChatSession]:
        """Live sessions, most recently updated first. Archived rows are excluded."""
        rows = (
            self.db.execute(
                self._scoped()
                .where(ChatSession.project_id == project_id)
                .where(ChatSession.archived_at.is_(None))
                .order_by(ChatSession.updated_at.desc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def latest_for_project(self, project_id: uuid.UUID) -> ChatSession | None:
        """The session a request without an explicit `session_id` should land in."""
        return self.db.execute(
            self._scoped()
            .where(ChatSession.project_id == project_id)
            .where(ChatSession.archived_at.is_(None))
            .order_by(ChatSession.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def create(self, *, project_id: uuid.UUID, title: str | None = None) -> ChatSession:
        return self.add(ChatSession(project_id=project_id, title=title))

    def archive(self, session: ChatSession) -> ChatSession:
        session.archived_at = utcnow()
        self.db.add(session)
        self.db.flush()
        return session

    def restore(self, session: ChatSession) -> ChatSession:
        session.archived_at = None
        self.db.add(session)
        self.db.flush()
        return session

    def get_archived(self, session_id: uuid.UUID) -> ChatSession:
        """Fetch regardless of archived state — restore has to reach archived rows.

        Still tenant-scoped: `_scoped()` cannot be issued without the tenant filter.
        """
        from ..core.errors import NotFoundError

        obj = self.db.execute(
            self._scoped().where(ChatSession.id == session_id)
        ).scalar_one_or_none()
        if obj is None:
            raise NotFoundError("ChatSession not found.")
        return obj

    def touch(self, session: ChatSession) -> None:
        """Bump `updated_at` so the session sorts to the top of the switcher."""
        session.updated_at = utcnow()
        self.db.add(session)
        self.db.flush()


class ChatRepository(TenantScopedRepository[ChatMessage]):
    model = ChatMessage

    def list_by_session(
        self,
        session_id: uuid.UUID,
        *,
        limit: int = DEFAULT_MESSAGE_LIMIT,
        before: datetime | None = None,
    ) -> list[ChatMessage]:
        """The newest `limit` turns before `before`, returned oldest-first.

        Windowing runs newest-first in SQL and is reversed for display: a thread grows
        at the end, so "the most recent page" is the one worth fetching. An unbounded
        list was the previous behaviour and it grew forever.
        """
        capped = max(1, min(limit, MAX_MESSAGE_LIMIT))
        stmt = self._scoped().where(ChatMessage.session_id == session_id)
        if before is not None:
            stmt = stmt.where(ChatMessage.created_at < before)
        rows = (
            self.db.execute(
                stmt.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(
                    capped
                )
            )
            .scalars()
            .all()
        )
        return list(reversed(rows))

    def preceding_user_question(self, message: ChatMessage) -> str | None:
        """The user turn a given assistant turn answered.

        `ask()` always persists the user turn immediately before its assistant reply
        in the same session, so "the latest user turn at or before this one" recovers
        the original question. Needed by `continue_message`: the grounding search has
        to be re-run to build a continuation prompt, and the question is not stored on
        the assistant row itself.
        """
        row = self.db.execute(
            self._scoped()
            .where(ChatMessage.session_id == message.session_id)
            .where(ChatMessage.role == ChatRole.user)
            .where(ChatMessage.created_at <= message.created_at)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row.content if row else None

    def count_in_session(self, session_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.tenant_id == self.tenant_id)
                .where(ChatMessage.session_id == session_id)
            ).scalar_one()
        )
