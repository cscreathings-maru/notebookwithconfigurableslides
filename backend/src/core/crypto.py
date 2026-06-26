"""Symmetric encryption for per-tenant BYOK provider config (encrypted at rest).

The Fernet key is derived from ORCH_SECRET_KEY so a single master secret protects
all tenant LLM credentials. Plaintext provider keys are never logged and only ever
live in memory transiently. Tenant.llm_config_enc stores the ciphertext bytes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings
from .errors import AppError


class CryptoError(AppError):
    code = "crypto_error"
    status_code = 500


def _fernet() -> Fernet:
    secret = get_settings().orch_secret_key.encode("utf-8")
    # Derive a stable 32-byte urlsafe key from the master secret.
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_json(data: dict[str, Any]) -> bytes:
    """Encrypt a JSON-serializable provider config to ciphertext bytes."""
    plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(plaintext)


def decrypt_json(token: bytes) -> dict[str, Any]:
    """Decrypt ciphertext bytes back to the provider config dict."""
    try:
        plaintext = _fernet().decrypt(token)
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise CryptoError("Failed to decrypt tenant provider config.") from exc
    return json.loads(plaintext.decode("utf-8"))
