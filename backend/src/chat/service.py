"""Chat service: RAG Q&A over a project's sources, with citations.

Pulls grounding snippets from Open Notebook search, answers with the resolved LLM
(OpenRouter in lite mode), and persists the user + assistant turns. Assistant turns
carry the snippets used as citations. Short recent history is included for coherence.
"""

from __future__ import annotations

import uuid

from ..core.logging import get_logger
from ..ingestion.repository import ProjectRepository
from ..models import ChatMessage, ChatRole
from ..tenancy.llm_config import TenantLlmConfigService
from .repository import ChatRepository

logger = get_logger("orchestrator.chat")

_HISTORY_TURNS = 6
_SNIPPET_CHARS = 240


class ChatService:
    def __init__(self, *, repo: ChatRepository, project_repo: ProjectRepository, on_client, llm):
        self.repo = repo
        self.project_repo = project_repo
        self.on_client = on_client
        self.llm = llm

    def list_messages(self, project_id: uuid.UUID) -> list[ChatMessage]:
        self.project_repo.get(project_id)  # 404 across tenants
        return self.repo.list_by_project(project_id)

    async def ask(self, *, project_id: uuid.UUID, question: str) -> ChatMessage:
        project = self.project_repo.get(project_id)
        provider_config = TenantLlmConfigService(self.repo.db, self.repo.tenant_id).get_config()

        snippets = []
        if project.on_notebook_id:
            snippets = await self.on_client.search(
                notebook_id=project.on_notebook_id, query=question
            )
        grounding = _grounding_text(snippets)
        history = _recent_history(self.repo.list_by_project(project_id))

        answer = await self.llm.chat(
            system=(
                "You answer questions strictly from the provided source excerpts. "
                "If the answer is not in the sources, say you don't have enough "
                "information. Be concise and cite facts to the sources."
            ),
            user=(
                f"Source excerpts:\n{grounding or '(no relevant excerpts found)'}\n\n"
                f"Question: {question}"
            ),
            provider_config=provider_config,
            history=history,
            temperature=0.2,
            max_tokens=1000,
        )

        # Persist the user turn, then the assistant turn with citations.
        self.repo.add(ChatMessage(project_id=project.id, role=ChatRole.user, content=question))
        assistant = ChatMessage(
            project_id=project.id,
            role=ChatRole.assistant,
            content=answer.text,
            citations=_citations(snippets),
        )
        self.repo.add(assistant)
        logger.info("chat_answered", extra={"project_id": str(project_id)})
        return assistant


def _grounding_text(snippets: list[dict]) -> str:
    return "\n".join(f"- {s.get('text', '')}" for s in snippets if s.get("text")).strip()


def _citations(snippets: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in snippets:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append({"source_ref": s.get("source_ref"), "snippet": text[:_SNIPPET_CHARS]})
    return out


def _recent_history(messages: list[ChatMessage]) -> list[dict[str, str]]:
    recent = messages[-_HISTORY_TURNS:]
    return [{"role": m.role.value, "content": m.content} for m in recent]
