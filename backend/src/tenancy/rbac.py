"""Role-based access control.

Roles are ordered (viewer < author < admin). `require_role(min_role)` returns a
FastAPI dependency that enforces the minimum role for a route. Per the contract,
lacking a role returns 403 (authenticated but unauthorized) — distinct from the 404
used for cross-tenant access to avoid resource enumeration.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from ..auth.dependencies import get_current_principal
from ..auth.principal import Principal
from ..core.config import get_settings
from ..core.errors import ForbiddenError
from ..models import UserRole

# Higher number = more privilege.
_ROLE_RANK: dict[UserRole, int] = {
    UserRole.viewer: 0,
    UserRole.author: 1,
    UserRole.admin: 2,
}


def has_at_least(role: UserRole, minimum: UserRole) -> bool:
    return _ROLE_RANK[role] >= _ROLE_RANK[minimum]


def require_role(minimum: UserRole) -> Callable[..., Principal]:
    """Build a dependency that admits only principals with at least `minimum` role."""

    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        # Lite mode: the default principal is admin and outranks every gate, but
        # skip the check explicitly so intent is clear and role config can't lock
        # the demo out. Full RBAC is enforced whenever LITE_MODE is off.
        if get_settings().lite_mode:
            return principal
        if not has_at_least(principal.role, minimum):
            raise ForbiddenError(
                f"Requires '{minimum.value}' role; '{principal.role.value}' is insufficient.",
                code="insufficient_role",
            )
        return principal

    return _dependency


# Convenience dependencies for common gates.
require_viewer = require_role(UserRole.viewer)
require_author = require_role(UserRole.author)
require_admin = require_role(UserRole.admin)
