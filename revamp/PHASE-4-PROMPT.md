# Phase 4 — Long-Term Hardening

**Duration:** ongoing · **Severity:** ⚪ Low–🟡 Medium · **Requires:** Phase 3 gate `PASS`

---

## Role & context

**NoteAI** turns uploaded documents into branded slide decks.

- `frontend/` — Next.js 14 App Router; single API client at `src/services/api.ts`
- `backend/` — FastAPI at `/api/v1`; Postgres, Redis/Arq, MinIO
- `presenton/` — slide renderer, vendored, same-origin at `/editor`
- `open-notebook` — embeddings + retrieval, project-scoped as of Phase 2

After Phases 0–3 the product works, is trustworthy, and has one pipeline. Phase 4 is **not a sprint** — it is a standing backlog worked between feature development.

---

## How this phase differs

Phases 0–3 were sequential with hard gates. Phase 4 is a **prioritised backlog**. Tasks are independent; pick by what the product needs next.

Two rules still apply:

1. **Each task still produces a test report entry.** Maintain a single rolling `revamp/reports/PHASE-4-REPORT.md`, appending a §3 row and §4 execution result per completed task. Do not skip reporting because the phase has no end date — that is exactly how a hardening backlog silently stops being worked.
2. **T-4.1 gates any multi-tenant sale.** Everything else is discretionary; that one is a precondition.

---

## Backlog

### T-4.1 — Multi-tenant re-enablement checklist 🟠 *(highest priority)*

**Context:** the platform ships `LITE_MODE=true` — single tenant, no auth. The SaaS code path (OIDC, RBAC, per-tenant BYOK, quotas) is intact but **has not run in production since the lite pivot**, and Phase 2's T-2.1 revealed that engine-tier isolation was never enforced at all.

`LITE_MODE=false` must be treated as **unverified** until this task completes. Do not enable it in any environment holding more than one tenant's data.

**Work:**

1. Audit every `if settings.lite_mode` branch. Each is a behavioural fork that has only been exercised on one side. Current sites: `auth/dependencies.py:41`, `tenancy/llm_config.py:51`, `metering/quota.py:74`.
2. Stand up a two-tenant staging environment with a real OIDC provider.
3. Run the isolation matrix — for **every** resource type (project, source, generation, template, guide, chat, usage), assert tenant A cannot read, list, mutate, or download tenant B's, by direct id and by enumeration.
4. **Re-verify engine-tier isolation across tenants**, not just across projects. Phase 2 proved project scoping; cross-tenant is a stronger claim needing its own evidence.
5. Verify RBAC: viewer cannot generate; author cannot approve templates.
6. Verify per-tenant BYOK: tenant A's key is never used for tenant B's request.
7. Load-test quota enforcement under concurrency — `QuotaService.used_this_month` (`quota.py:56-64`) counts rows without locking, so concurrent requests can both pass the check. **Assess whether the overshoot is acceptable or needs a constraint.**
8. Produce `docs/MULTI-TENANT-READINESS.md` with the matrix and results.

**Acceptance:** the full matrix passes on two-tenant staging; residual risks documented; sign-off recorded.

---

### T-4.2 — Engine contract tests against real containers 🟠

**Context:** `backend/tests/fakes.py` backs every engine test. Those tests validate **the orchestrator's assumptions about the engines**, not the engines' behaviour. Every production failure in the assessment lived at exactly this boundary — Presenton's routing, Open Notebook's global search, MinIO's URL reachability — and the fake-based suite was green throughout.

**Work:**

1. Add a compose profile starting real `presenton`, `open-notebook`, `minio` for tests.
2. Contract tests against live containers:
   - Presenton: generate returns the documented shape; template registration behaves as assumed; **brand tokens are honoured** (guards T-1.3 permanently)
   - Open Notebook: source add → status → search; **scoping holds** (guards T-2.1)
   - MinIO: presign, put, get, and **browser-reachability of the public endpoint** (guards T-1.5)
3. Run nightly, not per-commit — they are slow. Keep the fast fake-based suite for PRs.
4. **On failure, treat it as a production incident**, not a flaky test. A contract test going red means an engine changed under you.

**Acceptance:** contract tests run nightly against real containers; each of T-1.3, T-1.5, T-2.1 has a permanent guard.

---

### T-4.3 — Structured engine-error taxonomy surfaced in the UI 🟡

**Context:** Phase 2's T-2.3 made LLM failures diagnosable **in logs**. Users still see "engine_unavailable". Every distinct cause — bad key, no credit, rate limit, unknown model, engine down, timeout — renders identically.

**Work:**

1. Extend the `EngineError` taxonomy with sub-codes: `engine.auth_failed`, `engine.quota_exhausted`, `engine.rate_limited`, `engine.model_not_found`, `engine.unavailable`, `engine.timeout`.
2. Preserve the no-leak rule from `core/errors.py` — sub-codes must be **actionable without disclosing** provider internals.
3. Map each to a user-facing message and a recovery hint in both `en` and `id`.
4. Retry-after handling for `rate_limited`.

**Acceptance:** each cause produces a distinct, actionable message in both locales; no provider internals leak.

---

### T-4.4 — Unblock ingestion workers 🟡

**Context:** `ingest_source` blocks a worker slot polling Open Notebook for up to **2 minutes** (`config.py:116-117`: 60 attempts × 2s). Concurrent uploads exhaust the pool; a modest batch serialises.

**Work:**

