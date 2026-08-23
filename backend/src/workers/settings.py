"""Arq WorkerSettings — registers tasks and the Redis connection."""

from __future__ import annotations

from arq import func
from arq.connections import RedisSettings

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from .reconcile import reenqueue_stranded_jobs
from .tasks import run_catalog_template, run_generate, run_ingest

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

    # Cataloguing gets its own, longer ceiling. It is one LLM call per batch
    # of slides -- nine calls for the BRI template -- and Arq's 300s default
    # killed it two thirds of the way through with nothing persisted
    # (production, 2026-08-23). Raised per-function rather than globally so a
    # genuinely hung ingest still fails fast.
    #
    # 900s deliberately sits below `reconcile._RUNNING_STALE_AFTER` (30 min):
    # a job must never be able to outlive the point where the reconciler
    # presumes it dead and re-enqueues it alongside the copy still running.
    functions = [run_ingest, run_generate, func(run_catalog_template, timeout=900)]
    on_startup = _on_startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = get_settings().engine_max_retries
    keep_result = 3600
