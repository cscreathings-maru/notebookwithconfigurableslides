"""Open Notebook (analysis engine) client.

Implements the ingest/analyze surface the orchestrator depends on, pinned to a
specific API version and covered by contract tests. Resilience (timeout, retry,
circuit breaker) is inherited from EngineClient. The engine runs on a private
network; only this backend holds its URL. Per the engine contract, the tenant's
BYOK provider config is passed per call, not as a global key. Engine ids returned
here stay server-side.
"""

from __future__ import annotations

from typing import Any

from ..core.config import get_settings
from ..core.errors import EngineError
from .base import EngineClient

# Pinned upstream API version. Bumping this is a deliberate, contract-tested change.
OPEN_NOTEBOOK_API_VERSION = "v1"
_API = f"/api/{OPEN_NOTEBOOK_API_VERSION}"


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
            "POST", f"{_API}/notebooks", json={"name": name, "namespace": namespace}
        )
        return self._field(resp.json(), "id")

    async def add_source(
        self,
        *,
        notebook_id: str,
        uri: str,
        provider_config: dict[str, Any],
    ) -> str:
        """Add a file/URL source (engine fetches `uri`); returns on_source_id."""
        resp = await self.request(
            "POST",
            f"{_API}/notebooks/{notebook_id}/sources",
            json={"uri": uri, "provider": provider_config},
        )
        return self._field(resp.json(), "id")

    async def get_source_status(self, *, source_id: str) -> str:
        """Poll a source; returns queued/processing/ready/failed."""
        resp = await self.request("GET", f"{_API}/sources/{source_id}")
        return self._field(resp.json(), "status")

    async def run_transformation(
        self,
        *,
        source_id: str,
        provider_config: dict[str, Any],
    ) -> str:
        """Run a summary/insight transformation; returns analysis_ref."""
        resp = await self.request(
            "POST",
            f"{_API}/sources/{source_id}/transformations",
            json={"type": "summarize", "provider": provider_config},
        )
        body = resp.json()
        # Prefer an explicit analysis pointer; fall back to the resource id.
        return body.get("analysis_ref") or self._field(body, "id")

    async def search(self, *, notebook_id: str, query: str) -> list[dict[str, Any]]:
        """Context query for outline building; returns grounded snippets."""
        resp = await self.request(
            "POST",
            f"{_API}/notebooks/{notebook_id}/search",
            json={"query": query},
        )
        body = resp.json()
        results = body.get("results", body if isinstance(body, list) else [])
        return [r for r in results if isinstance(r, dict)]

    @staticmethod
    def _field(body: dict[str, Any], key: str) -> str:
        value = body.get(key)
        if not isinstance(value, str) or not value:
            raise EngineError(f"Open Notebook response missing '{key}'.")
        return value
