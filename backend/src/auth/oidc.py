"""OIDC token validation.

Production: validate the bearer JWT against the IdP's JWKS (issuer, audience,
signature, expiry). Dev mode (OIDC_DEV_MODE=true): accept HS256 tokens signed with
ORCH_SECRET_KEY so the stack runs without a live Keycloak/Authentik. The validated
claims' `sub` is the oidc_subject we map to a User.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from ..core.config import get_settings
from ..core.errors import UnauthorizedError


@lru_cache
def _jwks_client(issuer: str) -> PyJWKClient:
    # Standard OIDC discovery JWKS location.
    return PyJWKClient(f"{issuer.rstrip('/')}/protocol/openid-connect/certs")


def validate_token(token: str) -> dict[str, Any]:
    """Validate a bearer token and return its claims, or raise UnauthorizedError."""
    settings = get_settings()

    if settings.oidc_dev_mode:
        return _validate_dev(token, settings.orch_secret_key)

    if not settings.oidc_issuer:
        raise UnauthorizedError("OIDC issuer is not configured.")

    try:
        signing_key = _jwks_client(settings.oidc_issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience or None,
            options={"verify_aud": bool(settings.oidc_audience)},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token.") from exc

    if not claims.get("sub"):
        raise UnauthorizedError("Token is missing a subject claim.")
    return claims


def _validate_dev(token: str, secret: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired dev token.") from exc
    if not claims.get("sub"):
        raise UnauthorizedError("Dev token is missing a subject claim.")
    return claims
