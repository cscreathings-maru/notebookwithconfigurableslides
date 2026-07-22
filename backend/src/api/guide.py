"""Guide router — the auto-generated notebook overview (summary + questions).

GET returns the stored guide (404 until generated); POST (re)generates it from the
indexed sources. Generation is synchronous — the caller shows a loading state.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ..auth.principal import Principal
from ..core.errors import NotFoundError
from ..guide.service import GuideService
from ..models import NotebookGuide
from ..schemas.guide import GuideResponse
from ..tenancy.rbac import require_author, require_viewer
from .deps import get_guide_service

router = APIRouter(tags=["guide"])


def _to_response(project_id: uuid.UUID, guide: NotebookGuide) -> GuideResponse:
    return GuideResponse(
        project_id=project_id,
        summary=guide.summary,
        suggested_questions=list(guide.suggested_questions or []),
        status=guide.status,
        error=guide.error,
        updated_at=guide.updated_at,
    )


@router.get("/projects/{project_id}/guide", response_model=GuideResponse)
def get_guide(
    project_id: uuid.UUID,
    _: Principal = Depends(require_viewer),
    service: GuideService = Depends(get_guide_service),
) -> GuideResponse:
    guide = service.get(project_id)
    if guide is None:
        raise NotFoundError("No guide has been generated for this project yet.")
    return _to_response(project_id, guide)


@router.post("/projects/{project_id}/guide", response_model=GuideResponse)
async def generate_guide(
    project_id: uuid.UUID,
    _: Principal = Depends(require_author),
    service: GuideService = Depends(get_guide_service),
) -> GuideResponse:
    guide = await service.generate(project_id=project_id)
    return _to_response(project_id, guide)
