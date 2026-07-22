"""Open Notebook (analysis engine) client — targets the real /api REST surface.

This Open Notebook build manages its own models/credentials, so the per-call
`provider_config` is accepted for interface compatibility but NOT forwarded;
configure the embedding model inside Open Notebook (see deploy docs). The demo
pipeline only needs create-notebook, add-source and status polling. Grounding for
the outline comes from search (best-effort — never fatal). The transformation step
is intentionally a no-op: the outline builder never consumes analysis_ref.
"""

from __future__ import annotations

from typing import Any

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from .base import EngineClient

logger = get_logger("orchestrator.open_notebook")

_API = "/api"

# Open Notebook status strings normalized to the orchestrator's three-state model
# (ready / failed / processing). Unrecognized values are treated as processing,
# with the source's `embedded` flag as the authoritative fallback ready signal.
_READY_STATES = {
    "completed", "complete", "done", "ready", "success", "succeeded",
    "finished", "processed", "indexed", "embedded",
}
_FAILED_STATES = {"failed", "error", "errored", "failure", "cancelled", "canceled"}


class OpenNotebookClient(EngineClient):
    def __init__(self, **kwargs: Any):
        super().__init__(
            name="open-notebook",
            base_url=get_settings().open_notebook_url,
            **kwargs,
        )

    async def health(self) -> bool:
        """Liveness probe."""
        response = await self.request("GET", "/health")
        return response.status_code == 200

    async def create_notebook(self, *, name: str, namespace: str) -> str:
        """Create one notebook per project; returns on_notebook_id."""
        resp = await self.request(
            "POST",
            f"{_API}/notebooks",
            json={"name": name, "description": f"Orchestrator project ({namespace})"},
        )
        self._ensure_ok(resp, "create_notebook")
        return self._field(resp.json(), "id")

    async def add_source(
        self,
        *,
        notebook_id: str,
        uri: str,
        provider_config: dict[str, Any],
    ) -> str:
        """Add a fetchable source (public URL or presigned object URL) and embed it.

        `provider_config` is unused: Open Notebook embeds with its own configured
        model. `uri` is always something Open Notebook can GET, so type is "link".
        """
        resp = await self.request(
            "POST",
            f"{_API}/sources/json",
            json={
                "notebooks": [notebook_id],
                "type": "link",
                "url": uri,
                "embed": True,
                "async_processing": True,
            },
        )
        self._ensure_ok(resp, "add_source")
        return self._field(resp.json(), "id")

    async def get_source_status(self, *, source_id: str) -> str:
        """Poll a source; returns normalized queued/processing/ready/failed."""
        resp = await self.request("GET", f"{_API}/sources/{source_id}/status")
        self._ensure_ok(resp, "get_source_status")
        body = resp.json()
        raw = (body.get("status") or "").strip().lower()
        logger.info(
            "on_source_status",
            extra={"source_id": source_id, "raw_status": raw or "(none)"},
        )
        if raw in _FAILED_STATES:
            return "failed"
        if raw in _READY_STATES:
            return "ready"
        # Command status is ambiguous/empty — the source's embed flag is the
        # authoritative "done" signal for our purposes.
        if await self._is_embedded(source_id):
            return "ready"
        return "processing"

    async def _is_embedded(self, source_id: str) -> bool:
        """True once Open Notebook has embedded the source (best-effort signal)."""
        try:
            resp = await self.request("GET", f"{_API}/sources/{source_id}")
            if resp.status_code >= 400:
                return False
            return bool(resp.json().get("embedded"))
        except Exception:  # pragma: no cover - best-effort only
            return False

    async def run_transformation(
        self,
        *,
        source_id: str,
        provider_config: dict[str, Any],
    ) -> str:
        """No-op analysis step.

        The outline builder never reads analysis_ref, and this Open Notebook's
        transformation API needs a preconfigured transformation + chat model the
        lite demo does not provision. Return a stable ref so the caller can store it.
        """
        return source_id

    async def search(self, *, notebook_id: str, query: str) -> list[dict[str, Any]]:
        """Grounding snippets for outline building — best-effort, never fatal.

        Open Notebook search is global (not notebook-scoped) and returns free-form
        result dicts; map them to the {text, source_ref} shape the builder expects.
        Any failure (e.g. no embedding model yet) degrades to no grounding.
        """
        try:
            resp = await self.request(
                "POST",
                f"{_API}/search",
                json={
                    "query": query,
                    "type": "vector",
                    "limit": 10,
                    "search_sources": True,
                    "search_notes": False,
                    "minimum_score": 0.0,
                },
            )
            if resp.status_code >= 400:
                logger.warning("on_search_failed", extra={"status": resp.status_code})
                return []
            results = resp.json().get("results", [])
        except Exception as exc:  # pragma: no cover - best-effort only
            logger.warning("on_search_error", extra={"error": str(exc)})
            return []

        mapped: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            text = (
                item.get("content")
                or item.get("text")
                or item.get("full_text")
                or item.get("chunk")
                or ""
            )
            ref = item.get("source_id") or item.get("id") or item.get("source_ref")
            if text:
                mapped.append({"text": str(text), "source_ref": ref})
        return mapped

    @staticmethod
    def _ensure_ok(resp: Any, op: str) -> None:
        """Raise a clear EngineError on a non-2xx (base.request only retries 5xx/429)."""
        if resp.status_code >= 400:
            snippet = getattr(resp, "text", "")[:200]
            raise EngineError(
                f"Open Notebook {op} failed ({resp.status_code}): {snippet}"
            )

    @staticmethod
    def _field(body: dict[str, Any], key: str) -> str:
        value = body.get(key)
        if not isinstance(value, str) or not value:
            raise EngineError(f"Open Notebook response missing '{key}'.")
        return value
