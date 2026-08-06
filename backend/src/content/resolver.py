"""Resolve one of the four freeform content sources to plain text.

Shared by freeform deck generation (`generation/freeform_service.py`) and freeform
outline drafting (`outline/service.py::build_freeform`, DG-1/DG-2) -- both offer the
exact same four choices (`summary` / `notebook` / `chat` / `custom`) and resolve them
identically; only what happens to the resolved text differs downstream.

Lives outside both `generation/` and `outline/` on purpose. `generation/service.py`
already imports from `outline/` (the governed path consumes a built Outline), so
putting this resolver in either package and importing it from the other would create
a cycle once both needed it -- which is exactly what DG-2 does.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from ..chat.repository import ChatRepository
from ..core.errors import ValidationError
from ..guide.repository import GuideRepository
from ..ingestion.repository import SourceRepository

_SYNTHESIS_QUERY = "comprehensive synthesis of all key content"


class _OnClient(Protocol):
    async def search(
        self, *, allowed_source_refs: Any, query: str
    ) -> list[dict[str, Any]]: ...


class _Llm(Protocol):
    async def chat(self, **kwargs: Any) -> Any: ...


async def resolve_freeform_content(
    *,
    project: Any,
    content_source: str,
    custom_markdown: str | None,
    chat_message_id: uuid.UUID | None,
    provider_config: dict[str, Any],
    model: str | None,
    language: str,
    guide_repo: GuideRepository,
    chat_repo: ChatRepository,
    source_repo: SourceRepository,
    on_client: _OnClient,
    llm: _Llm,
) -> str:
    """Same resolution rules `FreeformGenerationService._resolve_content` had --
    moved here unchanged so DG-1's outline drafting can reuse them verbatim."""
    if content_source == "custom":
        if not (custom_markdown or "").strip():
            raise ValidationError("custom_markdown is required for content_source=custom.")
        return custom_markdown.strip()

    if content_source == "chat":
        if chat_message_id is None:
            raise ValidationError("chat_message_id is required for content_source=chat.")
        message = chat_repo.get(chat_message_id)  # 404 across tenants
        return message.content

    if content_source == "summary":
        guide = guide_repo.get_by_project(project.id)
        if guide is None or not guide.summary:
            raise ValidationError("Generate the notebook guide first.")
        return guide.summary

    if content_source == "notebook":
        # Scope retrieval to this project's own sources -- the engine index is shared.
        snippets: list[dict[str, Any]] = []
        if project.on_notebook_id:
            allowed = source_repo.engine_source_refs(project.id)
            snippets = await on_client.search(allowed_source_refs=allowed, query=_SYNTHESIS_QUERY)
        grounding = "\n".join(
            f"- {s.get('text', '')}" for s in snippets if s.get("text")
        ).strip()
        if not grounding:
            raise ValidationError(
                "No indexed content to synthesize; upload and index sources first."
            )
        answer = await llm.chat(
            system=(
                "Synthesize the source material into a well-structured brief suitable "
                "for a slide deck. Use clear sections and concise points. "
                f"Write in {language}."
            ),
            user=grounding,
            provider_config=provider_config,
            temperature=0.3,
            max_tokens=1400,
            model_override=model,
        )
        return answer.text

    raise ValidationError("content_source must be summary, notebook, chat, or custom.")
