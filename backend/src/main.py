"""FastAPI application factory — the only public surface of the platform.

Wires: structured logging, correlation-id middleware, the consistent JSON error
shape, health endpoints, and the versioned API. The Arq redis pool is attached to
app.state at startup so request handlers can enqueue async jobs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.health import router as health_router
from .api.router import api_v1
from .core.config import get_settings
from .core.errors import register_exception_handlers
from .core.logging import configure_logging, get_logger
from .core.middleware import CorrelationIdMiddleware

logger = get_logger("orchestrator.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("startup", extra={"environment": settings.environment})

    # Lazily connect the Arq pool so the API can enqueue jobs. Failure to reach
    # Redis is non-fatal for read endpoints; enqueue will surface it explicitly.
    app.state.arq_pool = None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        logger.info("arq_pool_connected")
    except Exception:  # pragma: no cover - infra dependent
        logger.warning("arq_pool_unavailable")

    yield

    pool = getattr(app.state, "arq_pool", None)
    if pool is not None:  # pragma: no cover - infra dependent
        await pool.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Presentation Notebook LLM — Orchestrator API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1)
    return app


app = create_app()
