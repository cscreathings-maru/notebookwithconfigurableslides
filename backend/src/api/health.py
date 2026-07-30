"""Health endpoints — unauthenticated liveness/readiness.

Registered twice, deliberately:

- under `/api` (`/api/healthz`, `/api/readyz`) so Traefik routes them. Traefik sends
  `/` to the frontend, so root-mounted probes were unreachable in the deployed stack —
  the orchestrator had health endpoints nothing could reach.
- at the root (`/healthz`, `/readyz`) for container probes, which talk to the process
  directly and never traverse the proxy.

`/readyz` reports **per dependency**. A Presenton outage means decks cannot render; it
does not mean the orchestrator is dead, and a probe that conflates the two removes a
service that is still serving most of its API. Only Postgres — the system of record —
can make the whole service `unready`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Response
from sqlalchemy import text

from ..core.config import get_settings
from ..core.db import engine
from ..core.logging import get_logger

logger = get_logger("orchestrator.health")

router = APIRouter(tags=["health"])

# Only a Postgres failure makes the service unready; everything else degrades.
_CRITICAL = "postgres"
_PROBE_TIMEOUT_SECONDS = 2.0


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up. Never touches a dependency."""
    return {"status": "ok"}


def _check_postgres() -> dict[str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        return {"status": "down", "detail": type(exc).__name__}
    return {"status": "ok"}


async def _check_redis() -> dict[str, str]:
    try:
        from redis.asyncio import from_url

        client = from_url(get_settings().redis_url)
        try:
            await asyncio.wait_for(client.ping(), timeout=_PROBE_TIMEOUT_SECONDS)
        finally:
            await client.aclose()
    except Exception as exc:
        return {"status": "down", "detail": type(exc).__name__}
    return {"status": "ok"}


async def _check_http(url: str) -> dict[str, str]:
    """Any HTTP answer means the dependency is listening — including a 4xx."""
    # A URL without a scheme raises httpx.UnsupportedProtocol, which reads as though the
    # dependency is down when in fact the *configuration* is wrong. That happened on the
    # production deployment: Presenton was healthy and reported `down`. Name the real
    # cause rather than making an operator debug a service that is fine.
    if not url.startswith(("http://", "https://")):
        return {
            "status": "misconfigured",
            "detail": f"URL has no http(s):// scheme: {url!r}",
        }
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
        if resp.status_code >= 500:
            return {"status": "degraded", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "down", "detail": type(exc).__name__}
    return {"status": "ok"}


async def _dependencies() -> dict[str, dict[str, str]]:
    """Probe every dependency concurrently; a slow one must not serialise the rest."""
    settings = get_settings()
    redis, minio, open_notebook, presenton = await asyncio.gather(
        _check_redis(),
        _check_http(f"{settings.minio_endpoint.rstrip('/')}/minio/health/live"),
        _check_http(f"{settings.open_notebook_url.rstrip('/')}/health"),
        _check_http(f"{settings.presenton_url.rstrip('/')}/"),
    )
    return {
        _CRITICAL: _check_postgres(),
        "redis": redis,
        "minio": minio,
        "open_notebook": open_notebook,
        "presenton": presenton,
    }


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, Any]:
    """Readiness: per-dependency status, with Postgres alone able to fail the check."""
    checks = await _dependencies()

    # `misconfigured` counts as not-ok: a probe that cannot be issued tells us nothing
    # about the dependency, and treating it as healthy would hide the config error.
    if checks[_CRITICAL]["status"] != "ok":
        overall = "unready"
        response.status_code = 503
    elif any(c["status"] != "ok" for c in checks.values()):
        overall = "degraded"
    else:
        overall = "ok"

    if overall != "ok":
        logger.warning(
            "readiness_not_ok",
            extra={
                "overall": overall,
                "unhealthy": [n for n, c in checks.items() if c["status"] != "ok"],
            },
        )
    return {"status": overall, "dependencies": checks}
