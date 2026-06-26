"""Stakeholder profiles router (admin writes; authors read approved only).

Tenant-scoped and versioned: PUT creates a new version, never mutating the prior
one. The logical `id` is what clients see; engine details are not involved here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from ..auth.dependencies import get_current_principal
from ..auth.principal import Principal
from ..models import StakeholderProfile, UserRole
from ..registry.service import ProfileService
from ..schemas.registry import ProfileResponse, ProfileWrite
from ..tenancy.rbac import require_admin, require_viewer
from .deps import get_profile_service

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _to_response(p: StakeholderProfile) -> ProfileResponse:
    return ProfileResponse(
        id=p.logical_id,
        version=p.version,
        name=p.name,
        audience=p.audience,
        template_id=p.template_id,
        template_version=p.template_version,
        tone=p.tone,
        verbosity=p.verbosity,
        slide_min=p.slide_min,
        slide_max=p.slide_max,
        language=p.language,
        section_structure=p.section_structure,
        prompt_config=p.prompt_config,
        status=p.status,
        created_at=p.created_at,
    )


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileWrite,
    principal: Principal = Depends(require_admin),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    profile = service.create(created_by=principal.user_id, **payload.model_dump())
    return _to_response(profile)


@router.get("", response_model=list[ProfileResponse])
def list_profiles(
    principal: Principal = Depends(require_viewer),
    service: ProfileService = Depends(get_profile_service),
) -> list[ProfileResponse]:
    approved_only = principal.role is not UserRole.admin
    return [_to_response(p) for p in service.list_all(approved_only=approved_only)]


@router.put("/{profile_id}", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def update_profile(
    profile_id: uuid.UUID,
    payload: ProfileWrite,
    principal: Principal = Depends(require_admin),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    profile = service.update(profile_id, created_by=principal.user_id, **payload.model_dump())
    return _to_response(profile)


@router.post("/{profile_id}/approve", response_model=ProfileResponse)
def approve_profile(
    profile_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    return _to_response(service.approve(profile_id, actor_user_id=principal.user_id))
