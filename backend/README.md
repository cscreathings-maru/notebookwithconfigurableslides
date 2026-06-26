# Orchestrator backend (Slice 0 — platform skeleton)

FastAPI orchestration service — the **only public surface** of the Presentation
Notebook LLM platform. Open Notebook and Presenton are internal engines reached
only from here over a private network; their URLs/credentials never leave the backend.

## What's in this slice

- **Config & secrets** — `src/core/config.py` (pydantic-settings, env-driven).
- **Structured logging + correlation id** — `src/core/logging.py`,
  `src/core/middleware.py` (JSON logs, `X-Correlation-ID` per request).
- **Consistent JSON errors** — `src/core/errors.py` → `{ "error": { code, message } }`.
- **Health** — `GET /healthz` (liveness), `GET /readyz` (DB readiness).
- **Data layer** — `Tenant`, `User`, `Job` models + Alembic migration `0001_initial`.
  UUID PKs, UTC timestamps, `tenant_id` on every table except `tenant`.
- **OIDC auth** — `src/auth/`; `GET /api/v1/auth/me` returns user, tenant, role.
- **Multi-tenancy** — tenant resolved **server-side** from the token; the
  `TenantScopedRepository` forces a `tenant_id` filter on every query, so
  cross-tenant access returns **404** (no enumeration).
- **RBAC** — `admin > author > viewer`; `require_role(...)` dependency → **403**
  when authenticated but under-privileged.
- **Async jobs** — `JobService` (idempotency key, attempts, progress) + Arq worker
  (`arq src.workers.WorkerSettings`); `GET /api/v1/jobs/{id}` to poll.
- **Engine client stubs** — `src/engines/` with timeout, bounded retry + backoff,
  and a circuit breaker (resilience real; engine methods are typed stubs).
- **BYOK** — per-tenant LLM provider config encrypted at rest (Fernet);
  `PUT /api/v1/tenant/llm-config` (admin); secret never echoed back.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Tests run on SQLite — no Postgres/Redis needed.
pytest -q

# Migrate a real Postgres (uses DATABASE_URL from the env):
alembic upgrade head
python -m scripts.seed_tenant --name "Acme" --admin you@acme.id
```

In Docker the service is built from this directory by `deploy/docker-compose.yml`
(API container runs uvicorn; the worker container runs Arq).

## Test-first note

The two guard tests (`tests/contract/test_tenant_isolation.py`,
`tests/integration/test_rbac_viewer.py`) were verified to fail when their guard is
removed — the tenant filter and the role check each have a proven red state — then
pass with the guard in place.