1. Replace in-task polling (`ingestion/service.py:210-218`) with re-enqueue-with-delay: check status, and if non-terminal, re-enqueue with a deferred run rather than sleeping.
2. Preserve idempotency and the resumability guarantees at `:162-190`.
3. Add a max-age guard so a stuck source eventually fails instead of re-enqueuing forever.
4. Load-test 20 concurrent uploads.

**Acceptance:** no worker blocks > 5s per task; 20 concurrent ingests complete without pool exhaustion; stuck sources terminate.

---

### T-4.5 — Retire Presenton's root-path API allowlist 🟡

**Context:** Phase 1's T-1.1 took option **1A** — `basePath` for the UI, plus an explicit Traefik allowlist for Presenton's root-level API paths, guarded by a collision test. This is the deferred **1B**.

**Work:**

1. Prefix Presenton's client-side API base so its browser calls target `/editor/api/...`.
2. Collapse the Traefik rule to a single `PathPrefix('/editor')`.
3. Retire the allowlist and the collision-guard test — with no shared prefixes, collision becomes structurally impossible rather than merely monitored.
4. Reclaim `/images`, `/fonts`, `/uploads`, `/app_data` for the NoteAI frontend.

**Acceptance:** one `PathPrefix` rule routes all Presenton traffic; the reclaimed prefixes reach the frontend; the editor journey still passes.

---

### T-4.6 — Repository hygiene ⚪

- Remove `metagpt/` and `.specify/` — unused scaffolding from earlier workflows (~15 files each). Confirm with the team first; the spec-kit skills in `.claude/skills/` may still be in use.
- `git rm --cached backend/.coverage`; add to `.gitignore`.
- Add `.DS_Store` to a global gitignore.
- Prune dead entries from `.env.lite.example`.
- Add a pre-commit hook for `ruff` + `prettier` + secret scanning.

**Acceptance:** clean `git status`; pre-commit hook active; no unused scaffolding.

---

### T-4.7 — Observability beyond logs ⚪

**Context:** structured logging with correlation ids exists (`core/logging.py`, `core/middleware.py`) and is good. There are no **metrics** — nobody can answer "how many generations failed this week?" without grepping.

**Work:**

1. Prometheus metrics: generation count by status, engine latency by engine, LLM token consumption, job queue depth, quota utilisation.
2. `/metrics` endpoint (**internal only** — must not route through Traefik's public entrypoint).
3. A dashboard covering the failure modes this programme fixed: silently-dropped jobs (T-1.4), engine errors by sub-code (T-4.3), ingest duration (T-4.4).
4. Alert on: generation failure rate > 10%, queue depth > 50, any circuit breaker open.

**Acceptance:** metrics exposed and scraped; dashboard live; alerts fire on synthetic failures.

---

### T-4.8 — Performance baseline ⚪

**Context:** no performance data exists. The assessment flagged risks (worker blocking, polling volume) without measurement.

**Work:**

1. Baseline: p50/p95 for ingest, guide generation, deck generation, download.
2. Frontend budgets per the project's own performance rules — LCP < 2.5s, INP < 200ms, CLS < 0.1; landing JS < 150kb gz.
3. Lighthouse in CI on the main routes.
4. Record baselines in `docs/PERFORMANCE-BASELINE.md`; treat regressions as bugs.

**Acceptance:** baselines recorded; Lighthouse in CI; budgets enforced.

---

## Priority ordering

| Order | Task | Trigger |
|---|---|---|
| 1 | **T-4.1** Multi-tenant readiness | Before any multi-tenant sale — **hard gate** |
| 2 | **T-4.2** Real engine contract tests | Before the next Presenton or Open Notebook upgrade |
| 3 | **T-4.3** Error taxonomy | When support load from opaque errors justifies it |
| 4 | **T-4.4** Unblock ingestion | Before concurrent usage grows |
| 5 | **T-4.7** Observability | Before the first real production incident, ideally |
| 6 | **T-4.5** Retire allowlist | Opportunistic — when Presenton is next touched |
| 7 | **T-4.8** Performance baseline | Before optimising anything |
| 8 | **T-4.6** Hygiene | Anytime |

---

## Verification

Per task. Standing regression suite before merging anything:

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term   # >= 88%
cd frontend && npm run typecheck && npm run test:coverage
npx playwright test
cd backend && ./.venv/bin/ruff check src/
```

---

## Deliverable

A **rolling** `revamp/reports/PHASE-4-REPORT.md`.

Unlike Phases 0–3, this is appended to over time. Per completed task, add:

- a §3 task row
- a §4 test-execution result
- a §6 regression confirmation
- a §7 entry if the work surfaced new findings

Add a dated changelog at the top so the document reads chronologically.

---

## Exit gate

Phase 4 has **no completion gate** — it is continuous. Two standing invariants:

| # | Invariant |
|---|---|
| **S1** | Backend coverage never falls below 88%; frontend thresholds never fall below Phase 2 levels |
| **S2** | `LITE_MODE=false` is not enabled in any multi-tenant environment until **T-4.1** passes |

**S2 is the one hard rule in this phase.** Everything else is prioritisation.

---

## Notes for the executor

- **T-4.1 is not optional if you sell to a second customer.** Everything else here is discretionary; that one is a precondition.
- **T-4.2 is the highest-leverage item.** Every production failure in this programme lived at an engine boundary that the fake-based suite reported green. Real contract tests are the only thing preventing a recurrence — and they permanently guard the three fixes that were most expensive to make.
- Resist treating this backlog as "done" because no gate forces it. The absence of a deadline is why hardening work quietly stops.
- When a Phase 4 task surfaces a 🔴 or 🟠 finding, **escalate it out of Phase 4** — critical findings do not belong in a discretionary backlog.
