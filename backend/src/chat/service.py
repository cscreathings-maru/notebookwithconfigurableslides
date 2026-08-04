"""Chat service: RAG Q&A over a project's sources, with citations.

Pulls grounding snippets from Open Notebook search, answers with the resolved LLM
(OpenRouter in lite mode), and persists the user + assistant turns into a session.
Assistant turns carry the snippets used as citations. Short recent history is
included for coherence.

A project holds many sessions. Requests that name none land in the most recently
used one, creating it if the project has never been chatted with — so a caller that
knows nothing about sessions still works.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..core.config import get_settings
from ..core.errors import NotFoundError, ValidationError
from ..core.logging import get_logger
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..models import ChatMessage, ChatRole, ChatSession
from ..models.chat import TITLE_MAX_CHARS
from ..tenancy.llm_config import TenantLlmConfigService
from .repository import DEFAULT_MESSAGE_LIMIT, ChatRepository, ChatSessionRepository

logger = get_logger("orchestrator.chat")

_HISTORY_TURNS = 6
_SNIPPET_CHARS = 240
# Long enough to tell two threads apart in a narrow switcher, short enough not to wrap.
_AUTO_TITLE_CHARS = 60


def derive_title(question: str) -> str:
    """A session title from its opening question.

    Collapses whitespace and truncates on a word boundary where possible, so the
    switcher shows "Syarat pendaftaran merchant" rather than a clipped fragment.
    """
    cleaned = " ".join(question.split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= _AUTO_TITLE_CHARS:
        return cleaned[:TITLE_MAX_CHARS]
    head = cleaned[:_AUTO_TITLE_CHARS]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return f"{cut}…"[:TITLE_MAX_CHARS]


class ChatService:
    def __init__(self, *, repo: ChatRepository, project_repo: ProjectRepository, on_client, llm):
        self.repo = repo
        self.project_repo = project_repo
        self.on_client = on_client
        self.llm = llm
        self.sessions = ChatSessionRepository(repo.db, repo.tenant_id)

    # --- sessions ---------------------------------------------------------------

    def list_sessions(self, project_id: uuid.UUID) -> list[ChatSession]:
        self.project_repo.get(project_id)  # 404 across tenants
        return self.sessions.list_by_project(project_id)

    def create_session(
        self, project_id: uuid.UUID, *, title: str | None = None
    ) -> ChatSession:
        self.project_repo.get(project_id)
        return self.sessions.create(project_id=project_id, title=_clean_title(title))

    def rename_session(self, session_id: uuid.UUID, *, title: str) -> ChatSession:
        cleaned = _clean_title(title)
        if not cleaned:
            raise ValidationError("A session title cannot be empty.")
        session = self.sessions.get(session_id)
        session.title = cleaned
        self.repo.db.add(session)
        self.repo.db.flush()
        return session

    def archive_session(self, session_id: uuid.UUID) -> ChatSession:
        """Soft delete. Messages are untouched so `restore_session` can undo it."""
        return self.sessions.archive(self.sessions.get(session_id))

    def restore_session(self, session_id: uuid.UUID) -> ChatSession:
        return self.sessions.restore(self.sessions.get_archived(session_id))

    def resolve_session(
        self, project_id: uuid.UUID, session_id: uuid.UUID | None
    ) -> ChatSession:
        """The session a request targets, creating the project's first one on demand.

        An explicit id is validated against the tenant AND the project, so a session
        id belonging to another project cannot be used to read or write here.
        """
        if session_id is not None:
            session = self.sessions.get(session_id)
            if session.project_id != project_id:
                raise ValidationError("That chat session belongs to another project.")
            return session
        existing = self.sessions.latest_for_project(project_id)
        return existing or self.sessions.create(project_id=project_id)

    # --- messages ---------------------------------------------------------------

    def list_messages(
        self,
        project_id: uuid.UUID,
        *,
        session_id: uuid.UUID | None = None,
        limit: int = DEFAULT_MESSAGE_LIMIT,
        before: datetime | None = None,
    ) -> list[ChatMessage]:
        self.project_repo.get(project_id)  # 404 across tenants
        session = self.resolve_session(project_id, session_id)
        return self.repo.list_by_session(session.id, limit=limit, before=before)

    async def ask(
        self,
        *,
        project_id: uuid.UUID,
        question: str,
        language: str | None = None,
        session_id: uuid.UUID | None = None,
    ) -> ChatMessage:
        project = self.project_repo.get(project_id)
        session = self.resolve_session(project_id, session_id)
        language = language or get_settings().default_language
        provider_config = TenantLlmConfigService(self.repo.db, self.repo.tenant_id).get_config()

        # Scope retrieval to this project's own sources -- the engine index is shared.
        snippets = []
        if project.on_notebook_id:
            allowed = SourceRepository(
                self.repo.db, self.repo.tenant_id
            ).engine_source_refs(project_id)
            snippets = await self.on_client.search(
                allowed_source_refs=allowed, query=question
            )
        grounding = _grounding_text(snippets)
        history = _recent_history(self.repo.list_by_session(session.id))

        answer = await self.llm.chat(
            system=(
                "You answer questions strictly from the provided source excerpts. "
                "If the answer is not in the sources, say you don't have enough "
                "information. Be concise and cite facts to the sources. "
                f"Respond in {language}."
            ),
            user=(
                f"Source excerpts:\n{grounding or '(no relevant excerpts found)'}\n\n"
                f"Question: {question}"
            ),
            provider_config=provider_config,
            history=history,
            temperature=0.2,
            max_tokens=get_settings().chat_llm_max_tokens,
        )

        # Name the session after its opening question, but never overwrite a title the
        # user chose -- an explicit rename has to survive the next message.
        if not session.title:
            session.title = derive_title(question)

        # Persist the user turn, then the assistant turn with citations.
        self.repo.add(
            ChatMessage(
                project_id=project.id,
                session_id=session.id,
                role=ChatRole.user,
                content=question,
            )
        )
        assistant = ChatMessage(
            project_id=project.id,
            session_id=session.id,
            role=ChatRole.assistant,
            content=answer.text,
            citations=_citations(snippets),
            truncated=answer.truncated,
        )
        self.repo.add(assistant)
        self.sessions.touch(session)
        logger.info(
            "chat_answered",
            extra={
                "project_id": str(project_id),
                "session_id": str(session.id),
                "truncated": answer.truncated,
            },
        )
        return assistant

    async def continue_message(self, message_id: uuid.UUID) -> ChatMessage:
        """Append a continuation to a truncated assistant turn, in place.

        Re-runs grounding search against the ORIGINAL question rather than reusing the
        first answer's snippets: `history` only carries role/content pairs, so the
        source excerpts used the first time are not recoverable from the row itself,
        and re-searching is cheap and gives the continuation the same grounding
        discipline as the initial answer.
        """
        message = self.repo.get(message_id)  # 404 across tenants
        if message.role is not ChatRole.assistant:
            raise ValidationError("Only an assistant message can be continued.")
        if not message.truncated:
            raise ValidationError("This message was not truncated.")

        question = self.repo.preceding_user_question(message)
        if question is None:
            # Should not happen (ask() always persists the pairing), but this is a
            # public endpoint keyed by id, so it is handled rather than asserted.
            raise NotFoundError("Could not find the question this answer belongs to.")

        project = self.project_repo.get(message.project_id)
        language = get_settings().default_language
        provider_config = TenantLlmConfigService(self.repo.db, self.repo.tenant_id).get_config()

        snippets: list[dict] = []
        if project.on_notebook_id:
            allowed = SourceRepository(
                self.repo.db, self.repo.tenant_id
            ).engine_source_refs(project.id)
            snippets = await self.on_client.search(allowed_source_refs=allowed, query=question)
        grounding = _grounding_text(snippets)

        answer = await self.llm.chat(
            system=(
                "You are continuing your own previous answer, which was cut off by a "
                "length limit before it was finished. Continue EXACTLY where it left "
                "off. Do not repeat anything already said, do not restart with a "
                "greeting or a summary of what came before, and do not re-answer the "
                "question from scratch -- pick up the sentence or list where it stops. "
                "Answer strictly from the provided source excerpts. "
                f"Respond in {language}."
            ),
            user=(
                f"Original question: {question}\n\n"
                f"Source excerpts:\n{grounding or '(no relevant excerpts found)'}\n\n"
                f"Your answer so far (continue from exactly here, do not repeat it):\n"
                f"{message.content}"
            ),
            provider_config=provider_config,
            temperature=0.2,
            max_tokens=get_settings().chat_llm_max_tokens,
        )

        # A plain concatenation: the cut usually falls on a token boundary the model
        # continues cleanly from, and a single joining space is the safe default when
        # it doesn't. Reconstructing the exact boundary is not worth the complexity.
        message.content = f"{message.content} {answer.text}".strip()
        message.citations = _merge_citations(message.citations, _citations(snippets))
        message.truncated = answer.truncated
        self.repo.db.add(message)
        self.repo.db.flush()
        self.sessions.touch(self.sessions.get(message.session_id))
        logger.info(
            "chat_continued",
            extra={
                "message_id": str(message_id),
                "still_truncated": answer.truncated,
            },
        )
        return message


def _clean_title(title: str | None) -> str | None:
    if title is None:
        return None
    collapsed = " ".join(title.split()).strip()
    return collapsed[:TITLE_MAX_CHARS] or None


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


def _merge_citations(existing: list[Any], new: list[dict]) -> list[dict]:
    """Union by (source_ref, snippet), existing first — a continuation adds to the
    trail rather than replacing it."""
    seen = {(c.get("source_ref"), c.get("snippet")) for c in existing if isinstance(c, dict)}
    merged = [c for c in existing if isinstance(c, dict)]
    for c in new:
        key = (c.get("source_ref"), c.get("snippet"))
        if key not in seen:
            seen.add(key)
            merged.append(c)
    return merged


def _recent_history(messages: list[ChatMessage]) -> list[dict[str, str]]:
    recent = messages[-_HISTORY_TURNS:]
    return [{"role": m.role.value, "content": m.content} for m in recent]
