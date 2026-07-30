"""Arq WorkerSettings — registers tasks and the Redis connection."""

from __future__ import annotations

from arq.connections import RedisSettings

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from .reconcile import reenqueue_stranded_jobs
from .tasks import run_generate, run_ingest

logger = get_logger("orchestrator.worker")


async def _on_startup(ctx: dict) -> None:
    configure_logging(get_settings().log_level)
    logger.info("worker_startup")

    # Redis holds only the pending queue; Postgres holds the durable job. A Redis
    # restart drops the former and strands the latter at `queued` forever, with no
    # error and no retry. Reconciling here catches exactly that, since a restart is
    # the most likely reason this worker is starting at all.
    try:
        await reenqueue_stranded_jobs(ctx.get("redis"))
    except Exception as exc:
        # Never let reconciliation stop the worker from coming up.
        logger.error(
            "worker_startup_reconcile_failed",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )


class WorkerSettings:
    """Referenced by `arq src.workers.WorkerSettings` in docker-compose."""

    functions = [run_ingest, run_generate]
    on_startup = _on_startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = get_settings().engine_max_retries
    keep_result = 3600
