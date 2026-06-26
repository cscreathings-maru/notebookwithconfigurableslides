Build the platform skeleton for a multi-tenant SaaS orchestration backend and its frontend shell. Do NOT build or reimplement Open Notebook or Presenton — they are existing external HTTP services; only stub typed clients for them.

Context: this is the orchestration layer of a "Presentation Notebook LLM" platform. It is the only public surface; two analysis/generation engines run on a private network behind it.

Stack: Python 3.11, FastAPI, SQLAlchemy + Alembic on PostgreSQL, Redis, Arq (or Celery) for async jobs, httpx for engine clients. Frontend: Next.js (App Router) + TypeScript + Tailwind.

Deliver:
1. Backend service `backend/` with: config/secrets loading, structured logging with a per-request correlation id, consistent JSON error shape, and health endpoint.
2. Data layer: SQLAlchemy models + Alembic migrations for Tenant, User, and a generic Job (fields per the data model: tenant_id everywhere except Tenant; UUID PKs; UTC timestamps).
3. OIDC authentication: validate the session token, map oidc_subject → User, expose GET /api/v1/auth/me returning user, tenant, role.
4. Multi-tenancy: middleware that resolves tenant_id SERVER-SIDE from the token (never from path/body), plus a tenant-scoped repository base that forces a tenant_id filter on every query and returns 404 on cross-tenant access.
5. RBAC with roles admin, author, viewer; a dependency that enforces required role per route.
6. Async job framework: enqueue, idempotency key, attempts, progress, and GET /api/v1/jobs/{id} for polling.
7. Typed engine client stubs (Open Notebook, Presenton) with timeout, bounded retry with backoff, and circuit breaker — methods only, no engine logic.
8. Encrypted per-tenant LLM provider config storage (BYOK).
9. Frontend shell: OIDC login, authenticated layout, role-aware navigation, and an API client.
10. Tests: contract test asserting cross-tenant access returns 404; integration test asserting a viewer cannot perform a mutating action; verify they fail before implementation.

Constraints: engine URLs/credentials live only in the backend; never exposed to the client. Provide docker-compose-ready service config and an .env.example.
