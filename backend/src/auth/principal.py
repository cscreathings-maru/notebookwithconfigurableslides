"""The authenticated principal: who is calling and which tenant they belong to.

Tenant identity here is derived SERVER-SIDE from the validated token (via the User
record), never from a client-supplied path or body parameter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ..models import UserRole


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: UserRole
    email: str

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.admin
