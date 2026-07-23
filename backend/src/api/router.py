"""Aggregate the versioned API surface under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    auth,
    chat,
    generations,
    guide,
    jobs,
    languages,
    models,
    outlines,
    profiles,
    projects,
    sources,
    templates,
    tenant,
    usage,
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(jobs.router)
api_v1.include_router(projects.router)
api_v1.include_router(sources.router)
api_v1.include_router(guide.router)
api_v1.include_router(chat.router)
api_v1.include_router(profiles.router)
api_v1.include_router(templates.router)
api_v1.include_router(outlines.router)
api_v1.include_router(generations.router)
api_v1.include_router(usage.router)
api_v1.include_router(tenant.router)
api_v1.include_router(models.router)
api_v1.include_router(languages.router)
