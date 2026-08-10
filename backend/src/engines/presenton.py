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

import asyncio
from dataclasses import dataclass, field
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

# TM-0 (2026-08-06, confirmed against the deployed engine's openapi.json): the
# task-status endpoint lives OUTSIDE /api/v1/ppt, unlike every other route this
# client calls.
_TASK_STATUS_PATH = "/api/v1/async-tasks/status/{id}"


@dataclass(frozen=True)
class TemplateRegistration:
    """Outcome of a template registration attempt.

    Carries the reason alongside the ref so a failure stays visible all the way to
    the UI instead of being flattened into an indistinguishable "default".
    """

    ref: str
    status: RegistrationStatus
    error: str | None
    # Slide preview images the engine returned at the preview step (DG-3), empty
    # when there was no successful preview to draw them from. Carried here rather
    # than fetched separately -- the engine only produces them as a side effect of
    # the same call that yields `ref`.
    slide_image_urls: list[str] = field(default_factory=list)

    @classmethod
    def rejected(cls, error: str) -> TemplateRegistration:
        return cls(ref=_STOCK_TEMPLATE_REF, status=RegistrationStatus.failed, error=error)

    @classmethod
    def without_source(cls) -> TemplateRegistration:
        """No PPTX was uploaded, so there is nothing for the engine to derive a brand from.

        Distinct from an engine failure: nothing went wrong, the template simply cannot
        carry branding. Recorded as `no_source`, not `failed` -- there is nothing to
        retry and nothing that went wrong (TM-3).
        """
        return cls(
            ref=_STOCK_TEMPLATE_REF,
            status=RegistrationStatus.no_source,
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
        """Register a branded template with the engine (TM-1).

        **The uploaded PPTX *is* the brand.** Neither engine call in this method
        takes colour or font parameters — the engine derives layouts, fonts and
        palette from the deck itself. So branding reaches the renderer by getting
        the PPTX there, not by translating `brand_tokens`.

        Three steps:

        1. `POST /template/fonts-upload-and-slides-preview` — multipart upload of
           the PPTX; returns `{pptx_url, slide_image_urls, fonts, modified_pptx_url}`.
        2. `POST /template/async` — `CreateTemplateRequest` referencing those,
           returns an `AsyncTaskModel` (a task to poll, not a finished template —
           layout generation for every slide runs in parallel on the engine side
           and can take minutes).
        3. Poll `GET /async-tasks/status/{id}` to a terminal state: `error` non-null
           is a rejection, `data` non-null is the finished template (its id is
           inside `data`, key unconfirmed by TM-0's schema dump since `data` is a
           free-form object -- tolerated the same way `_first` already tolerates
           varying response shapes elsewhere in this client).

        **History.** The path this replaces called `/templates/...` (plural); the
        engine serves `/template/...` (singular) — confirmed 2026-08-06 against
        the live engine (`404` plural, `422` singular). Every registration ever
        attempted took the `>= 400` branch and silently fell back to the stock
        theme. Before that, an even earlier version sent a request body the engine
        rejected with a plain 422 (T-1.3). Same failure shape, three different
        root causes — which is exactly why the outcome is always recorded here
        rather than assumed, so the next one is diagnosable in minutes, not days.

        Still never hard-fails template creation — but the outcome is recorded, so
        a degraded template is distinguishable from a healthy one (T-1.6).
        """
        if not pptx_bytes:
            # Nothing to derive a brand from. Colour pickers alone cannot brand a deck:
            # the engine has no parameter for them. Recorded, not silently "default".
            return TemplateRegistration.without_source()

        try:
            preview = await self.request(
                "POST",
                "/api/v1/ppt/template/fonts-upload-and-slides-preview",
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
                return TemplateRegistration.rejected(detail)

            body = preview.json()
            pptx_url = body.get("pptx_url")
            slide_image_urls = body.get("slide_image_urls") or []
            if not pptx_url:
                detail = "preview step returned no pptx_url"
                logger.warning("presenton_template_preview_incomplete", extra={"name": name})
                return TemplateRegistration.rejected(detail)

            create = await self.request(
                "POST",
                "/api/v1/ppt/template/async",
                json={
                    "pptx_url": pptx_url,
                    "slide_image_urls": slide_image_urls,
                    "fonts": body.get("fonts") or {},
                    "name": name,
                },
            )
            if create.status_code >= 400:
                detail = f"async create returned {create.status_code}: {create.text[:200]}"
                logger.warning(
                    "presenton_template_create_rejected",
                    extra={"status_code": create.status_code, "detail": detail},
                )
                return TemplateRegistration.rejected(detail)

            task = create.json()
            task_id = task.get("id")
            if not task_id:
                detail = "engine accepted the template but returned no task id"
                logger.warning("presenton_template_create_no_task_id", extra={"name": name})
                return TemplateRegistration.rejected(detail)

            final = await self._poll_task(task_id)
            if final.get("error"):
                detail = f"template creation failed: {final['error']}"
                logger.warning(
                    "presenton_template_task_failed", extra={"task_id": task_id, "detail": detail}
                )
                return TemplateRegistration.rejected(detail)

            data = final.get("data") or {}
            try:
                ref = self._first(data, "template_id", "id", "template")
            except EngineError:
                detail = "engine finished registration but returned no template ref"
                logger.warning("presenton_template_task_no_ref", extra={"task_id": task_id})
                return TemplateRegistration.rejected(detail)

            return TemplateRegistration(
                ref=str(ref),
                status=RegistrationStatus.registered,
                error=None,
                slide_image_urls=[str(u) for u in slide_image_urls if u],
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            logger.warning("presenton_template_registration_unreachable", extra={"error": detail})
            return TemplateRegistration.rejected(detail)

    async def _poll_task(self, task_id: str) -> dict[str, Any]:
        """Poll an engine async task to a terminal state.

        Terminal is defined by `error` or `data` being non-null, not by matching a
        specific `status` string -- `AsyncTaskStatus`'s own enum values were not
        part of TM-0's confirmed contract, while `error`/`data` are: both are
        plain, always-present-in-the-schema fields on `AsyncTaskModel`.
        """
        settings = get_settings()
        path = _TASK_STATUS_PATH.format(id=task_id)
        for _ in range(settings.template_registration_poll_max_attempts):
            resp = await self.request("GET", path)
            if resp.status_code >= 400:
                raise EngineError(f"Presenton task status check failed ({resp.status_code}).")
            task = resp.json()
            if task.get("error") is not None or task.get("data") is not None:
                return task
            await asyncio.sleep(settings.template_registration_poll_interval_seconds)
        raise EngineError("Presenton template registration timed out.")

    async def delete_template(self, *, ref: str) -> None:
        """DELETE /template/{id} (TM-5). No-op for the stock-theme sentinel --
        there is no engine-side row for a template that never registered."""
        if not ref or ref == _STOCK_TEMPLATE_REF:
            return
        resp = await self.request("DELETE", f"/api/v1/ppt/template/{ref}")
        if resp.status_code >= 400 and resp.status_code != 404:
            # 404 here means the engine already has no such template -- not a
            # failure of intent, the desired end state already holds.
            raise EngineError(f"Presenton template delete failed ({resp.status_code}).")

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
