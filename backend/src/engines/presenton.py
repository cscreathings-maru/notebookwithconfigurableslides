"""Presenton (generation engine) client — STUB.

Typed method surface only; param mapping and generation land in Slice 3. HTTP Basic
auth (single admin account) is engine-internal defense-in-depth, NOT a tenant
boundary — isolation is enforced in the orchestrator. Resilience is inherited from
EngineClient. Engine ids (presentation_id, edit_path) stay server-side.
"""

from __future__ import annotations

from typing import Any

from ..core.config import get_settings
from .base import EngineClient


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
        """Liveness probe — the one method wired through the real transport."""
        response = await self.request("GET", "/health")
        return response.status_code == 200

    async def upload_files(self, *, file_paths: list[str]) -> list[str]:
        """POST /api/v1/ppt/files/upload; returns engine file refs."""
        resp = await self.request(
            "POST", "/api/v1/ppt/files/upload", json={"files": file_paths}
        )
        body = resp.json()
        return list(body.get("file_refs", []))

    async def generate(self, *, params: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/ppt/presentation/generate.

        Returns {presentation_id, path, edit_path}. The orchestrator pulls the file
        from `path`; `edit_path` is internal-only and never surfaced to clients.
        """
        resp = await self.request(
            "POST", "/api/v1/ppt/presentation/generate", json=params
        )
        return resp.json()

    async def export(self, *, presentation_id: str, target_format: str) -> dict[str, Any]:
        """Export an existing presentation to another format (e.g. pdf); returns {path}."""
        resp = await self.request(
            "POST",
            "/api/v1/ppt/presentation/export",
            json={"presentation_id": presentation_id, "export_as": target_format},
        )
        return resp.json()

    async def download(self, *, path: str) -> bytes:
        """Fetch the produced artifact bytes from the engine-returned path."""
        resp = await self.request("GET", path)
        return resp.content

    async def register_template(
        self,
        *,
        name: str,
        source_pptx_path: str | None = None,
    ) -> str:
        """Register/import a tenant-namespaced template; returns presenton_template_ref.

        With `source_pptx_path` the engine imports/generates a template from the PPTX
        (fetched via the presigned URL); otherwise it registers a named template. The
        returned ref is stored server-side and never exposed to clients.
        """
        payload: dict[str, Any] = {"name": name}
        if source_pptx_path is not None:
            payload["source_pptx_url"] = source_pptx_path
        resp = await self.request(
            "POST", "/api/v1/ppt/template/import", json=payload
        )
        body = resp.json()
        ref = body.get("template_id") or body.get("id") or body.get("template")
        if not isinstance(ref, str) or not ref:
            from ..core.errors import EngineError

            raise EngineError("Presenton template import returned no template ref.")
        return ref
