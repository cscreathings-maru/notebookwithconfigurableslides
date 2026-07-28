"""Presenton (generation engine) client.

Issues real requests through EngineClient (timeout, retry on 5xx/429, breaker).
HTTP Basic auth (admin user/pass, same as the web UI) is engine-internal
defense-in-depth, not a tenant boundary. Response shapes are parsed defensively
(cloud returns absolute URLs; self-hosted returns relative paths like /app_data/…,
resolved against base_url) and non-2xx raises a clear EngineError. Engine ids/paths
stay server-side.

Matches the self-hosted contract: POST /api/v1/ppt/presentation/generate returns
one file in the requested export_as (pptx|pdf) — there is no separate export
endpoint, so callers pick the format up front.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from ..models import RegistrationStatus
from .base import EngineClient

logger = get_logger("orchestrator.presenton")

# Engine ref used when registration did not yield a usable template.
_STOCK_TEMPLATE_REF = "default"


@dataclass(frozen=True)
class TemplateRegistration:
    """Outcome of a template registration attempt.

    Carries the reason alongside the ref so a fallback stays visible all the way to
    the UI instead of being flattened into an indistinguishable "default".
    """

    ref: str
    status: RegistrationStatus
    error: str | None

    @classmethod
    def fallen_back(cls, error: str) -> TemplateRegistration:
        return cls(ref=_STOCK_TEMPLATE_REF, status=RegistrationStatus.fallback, error=error)


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
    ) -> TemplateRegistration:
        """Register/import a template with the engine.

        Still falls back to the stock theme rather than failing template creation, but
        reports *which* happened. Returning a bare "default" made a degraded template
        indistinguishable from a healthy one, so a user whose branding silently never
        applied had nothing to look at.
        """
        payload: dict[str, Any] = {"name": name}
        if source_pptx_path is not None:
            payload["source_pptx_url"] = source_pptx_path
        try:
            resp = await self.request("POST", "/api/v1/ppt/templates/init", json=payload)
            if resp.status_code >= 400:
                detail = f"engine returned {resp.status_code}: {resp.text[:200]}"
                logger.warning(
                    "presenton_template_init_rejected",
                    extra={"status_code": resp.status_code, "detail": detail},
                )
                return TemplateRegistration.fallen_back(detail)
            ref = self._first(resp.json(), "template_id", "id", "template")
            if not ref:
                detail = "engine accepted the template but returned no template ref"
                logger.warning("presenton_template_init_no_ref", extra={"name": name})
                return TemplateRegistration.fallen_back(detail)
            return TemplateRegistration(
                ref=ref, status=RegistrationStatus.registered, error=None
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            logger.warning("presenton_template_init_unreachable", extra={"error": detail})
            return TemplateRegistration.fallen_back(detail)

    @staticmethod
    def _ensure_ok(resp: Any, op: str) -> None:
        if resp.status_code >= 400:
            snippet = getattr(resp, "text", "")[:200]
            if resp.status_code == 401:
                raise EngineError(f"Presenton {op} failed (401 Unauthorized - verify PRESENTON_AUTH_USERNAME and PASSWORD): {snippet}")
            raise EngineError(f"Presenton {op} failed ({resp.status_code}): {snippet}")

    @staticmethod
    def _first(body: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
        raise EngineError(f"Presenton response missing any of {keys}.")
