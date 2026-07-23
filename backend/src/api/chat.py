"""Chat router — RAG Q&A over a project's sources.

GET lists the thread; POST asks a question and returns the assistant turn with
citations. Answering is synchronous (a few seconds); the caller shows a spinner.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ..auth.principal import Principal
from ..chat.service import ChatService
from ..models import ChatMessage
from ..schemas.chat import ChatAsk, ChatMessageResponse
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


@router.get("/projects/{project_id}/chat", response_model=list[ChatMessageResponse])
def list_chat(
    project_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    service: ChatService = Depends(get_chat_service),
) -> list[ChatMessageResponse]:
    return [_to_response(m) for m in service.list_messages(project_id)]


@router.post("/projects/{project_id}/chat", response_model=ChatMessageResponse)
async def ask_chat(
    project_id: uuid.UUID,
    payload: ChatAsk,
    _: Principal = Depends(require_author),
    service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    assistant = await service.ask(
        project_id=project_id, question=payload.question, language=payload.language
    )
    return _to_response(assistant)
