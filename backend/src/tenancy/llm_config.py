"""Per-tenant BYOK LLM provider config — encrypted at rest, decrypted only in memory.

Stores {base_url, model, api_key, ...} encrypted in Tenant.llm_config_enc via the
master-secret-derived Fernet key. The plaintext key is never logged and never sent
to a client; it is passed per-request to the engines (see the engine contract).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..core.crypto import decrypt_json, encrypt_json
from ..core.errors import NotFoundError
from ..models import Tenant

# Fields safe to echo back to admins (everything except the secret key).
_PUBLIC_FIELDS = {"base_url", "model", "provider"}


class TenantLlmConfigService:
    def __init__(self, db: Session, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def _tenant(self) -> Tenant:
        tenant = self.db.get(Tenant, self.tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        return tenant

    def set_config(self, *, provider: str, config: dict[str, Any]) -> None:
        """Encrypt and persist the tenant's provider config (immutable update)."""
        tenant = self._tenant()
        tenant.llm_provider = provider
        tenant.llm_config_enc = encrypt_json({"provider": provider, **config})
        self.db.add(tenant)
        self.db.flush()

    def get_config(self) -> dict[str, Any]:
        """Decrypt and return the full provider config (server-side use only)."""
        tenant = self._tenant()
        if not tenant.llm_config_enc:
            raise NotFoundError("Tenant has no LLM provider configured.")
        return decrypt_json(tenant.llm_config_enc)

    def get_public_config(self) -> dict[str, Any]:
        """Return only non-secret fields, safe to show an admin in the UI."""
        config = self.get_config()
        return {k: v for k, v in config.items() if k in _PUBLIC_FIELDS}
