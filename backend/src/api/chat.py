"""Chat router — RAG Q&A over a project's sources, split into named sessions.

Sessions let one project hold several unrelated lines of enquiry. Every message
endpoint accepts an optional `session_id`; omitting it targets the project's most
recent session (created on demand), so a caller that knows nothing about sessions
still works.

Answering is synchronous (a few seconds); the caller shows a spinner.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..auth.principal import Principal
from ..chat.repository import DEFAULT_MESSAGE_LIMIT, MAX_MESSAGE_LIMIT
from ..chat.service import ChatService
from ..models import ChatMessage, ChatSession
from ..schemas.chat import (
    ChatAsk,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionRename,
    ChatSessionResponse,
)
from ..tenancy.rbac import require_author, require_viewer
from .deps import get_chat_service

router = APIRouter(tags=["chat"])


def _to_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=list(message.citations or []),
        created_at=message.created_at,
    )


def _session_response(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        project_id=session.project_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


# --- sessions ------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/chat/sessions", response_model=list[ChatSessionResponse]
)
def list_sessions(
    project_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    service: ChatService = Depends(get_chat_service),
) -> list[ChatSessionResponse]:
    return [_session_response(s) for s in service.list_sessions(project_id)]


@router.post(
    "/projects/{project_id}/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=201,
)
def create_session(
    project_id: uuid.UUID,
    payload: ChatSessionCreate,
    _: Principal = Depends(require_author),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    return _session_response(service.create_session(project_id, title=payload.title))


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_session(
    session_id: uuid.UUID,
    payload: ChatSessionRename,
    _: Principal = Depends(require_author),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    return _session_response(service.rename_session(session_id, title=payload.title))


@router.delete("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def archive_session(
    session_id: uuid.UUID,
    _: Principal = Depends(require_author),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    """Soft delete: the thread is hidden but every message survives for `restore`."""
    return _session_response(service.archive_session(session_id))


@router.post("/chat/sessions/{session_id}/restore", response_model=ChatSessionResponse)
def restore_session(
    session_id: uuid.UUID,
    _: Principal = Depends(require_author),
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    """Undo an archive. Reaches archived rows, still only within the tenant."""
    return _session_response(service.restore_session(session_id))


# --- messages ------------------------------------------------------------------


@router.get("/projects/{project_id}/chat", response_model=list[ChatMessageResponse])
def list_chat(
    project_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    limit: int = Query(DEFAULT_MESSAGE_LIMIT, ge=1, le=MAX_MESSAGE_LIMIT),
    before: datetime | None = Query(
        None, description="Return turns older than this timestamp (pagination cursor)."
    ),
    _: Principal = Depends(require_viewer),
    service: ChatService = Depends(get_chat_service),
) -> list[ChatMessageResponse]:
    messages = service.list_messages(
        project_id, session_id=session_id, limit=limit, before=before
    )
    return [_to_response(m) for m in messages]


@router.post("/projects/{project_id}/chat", response_model=ChatMessageResponse)
async def ask_chat(
    project_id: uuid.UUID,
    payload: ChatAsk,
    _: Principal = Depends(require_author),
    service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    assistant = await service.ask(
        project_id=project_id,
        question=payload.question,
        language=payload.language,
        session_id=payload.session_id,
    )
    return _to_response(assistant)
