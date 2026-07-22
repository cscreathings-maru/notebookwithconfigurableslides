"""Tenant-scoped repository for ChatMessage (one implicit thread per project)."""

from __future__ import annotations

import uuid

from ..models import ChatMessage
from ..tenancy.repository import TenantScopedRepository


class ChatRepository(TenantScopedRepository[ChatMessage]):
    model = ChatMessage

    def list_by_project(self, project_id: uuid.UUID) -> list[ChatMessage]:
        rows = (
            self.db.execute(
                self._scoped()
                .where(ChatMessage.project_id == project_id)
                .order_by(ChatMessage.created_at)
            )
            .scalars()
            .all()
        )
        return list(rows)
