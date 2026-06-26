"""Arq worker entrypoint. docker-compose runs `arq src.workers.WorkerSettings`."""

from .settings import WorkerSettings

__all__ = ["WorkerSettings"]
