"""Presenton (generation engine) client.

Issues real requests through EngineClient (timeout, retry on 5xx/429, breaker).
HTTP Basic auth is engine-internal defense-in-depth, not a tenant boundary. Response
shapes are parsed defensively (Presenton versions vary on id/path key names) and
non-2xx raises a clear EngineError with a body snippet. Engine ids/paths stay
server-side. NOTE: the exact /api/v1/ppt/* contract should be verified against the
running image's /openapi.json (Phase 0) — mismatches surface as EngineError here.
"""

from __future__ import annotations

from typing import Any

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from .base import EngineClient

logger = get_logger("orchestrator.presenton")


class PresentonClient(EngineClient):
    def __init__(self, **kwargs: Any):
        settings = get_settings()
        super().__init__(
            name="presenton",
            base_url=settings.presenton_url,
            auth=(settings.presenton_auth_username, settings.presenton_auth_password),
            **kwargs,
        )

    async def health(self) -> bool:
        """Liveness probe."""
        response = await self.request("GET", "/health")
        return response.status_code == 200

    async def generate(self, *, params: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/ppt/presentation/generate → {presentation_id, path}."""
        resp = await self.request(
            "POST", "/api/v1/ppt/presentation/generate", json=params
        )
        self._ensure_ok(resp, "generate")
        body = resp.json()
        return {
            "presentation_id": self._first(body, "presentation_id", "id", "presentationId"),
            "path": self._first(body, "path", "url", "download_url", "file_url"),
        }

    async def export(self, *, presentation_id: str, target_format: str) -> dict[str, Any]:
        """Export an existing presentation to another format; returns {path}."""
        resp = await self.request(
            "POST",
            "/api/v1/ppt/presentation/export",
            json={"presentation_id": presentation_id, "export_as": target_format},
        )
        self._ensure_ok(resp, "export")
        body = resp.json()
        return {"path": self._first(body, "path", "url", "download_url", "file_url")}

    async def download(self, *, path: str) -> bytes:
        """Fetch the produced artifact bytes from the engine-returned path."""
        resp = await self.request("GET", path)
        self._ensure_ok(resp, "download")
        return resp.content

    async def register_template(
        self,
        *,
        name: str,
        source_pptx_path: str | None = None,
    ) -> str:
        """Register/import a template; returns presenton_template_ref (server-side)."""
        payload: dict[str, Any] = {"name": name}
        if source_pptx_path is not None:
            payload["source_pptx_url"] = source_pptx_path
        resp = await self.request("POST", "/api/v1/ppt/template/import", json=payload)
        self._ensure_ok(resp, "register_template")
        body = resp.json()
        ref = self._first(body, "template_id", "id", "template")
        if not ref:
            raise EngineError("Presenton template import returned no template ref.")
        return ref

    @staticmethod
    def _ensure_ok(resp: Any, op: str) -> None:
        if resp.status_code >= 400:
            snippet = getattr(resp, "text", "")[:200]
            raise EngineError(f"Presenton {op} failed ({resp.status_code}): {snippet}")

    @staticmethod
    def _first(body: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
        raise EngineError(f"Presenton response missing any of {keys}.")
