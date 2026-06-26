"""Tenant-scoped Outline repository."""

from __future__ import annotations

from ..models import Outline
from ..tenancy.repository import TenantScopedRepository


class OutlineRepository(TenantScopedRepository[Outline]):
    model = Outline
