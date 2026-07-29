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

_PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


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

    @classmethod
    def without_source(cls) -> TemplateRegistration:
        """No PPTX was uploaded, so there is nothing for the engine to derive a brand from.

        Distinct from an engine failure: nothing went wrong, the template simply cannot
        carry branding. Recorded as `fallback` so the UI still warns that decks will
        render with the stock theme.
        """
        return cls(
            ref=_STOCK_TEMPLATE_REF,
            status=RegistrationStatus.fallback,
            error=(
                "No base PPTX uploaded. The slide engine derives colours, fonts and "
                "layouts from the uploaded deck — brand tokens alone cannot style a "
                "presentation. Upload a branded .pptx to apply this template."
            ),
        )


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
        pptx_bytes: bytes | None = None,
        pptx_filename: str | None = None,
    ) -> TemplateRegistration:
        """Register a branded template with the engine, in the two steps it requires.

        **The uploaded PPTX *is* the brand.** `POST /templates/init` takes no colour or
        font parameters — it derives layouts, fonts and palette from the deck itself
        (`_prepare_template_source` in the engine's `template.py`). So branding reaches
        the renderer by getting the PPTX there, not by translating `brand_tokens`.

        Two steps, because `init` cannot accept a file:

        1. `POST /templates/fonts-upload-and-slides-preview` — multipart upload of the
           PPTX; returns `{pptx_url, slide_image_urls, fonts}`.
        2. `POST /templates/init` — JSON referencing those, returns the template id.

        The previous single-step call sent `{"name", "source_pptx_url"}`. `InitTemplateRequest`
        declares `pptx_url` and `slide_image_urls` as **required** and has no
        `source_pptx_url` field, so every call failed validation with a 422, took the
        `>= 400` branch, and fell back to the stock theme. That is why configured
        branding never appeared on a deck.

        Still never hard-fails template creation — but the outcome is recorded, so a
        degraded template is distinguishable from a healthy one (T-1.6).
        """
        if not pptx_bytes:
            # Nothing to derive a brand from. Colour pickers alone cannot brand a deck:
            # the engine has no parameter for them. Recorded, not silently "default".
            return TemplateRegistration.without_source()

        try:
            preview = await self.request(
                "POST",
                "/api/v1/ppt/templates/fonts-upload-and-slides-preview",
                files={
                    "pptx_file": (
                        pptx_filename or "template.pptx",
                        pptx_bytes,
                        _PPTX_MEDIA_TYPE,
                    )
                },
            )
            if preview.status_code >= 400:
                detail = f"preview step returned {preview.status_code}: {preview.text[:200]}"
                logger.warning("presenton_template_preview_rejected", extra={"detail": detail})
                return TemplateRegistration.fallen_back(detail)

            body = preview.json()
            pptx_url = body.get("pptx_url")
            slide_image_urls = body.get("slide_image_urls") or []
            if not pptx_url:
                detail = "preview step returned no pptx_url"
                logger.warning("presenton_template_preview_incomplete", extra={"name": name})
                return TemplateRegistration.fallen_back(detail)

            resp = await self.request(
                "POST",
                "/api/v1/ppt/templates/init",
                json={
                    "pptx_url": pptx_url,
                    "slide_image_urls": slide_image_urls,
                    "fonts": body.get("fonts") or {},
                    "name": name,
                },
            )
            if resp.status_code >= 400:
                detail = f"init returned {resp.status_code}: {resp.text[:200]}"
                logger.warning(
                    "presenton_template_init_rejected",
                    extra={"status_code": resp.status_code, "detail": detail},
                )
                return TemplateRegistration.fallen_back(detail)

            # `init` is declared `response_model=str`, so the body is a bare id string,
            # not an object. Tolerate both shapes rather than assuming.
            parsed = resp.json()
            ref = parsed if isinstance(parsed, str) else self._first(
                parsed, "template_id", "id", "template"
            )
            if not ref:
                detail = "engine accepted the template but returned no template ref"
                logger.warning("presenton_template_init_no_ref", extra={"name": name})
                return TemplateRegistration.fallen_back(detail)
            return TemplateRegistration(
                ref=str(ref), status=RegistrationStatus.registered, error=None
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
