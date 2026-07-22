"""Guide service: generate a project's overview (summary + suggested questions).

RAG in the orchestrator: pull grounding snippets from Open Notebook search, then use
the resolved LLM (OpenRouter in lite mode) to write a summary and a handful of
starter questions. Reuses the proven search() + LlmClient path rather than an
unverified Open Notebook summarize endpoint. Upserts the single per-project guide.
"""

from __future__ import annotations

import json
import uuid

from ..core.errors import ValidationError
from ..core.logging import get_logger
from ..ingestion.repository import ProjectRepository
from ..models import GuideStatus, NotebookGuide
from ..tenancy.llm_config import TenantLlmConfigService
from .repository import GuideRepository

logger = get_logger("orchestrator.guide")

_SUGGESTED_COUNT = 5


class GuideService:
    def __init__(self, *, repo: GuideRepository, project_repo: ProjectRepository, on_client, llm):
        self.repo = repo
        self.project_repo = project_repo
        self.on_client = on_client
        self.llm = llm

    def get(self, project_id: uuid.UUID) -> NotebookGuide | None:
        self.project_repo.get(project_id)  # 404 across tenants
        return self.repo.get_by_project(project_id)

    async def generate(self, *, project_id: uuid.UUID) -> NotebookGuide:
        project = self.project_repo.get(project_id)
        if not project.on_notebook_id:
            raise ValidationError("Project has no notebook yet.")

        provider_config = TenantLlmConfigService(self.repo.db, self.repo.tenant_id).get_config()

        snippets = await self.on_client.search(
            notebook_id=project.on_notebook_id,
            query="overview, key topics, main findings, and important facts",
        )
        grounding = _grounding_text(snippets)
        if not grounding:
            raise ValidationError(
                "No indexed source content yet; upload a source and wait for it to be ready."
            )

        summary = (
            await self.llm.chat(
                system=(
                    "You are a research assistant. Write a clear, well-structured overview "
                    "(3-6 short paragraphs) of the provided source material. Ground every "
                    "claim in the material; do not invent facts."
                ),
                user=f"Source excerpts:\n{grounding}\n\nWrite the overview.",
                provider_config=provider_config,
                temperature=0.3,
                max_tokens=900,
            )
        ).text

        questions = await self._suggested_questions(grounding, provider_config)

        guide = self.repo.get_by_project(project_id)
        if guide is None:
            guide = NotebookGuide(project_id=project.id, status=GuideStatus.pending)
            self.repo.add(guide)
        guide.summary = summary
        guide.suggested_questions = questions
        guide.status = GuideStatus.ready
        guide.error = None
        self.repo.db.add(guide)
        self.repo.db.flush()
        logger.info("guide_generated", extra={"project_id": str(project_id)})
        return guide

    async def _suggested_questions(self, grounding: str, provider_config: dict) -> list[str]:
        answer = await self.llm.chat(
            system=(
                "You suggest starter questions a reader could ask about the sources. "
                f"Return STRICT JSON: an array of exactly {_SUGGESTED_COUNT} short question "
                'strings, e.g. ["...", "..."]. No prose, JSON only.'
            ),
            user=f"Source excerpts:\n{grounding}\n\nReturn the JSON array of questions.",
            provider_config=provider_config,
            temperature=0.4,
            max_tokens=400,
        )
        return _parse_questions(answer.text)


def _grounding_text(snippets: list[dict]) -> str:
    return "\n".join(f"- {s.get('text', '')}" for s in snippets if s.get("text")).strip()


def _parse_questions(text: str) -> list[str]:
    """Best-effort parse of the model's JSON question array."""
    try:
        start, end = text.index("["), text.rindex("]") + 1
        data = json.loads(text[start:end])
        return [str(q).strip() for q in data if str(q).strip()][:_SUGGESTED_COUNT]
    except (ValueError, json.JSONDecodeError):
        # Fallback: split lines, strip bullets/numbering.
        lines = [ln.strip("-*0123456789. ").strip() for ln in text.splitlines()]
        return [ln for ln in lines if ln.endswith("?")][:_SUGGESTED_COUNT]
