"""Arq WorkerSettings — registers tasks and the Redis connection."""

from __future__ import annotations

from arq.connections import RedisSettings

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from .tasks import run_generate, run_ingest

logger = get_logger("orchestrator.worker")


async def _on_startup(ctx: dict) -> None:
    configure_logging(get_settings().log_level)
    logger.info("worker_startup")


class WorkerSettings:
    """Referenced by `arq src.workers.WorkerSettings` in docker-compose."""

    functions = [run_ingest, run_generate]
    on_startup = _on_startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = get_settings().engine_max_retries
    keep_result = 3600
