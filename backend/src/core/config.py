"""Application configuration.

All secrets and engine coordinates load from the environment (see deploy/.env.example).
Engine URLs/credentials live ONLY here in the backend and are never serialized to clients.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Orchestrator runtime ---
    app_name: str = "presentation-notebook-llm-orchestrator"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    public_base_url: str = Field(default="http://localhost:3000", alias="PUBLIC_BASE_URL")

    # Master secret used to derive the BYOK encryption key and sign dev tokens.
    orch_secret_key: str = Field(default="dev-insecure-change-me", alias="ORCH_SECRET_KEY")

    # --- PostgreSQL (system of record) ---
    database_url: str = Field(
        default="postgresql+psycopg://orch:change-me@postgres:5432/orchestrator",
        alias="DATABASE_URL",
    )

    # --- Redis (queue / idempotency / cache) ---
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    # --- OIDC (Keycloak / Authentik) ---
    oidc_issuer: str = Field(default="", alias="OIDC_ISSUER")
    oidc_client_id: str = Field(default="orchestrator", alias="OIDC_CLIENT_ID")
    oidc_client_secret: str = Field(default="", alias="OIDC_CLIENT_SECRET")
    oidc_audience: str = Field(default="", alias="OIDC_AUDIENCE")
    # Dev mode accepts HS256 tokens signed with orch_secret_key so the stack runs
    # without a live IdP. NEVER enable in production.
    oidc_dev_mode: bool = Field(default=False, alias="OIDC_DEV_MODE")

    # --- Internal engines (private network only; never client-exposed) ---
    open_notebook_url: str = Field(
        default="http://open-notebook:5055", alias="OPEN_NOTEBOOK_URL"
    )
    presenton_url: str = Field(default="http://presenton:80", alias="PRESENTON_URL")
    presenton_auth_username: str = Field(default="admin", alias="PRESENTON_AUTH_USERNAME")
    presenton_auth_password: str = Field(default="", alias="PRESENTON_AUTH_PASSWORD")

    # --- Engine resilience knobs (timeouts / retries / circuit breaker) ---
    engine_timeout_seconds: float = Field(default=30.0)
    engine_max_retries: int = Field(default=3)
    engine_backoff_base_seconds: float = Field(default=0.5)
    engine_circuit_fail_threshold: int = Field(default=5)
    engine_circuit_reset_seconds: float = Field(default=30.0)

    # --- Ingestion polling (analysis is async on the engine side) ---
    ingest_poll_interval_seconds: float = Field(default=2.0)
    ingest_poll_max_attempts: int = Field(default=60)  # ~2 min at 2s
    ingest_presign_ttl_seconds: int = Field(default=900)

    # --- Outline LLM (controlled prompt: low temperature, pinned model) ---
    outline_llm_temperature: float = Field(default=0.1)
    outline_llm_max_tokens: int = Field(default=2000)

    # --- Metering (fallback pricing when a tenant has no per-model rates) ---
    usage_cost_per_1k_tokens: float = Field(default=0.002)
    default_input_cost_per_1k: float = Field(default=0.0014)
    default_output_cost_per_1k: float = Field(default=0.0028)

    # --- Quota policy when monthly generations are exceeded ---
    quota_policy: str = Field(default="block")  # "block" | "flag"

    # --- MinIO / S3-compatible object storage (tenant-prefixed keys) ---
    minio_endpoint: str = Field(default="http://minio:9000", alias="MINIO_ENDPOINT")
    minio_root_user: str = Field(default="minio", alias="MINIO_ROOT_USER")
    minio_root_password: str = Field(default="", alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = Field(default="presentations", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so config is parsed once per process."""
    return Settings()
