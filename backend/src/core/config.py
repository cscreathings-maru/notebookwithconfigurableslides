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

    # --- Lite mode (single-tenant demo build) ---
    # When true: auth/RBAC are bypassed behind their existing interfaces, every
    # request runs as the fixed default admin below, quotas are not enforced, and
    # the LLM provider config is read from the OpenRouter env vars instead of the
    # per-tenant BYOK record. Flip to false to restore the full multi-tenant SaaS.
    lite_mode: bool = Field(default=True, alias="LITE_MODE")
    default_tenant_slug: str = Field(default="demo", alias="DEFAULT_TENANT_SLUG")
    default_tenant_name: str = Field(default="Demo Workspace", alias="DEFAULT_TENANT_NAME")
    default_user_email: str = Field(default="demo@local", alias="DEFAULT_USER_EMAIL")

    # --- OpenRouter (lite-mode LLM for outline / analysis / generation) ---
    # Single source of truth for the OpenRouter swap. Chat-completions only —
    # embeddings are served elsewhere (see Open Notebook config). Set the exact
    # model slug here (e.g. the DeepSeek variant you intend to demo).
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="deepseek/deepseek-chat-v3", alias="OPENROUTER_MODEL"
    )
    # Curated model slugs offered in the Studio model dropdown (CSV). The default
    # OPENROUTER_MODEL is always included even if omitted here.
    openrouter_models: str = Field(
        default="deepseek/deepseek-chat-v3,openai/gpt-4o-mini,anthropic/claude-3.5-sonnet,google/gemini-flash-1.5",
        alias="OPENROUTER_MODELS",
    )

    @property
    def openrouter_model_list(self) -> list[str]:
        """De-duplicated dropdown models, with the active default first."""
        items = [m.strip() for m in self.openrouter_models.split(",") if m.strip()]
        ordered = [self.openrouter_model] + [m for m in items if m != self.openrouter_model]
        seen: set[str] = set()
        return [m for m in ordered if not (m in seen or seen.add(m))]

    # AI output language (the deck planner, plus the guide/chat prompts).
    # The prompts expect a language NAME (e.g. "Bahasa Indonesia"),
    # never an ISO code. Default targets Indonesian users; both are configurable.
    default_language: str = Field(default="Bahasa Indonesia", alias="DEFAULT_LANGUAGE")
    languages: str = Field(default="Bahasa Indonesia,English", alias="LANGUAGES")

    @property
    def language_list(self) -> list[str]:
        """De-duplicated language dropdown, with the active default first."""
        items = [m.strip() for m in self.languages.split(",") if m.strip()]
        ordered = [self.default_language] + [m for m in items if m != self.default_language]
        seen: set[str] = set()
        return [m for m in ordered if not (m in seen or seen.add(m))]

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

    # --- Deck template cataloguing (LD-2: one-time-per-template LLM call --
    # dump.py's slide text -> DesignCatalog. Low temperature: this is
    # classification, not composition, and consistency across a 30-slide
    # template matters more than variety) ---
    # 16000, not 6000: a reasoning-capable model (confirmed in production
    # 2026-08-16 against moonshotai/kimi-k3) can spend its ENTIRE completion
    # budget on hidden reasoning tokens before emitting any visible content,
    # returning HTTP 200 with `content: null` -- see
    # `LlmClient._extract_json_content`'s diagnostics. Cataloguing is a
    # one-time-per-template cost (assessment §4: "there is no reason to
    # economise there"), so a generous ceiling here is cheap insurance.
    deck_catalog_llm_temperature: float = Field(default=0.1)
    deck_catalog_llm_max_tokens: int = Field(default=16000)
    # How much slide dump may go into ONE cataloguing call, in characters
    # (~4 chars/token). Sending the whole template at once built a 21k-token
    # prompt, and a reasoning model asked to classify 30 slides in one go
    # spent its ENTIRE 16k output budget thinking -- 56k characters of
    # reasoning, `finish_reason: "length"`, `content: null` (production,
    # 2026-08-23, moonshotai/kimi-k3). Reasoning scales with how much is asked
    # at once, so asking less per call is the fix that holds for any model.
    # This is the plan's own documented contingency
    # (`ASSESSMENT-LLM-DECK-PLANNING.md` §7: "Chunk the dump per slide -- more
    # calls, still one-time"); cataloguing runs once per template, so the
    # extra round trips cost effectively nothing.
    #
    # Bounded by SIZE, not slide count: within one real template a slide
    # ranges from 341 to 7,960 characters (BRI's cover vs. its 95-shape
    # timeline), so "6 slides" bounds nothing that matters.
    deck_catalog_max_chars_per_call: int = Field(default=6000, ge=500)
    # Cataloguing calls in flight at once. Nine sequential calls at ~80s each
    # exceeded the worker's job timeout (production, 2026-08-23); the batches
    # are independent, so they need not queue behind each other. Keep it
    # modest -- a burst invites provider rate limiting.
    deck_catalog_concurrency: int = Field(default=4, ge=1, le=16)

    # --- Deck content + design planner (LD-6: ONE call -- content AND design
    # selection together, never layout/colour/font. Replaces RM-6's
    # content-only call plus RM-7's separate layout tie-break call: now that
    # a template's designs are catalogued once at onboarding (LD-2), picking
    # one per section is a small enough judgement to fold into the same call
    # that writes the content -- there is no separate matching step left) ---
    # 8000, not 4000, for the same reasoning-token-budget risk as cataloguing
    # above, on a smaller margin since this call recurs per generation.
    deck_plan_llm_temperature: float = Field(default=0.4)
    deck_plan_llm_max_tokens: int = Field(default=8000)

    # --- Per-task model routing (RM-12, COST-AND-MODEL-STRATEGY.md §6) ---
    # Empty means "use the tenant's configured model". One global model is what
    # let the deck engine silently inherit the chat model once before; these
    # exist so the deck calls can be priced and evaluated separately from chat:
    #   - deck planning is the quality-sensitive one (Bahasa Indonesia,
    #     character budgets, strict JSON, design selection) -- worth spending on.
    #   - template cataloguing runs once per template and amortises to
    #     near-zero (assessment §4) -- also worth the best model, not the
    #     cheapest, hence no separate "cheap tier" default here either.
    deck_plan_model: str = Field(default="", alias="DECK_PLAN_MODEL")
    deck_catalog_model: str = Field(default="", alias="DECK_CATALOG_MODEL")

    # --- Chat LLM (RAG Q&A + guide) ---
    # A safety net, not an answer-length policy: most replies land far below this, so
    # raising it barely moves average cost. It used to be hard-coded at 1000 — the
    # lowest cap in the codebase, and the only one on a surface producing long prose —
    # which truncated ordinary answers (mid-sentence, even inside table cells) with no
    # signal to the caller. Anything still cut off is meant to be continued via
    # ChatService.continue_message, not chased by raising this further.
    chat_llm_max_tokens: int = Field(default=8000, alias="CHAT_LLM_MAX_TOKENS")

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
