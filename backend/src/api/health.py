"""Health endpoints — unauthenticated liveness/readiness."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..core.db import engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness: the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return {"status": "degraded", "db": "unreachable"}
    return {"status": "ok", "db": "ok"}
