"""Open Notebook (analysis engine) client — targets the real /api REST surface.

This Open Notebook build manages its own models/credentials, so the per-call
`provider_config` is accepted for interface compatibility but NOT forwarded;
configure the embedding model inside Open Notebook (see deploy docs). The demo
pipeline only needs create-notebook, add-source and status polling. Grounding for
the outline comes from search (best-effort — never fatal). The transformation step
is intentionally a no-op: the outline builder never consumes analysis_ref.

**Files are uploaded, not linked.** `type: "link"` selects the engine's web-page
extractor; it is for articles and HTML pages. Handing it a presigned object-store
URL for a .docx/.pptx/.pdf failed within a second with `started_at: null` and
"Could not extract content from this source" — the binary never reached a document
handler. Uploads go through the multipart `POST /api/sources` with `type: "upload"`
instead, which also removes the engine's dependency on reaching the object store
and the presign-expiry race that made every retry unrecoverable.

**Search is not scoped by the engine.** See `search()` — the instance is a single
shared index, and isolation is enforced on this side of the boundary.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from .base import EngineClient

logger = get_logger("orchestrator.open_notebook")

_API = "/api"

# Grounding snippets returned to callers.
_GROUNDING_LIMIT = 10
# Post-filtering discards hits belonging to other projects, so ask the engine for more
# than we need or recall collapses on a busy shared instance. The engine caps limit at 1000.
_GROUNDING_OVER_FETCH = 6

# Engine explanations are stored on Source.error (String(1024)); keep well inside it.
_DETAIL_MAX_CHARS = 800


@dataclass(frozen=True)
class SourceProgress:
    """A source's normalized state plus the engine's own explanation of it.

    `detail` is what the engine said, verbatim. Carrying it separately from `state`
    keeps the orchestrator's three-state model intact while preserving the one piece
    of information a user actually needs when something fails.
    """

    state: str  # "ready" | "failed" | "processing"
    detail: str | None


def _status_detail(body: dict[str, Any]) -> str | None:
    """The engine's explanation, from `message` plus any `processing_info`.

    Both fields are part of `SourceStatusResponse`. `message` is always populated —
    even for legacy sources, where it says so.
    """
    parts: list[str] = []
    message = (body.get("message") or "").strip()
    if message:
        parts.append(message)

    info = body.get("processing_info")
    if isinstance(info, dict):
        # Surface the fields most likely to name a cause; keep it bounded so a large
        # payload cannot flood the column or the log.
        for key in ("error", "error_message", "detail", "reason", "exception"):
            value = str(info.get(key) or "").strip()
            if value and value not in parts:
                parts.append(value)
    elif info:
        parts.append(str(info).strip())

    joined = " | ".join(p for p in parts if p)
    return joined[:_DETAIL_MAX_CHARS] or None


def _result_text(item: dict[str, Any]) -> str:
    """The snippet text of one search hit.

    `fn::vector_search` returns the matched chunks under **`matches`** — a list of
    strings — not a scalar `content`/`text` field. Reading only the scalar names
    dropped every hit silently: the engine answered with real results, this mapper
    kept none of them, and chat produced "I don't have enough information" with empty
    citations. That is indistinguishable from an empty index, which is exactly what
    made it expensive to find. The scalar names are kept as a fallback so a future
    engine version that returns one still works.
    """
    matches = item.get("matches")
    if isinstance(matches, list):
        joined = "\n".join(str(m).strip() for m in matches if str(m).strip())
        if joined:
            return joined
    elif isinstance(matches, str) and matches.strip():
        return matches.strip()

    for key in ("content", "text", "full_text", "chunk"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _result_source_ref(item: dict[str, Any]) -> str | None:
    """The engine source id a search hit came from, or None if unresolvable.

    `parent_id` is the only field that names the *source* for both result kinds the
    engine emits: `fn::vector_search` selects `source.id as parent_id` for both
    `source_embedding` and `source_insight` rows, but aliases `id` to the insight's
    own id in the latter. Preferring `id` would fail to match a legitimate hit and
    silently drop it.
    """
    raw = item.get("parent_id") or item.get("source_id") or item.get("source_ref")
    if raw is None:
        return None
    return str(raw).strip() or None

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

    async def add_source_file(
        self,
        *,
        notebook_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload file bytes and embed them; returns on_source_id.

        The multipart form is the engine's own upload surface: `notebooks` is a JSON
        array *string* and the booleans are the strings "true"/"false", because every
        field arrives as form data. Sending the file itself is what lets the engine
        pick a document handler — the link path never could, whatever Content-Type
        the object store served (see module docstring).
        """
        resp = await self.request(
            "POST",
            f"{_API}/sources",
            data={
                "type": "upload",
                "notebooks": json.dumps([notebook_id]),
                "title": filename,
                "embed": "true",
                "async_processing": "true",
            },
            files={"file": (filename, content, content_type)},
        )
        self._ensure_ok(resp, "add_source_file")
        return self._field(resp.json(), "id")

    async def add_source_link(self, *, notebook_id: str, url: str) -> str:
        """Add a real web URL (article/page) and embed it; returns on_source_id.

        Only for user-supplied web links. Never for object-store URLs — see
        `add_source_file`.
        """
        resp = await self.request(
            "POST",
            f"{_API}/sources/json",
            json={
                "notebooks": [notebook_id],
                "type": "link",
                "url": url,
                "embed": True,
                "async_processing": True,
            },
        )
        self._ensure_ok(resp, "add_source_link")
        return self._field(resp.json(), "id")

    async def get_source_status(self, *, source_id: str) -> SourceProgress:
        """Poll a source; returns the normalized state **and the engine's own reason**.

        `SourceStatusResponse` declares `message` as required and `processing_info` as
        optional detail. Both were previously discarded, so a source that failed inside
        the engine surfaced to the user as "Analysis failed for this source." — a string
        this codebase wrote, carrying nothing the engine had said.

        That is the same concealment as template registration returning `"default"`
        (T-1.6) and the LLM collapsing every error into one message (T-2.3): a real,
        specific cause replaced by a plausible generic one.
        """
        resp = await self.request("GET", f"{_API}/sources/{source_id}/status")
        self._ensure_ok(resp, "get_source_status")
        body = resp.json()
        raw = (body.get("status") or "").strip().lower()
        detail = _status_detail(body)
        logger.info(
            "on_source_status",
            extra={
                "source_id": source_id,
                "raw_status": raw or "(none)",
                "engine_message": detail or "(none)",
            },
        )
        if raw in _FAILED_STATES:
            return SourceProgress(state="failed", detail=detail)
        if raw in _READY_STATES:
            return SourceProgress(state="ready", detail=detail)
        # Command status is ambiguous/empty — the source's embed flag is the
        # authoritative "done" signal for our purposes.
        if await self._is_embedded(source_id):
            return SourceProgress(state="ready", detail=detail)
        return SourceProgress(state="processing", detail=detail)

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

    async def search(
        self, *, allowed_source_refs: Collection[str], query: str
    ) -> list[dict[str, Any]]:
        """Grounding snippets restricted to the caller's own sources.

        Open Notebook's `POST /api/search` accepts no notebook filter: `fn::vector_search`
        and `fn::text_search` scan every embedding in the instance, so one shared engine
        serves every project of every tenant. Scoping is therefore enforced here, against
        the engine source ids recorded on the caller's own tenant-scoped Postgres rows --
        not against anything the engine reports about itself.

        **Fails closed.** An empty allow-set, or a result whose source cannot be resolved,
        yields no grounding rather than unscoped grounding: an empty guide is a visible,
        recoverable bug, while a guide grounded in another tenant's documents is a breach.

        Availability failures (no embedding model yet, engine down) still degrade to no
        grounding -- that best-effort posture is correct and unchanged.
        """
        allowed = {str(ref).strip() for ref in allowed_source_refs if str(ref).strip()}
        if not allowed:
            logger.warning("on_search_skipped_unscoped")
            return []

        try:
            resp = await self.request(
                "POST",
                f"{_API}/search",
                json={
                    "query": query,
                    "type": "vector",
                    "limit": _GROUNDING_LIMIT * _GROUNDING_OVER_FETCH,
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
        dropped = 0
        for item in results:
            if not isinstance(item, dict):
                continue
            text = _result_text(item)
            if not text:
                continue
            ref = _result_source_ref(item)
            if ref is None or ref not in allowed:
                dropped += 1
                continue
            mapped.append({"text": str(text), "source_ref": ref})
            if len(mapped) >= _GROUNDING_LIMIT:
                break

        if dropped:
            # Expected on a shared instance; a sudden drop to zero kept means the id
            # formats have diverged, which fails closed and shows up as empty grounding.
            logger.info(
                "on_search_filtered",
                extra={"kept": len(mapped), "dropped": dropped},
            )
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
