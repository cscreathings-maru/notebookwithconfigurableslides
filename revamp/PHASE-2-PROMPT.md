# Phase 2 — Architecture Stabilisation

**Duration:** 4–5 days · **Severity:** 🔴 Critical + 🟠 High · **Requires:** Phase 1 gate `PASS`

---

## Role & context

**NoteAI** turns uploaded documents into branded slide decks.

- `frontend/` — Next.js 14 App Router; single API client at `src/services/api.ts`
- `backend/` — FastAPI at `/api/v1`; Postgres, Redis/Arq, MinIO
- `presenton/` — slide renderer, vendored in Phase 0, served same-origin at `/editor` via build-time `basePath`
- `open-notebook` — embeddings + retrieval over SurrealDB
- Traefik path-routes everything on one origin

After Phase 1 the core loop works: upload → generate → **branded** download → edit.

Phase 2 makes it **trustworthy**. Phase 1 fixed what users could see. Phase 2 fixes what they cannot: a data-isolation hole, a reporting layer blind to the primary path, undiagnosable LLM failures, and the absence of any test tier over the frontend where two of Phase 1's defects lived.

---

## Scope

### In scope

| Task | Fixes | Severity |
|---|---|---|
| T-2.1 | RAG retrieval is not scoped to project or tenant | 🔴 |
| T-2.2 | Primary generation path bypasses quota and metering | 🟠 |
| T-2.3 | `LlmClient` bypasses resilience and discards error detail | 🟠 |
| T-2.4 | No health monitoring anywhere | 🟠 |
| T-2.5 | Zero frontend tests | 🟡 |
| T-2.6 | The "verification suite" is a regex script that proves nothing | 🟡 |
| T-2.7 | Documentation asserts quality that was never measured | 🟡 |

### Out of scope — defer

- Deleting the governed outline/profile pipeline → **Phase 3**
- Collapsing the polymorphic `/generations` endpoint → **Phase 3**
- Removing the `run_transformation` dead abstraction → **Phase 3**
- Replacing `StudioPanel` polling with SSE → **Phase 3**
- Engine contract tests against real containers → **Phase 4**

---

## Tasks

T-2.1 first — it is the only 🔴 and it gates any multi-tenant claim.

---

### T-2.1 — Scope RAG retrieval to the project 🔴

**Problem:** Project A's guide, chat answers, and generated decks can be grounded in **Project B's documents**. With `LITE_MODE=false`, across tenants.

**Evidence:**
- `backend/src/engines/open_notebook.py:127-169` — `search()` accepts `notebook_id` and **never uses it**. The request body is `{query, type, limit, search_sources, search_notes, minimum_score}` — no notebook filter. The docstring concedes: *"Open Notebook search is global (not notebook-scoped)"*.
- Callers that pass `notebook_id` believing it scopes the query:
  - `backend/src/chat/service.py:45` — every chat answer
  - `backend/src/guide/service.py:48` — every project overview
  - `backend/src/generation/freeform_service.py:155` — `content_source="notebook"` deck generation

**Why the existing tests miss it:** `backend/tests/contract/test_tenant_isolation.py` exercises only the Postgres repository layer, where isolation is genuinely airtight (`tenancy/repository.py:36-38` makes an unfiltered query impossible). The engine tier has **no isolation test at all**. The orchestrator's boundary is sound; the engine behind it is a shared global index.

This directly violates the spec's User Story 4, which designates isolation a release blocker (`specs/001-presentation-notebook-llm/spec.md`).

**Change:**

1. **Establish what Open Notebook actually supports.** Read the API surface of the pinned image (`lfnovo/open_notebook:v1-latest`). Determine whether `/api/search` accepts a notebook filter, whether per-notebook search exists on another route, or whether results carry a notebook reference usable for post-filtering. **Record the finding** — it determines which option below is available, and nobody on the team currently knows the answer.

2. Choose by capability:

   | Option | Approach | When |
   |---|---|---|
   | **A — engine-side filter** | Pass the notebook filter in the search request | Engine supports it. **Strongly preferred.** |
   | **B — post-filter** | Retrieve, then drop results whose notebook ≠ the project's | Engine returns a usable notebook ref. Acceptable interim; over-fetch to keep recall. |
   | **C — instance/namespace per tenant** | Separate Open Notebook namespace per tenant | Neither A nor B is possible. Heaviest; strongest guarantee. |

   > **If only C is available, say so explicitly and escalate before building it** — it is an infrastructure change with cost implications, not a code fix.

3. **Fail closed.** If the notebook reference is missing or unfilterable, return **no** grounding rather than unscoped grounding. An empty guide is a visible, recoverable bug. A guide grounded in another tenant's documents is a breach.

   This overrides the current best-effort posture at `open_notebook.py:132` (*"Any failure … degrades to no grounding"*) — keep that for *availability* failures, not for *scoping* failures.

4. **Engine-tier isolation test** — the gap that let this through:
   ```python
   # backend/tests/contract/test_engine_isolation.py
   def test_search_results_never_cross_notebooks(): ...
   def test_guide_is_grounded_only_in_own_project_sources(): ...
   def test_chat_citations_reference_only_own_project_sources(): ...
   ```

5. Delete the now-inaccurate docstring claim at `open_notebook.py:129-130`.

**Acceptance:**
- Two projects with disjoint sources: neither guide, chat, nor deck for A references B's content
- Missing/unfilterable notebook ref → empty grounding, never unscoped grounding
- Engine-isolation tests pass and fail against the old implementation
- `LITE_MODE=false` is safe to enable (or the residual risk is documented)

---

### T-2.2 — Unify quota and metering across both generation paths 🟠

**Problem:** the `/usage` dashboard reports **zero generations** for the path users actually use.

**Evidence:**
- `backend/src/generation/service.py:108` — governed path calls `QuotaService.enforce`
- `backend/src/generation/service.py:143` — governed path calls `MeteringService.record(action="generation.created")`
- `backend/src/generation/freeform_service.py:53-124` — freeform path calls **neither**
- `backend/src/metering/aggregation.py:20,34` — rollups count `action == "generation.created"`

The Studio (freeform) path is the primary user path. It emits no usage record, so the README's "Usage Dashboard & Quotas" feature is structurally unable to observe the product it reports on.

**Change:**

1. Extract a shared pre-flight both services call:
   ```python
   # backend/src/generation/preflight.py
   async def authorize_and_meter(*, db, tenant_id, actor_user_id, alert_sink, resource: dict) -> None:
       """Quota gate + usage record. Every generation path goes through here."""
   ```
2. Call it from **both** `service.py` and `freeform_service.py`.
3. Preserve current ordering: quota is enforced **before** any row is written, so a blocked attempt consumes nothing (`service.py:106-110`).
4. Respect lite mode — `QuotaService.enforce` already short-circuits when `lite_mode` is on (`quota.py:73-75`). **Metering must still record** even in lite mode, or the dashboard stays blind.
5. Tests: a freeform generation appears in `/usage`; with `LITE_MODE=false` and quota exhausted, a freeform generation is blocked with `429 quota_exceeded`.

**Acceptance:**
- A freeform generation increments `/usage` generation count
- Quota blocks freeform generations when exhausted (non-lite)
- Both paths route through one pre-flight — no duplicated logic

---

### T-2.3 — Bring `LlmClient` under the resilience layer 🟠

**Problem:** LLM failures are undiagnosable, and the LLM is the one engine with no retry or circuit breaker.

**Evidence:**
- `backend/src/engines/llm.py:37-84` — calls `httpx` directly. No retry, no backoff, no breaker — unlike `OpenNotebookClient` and `PresentonClient`, which both extend `EngineClient` (`engines/base.py`).
- `backend/src/engines/llm.py:82-83` — `raise EngineError("LLM provider request failed.")`, discarding status code and body

OpenRouter's distinct failure modes — 401 invalid key, 402 insufficient credits, 429 rate-limited, 404 unknown model slug — all collapse into one opaque string. An operator cannot tell a billing problem from a typo in `OPENROUTER_MODEL`.

**Change:**

1. Make `LlmClient` extend `EngineClient` so it inherits timeout, bounded backoff on 5xx/429 only, and the breaker. Preserve the injectable-client seam used by tests.
2. **Log status code and a body snippet server-side** at `error`, with the correlation id. Keep the client-facing message opaque — `core/errors.py`'s no-leak posture is correct and stays.
3. Map the common cases to actionable operator-facing log messages:
   - 401 → "LLM provider rejected the API key"
   - 402 → "LLM provider account has insufficient credit"
   - 404 → "Model slug not found — check OPENROUTER_MODEL"
   - 429 → "Rate limited; retrying with backoff"
4. Preserve per-request `provider_config` and `model_override` — the Studio model dropdown depends on both.
5. Tests: each status maps to its message; 429 retries; 401 does not.

**Acceptance:**
- `LlmClient` extends `EngineClient`; retry/breaker verified by test
- Logs identify which failure occurred; client responses still leak nothing
- Coverage for `engines/llm.py` rises from 31% to ≥ 70%

---

### T-2.4 — Restore health monitoring 🟠

**Problem:** there is none.

**Evidence:**
- `backend/src/api/health.py` registers `/healthz` and `/readyz` at the **root**, outside the `/api/v1` prefix (`api/router.py:24`)
- Traefik routes `/` to the frontend (`docker-compose.lite.yml:61`) — **both endpoints are unreachable in the deployed stack**
- `grep -c healthcheck deploy/docker-compose*.yml` → **0** in both files
- `docker-compose.lite.yml:45` — `init` uses `depends_on: [postgres]` with no readiness condition, so `alembic upgrade head` races Postgres startup

**Change:**

1. Move health endpoints under `/api` so Traefik routes them (`/api/healthz`, `/api/readyz`). Keep the root registrations as aliases for direct container probes.
2. Extend `/readyz` beyond Postgres to report Redis, MinIO, and each engine — **degraded, not failed**, per dependency, so a Presenton outage does not read as a dead orchestrator.
3. Add compose `healthcheck` blocks for postgres, redis, minio, orchestrator, frontend, presenton.
4. Convert `depends_on` to `condition: service_healthy` where readiness genuinely matters — `init` on postgres above all.
5. Test asserting `/api/readyz` reports each dependency independently.

**Acceptance:**
- `curl https://<domain>/api/readyz` returns per-dependency status through Traefik
- Every service has a healthcheck; `docker compose ps` shows health state
- `init` cannot run before Postgres is accepting connections

---

### T-2.5 — Establish the frontend test tier 🟡

**Problem:** ~4,760 LOC, zero tests, no framework installed (`frontend/package.json`). **Both frontend defects fixed in Phase 1 (T-1.2's wrong identifier and dead env var) were trivially unit-testable and shipped anyway.**

**Change:**

1. Install Vitest + React Testing Library + jsdom. Add `test` and `test:coverage` scripts.
2. Cover, in priority order:
   - `services/api.ts` — error envelope parsing, `ApiError` shape, FormData boundary handling (`api.ts:39-67`)
   - `components/project/SlideEditorModal.tsx` — URL resolution, both branches (regression guard for T-1.2)
   - `components/project/StudioPanel.tsx` — config assembly, terminal-state polling, download branch
   - `components/registry/SectionStructureBuilder.tsx` — reorder/delete (pure state logic, high value per test)
   - `lib/i18n` — `en` and `id` key parity, so a missing translation fails CI
3. Target ≥ 60% on `services/` and `lib/`, ≥ 40% on `components/`. **Do not chase a global number** — buy regression protection where Phase 1's bugs actually lived.
4. Wire into CI alongside `npm run typecheck`.

**Acceptance:**
- `npm run test` runs in CI and fails the build on failure
- Coverage thresholds met; i18n parity enforced
- A test would have caught T-1.2 (demonstrate by reverting the fix locally and observing red)

---

### T-2.6 — Retire the fake verification suite 🟡

**Problem:** `automation/verify_noteai_revamp.py` manufactures false confidence, and `README.md:79` cites it as quality evidence.

**Evidence:** `automation/verify_noteai_revamp.py:34-49` — `check_file_contains()` asserts that source files *match regex patterns*. Example (`:63`): tailwind config contains the string `2563EB`. It executes no application code, starts no server, and issues no request. It reports "100% pass, 26 criteria" while `/editor` 404s, downloads fail, branding is unwired, and RAG leaks across projects.

**This is the most damaging item in the repository** — not because it is wrong, but because it was believed.

**Change:**

1. Delete `automation/verify_noteai_revamp.py`. Do not extend it; the approach is unfixable.
2. Replace with a Playwright smoke suite over real journeys:
   - `smoke/01-shell.spec.ts` — app loads, nav renders, no console errors
   - `smoke/02-project-lifecycle.spec.ts` — create project → upload source → reaches `ready`
   - `smoke/03-generation.spec.ts` — generate a deck → reaches `ready` → PPTX downloads
   - `smoke/04-editor.spec.ts` — Editor opens Presenton with the deck loaded
   - `smoke/05-branding.spec.ts` — branded template produces a deck with the configured colour
3. Run against the compose stack in CI.
4. Update `README.md` to point at the real suites, and state what they do and do not cover.

**Acceptance:**
- The regex script is gone
- Five smoke journeys run against a live stack and pass
- No documentation cites the deleted script

---

### T-2.7 — Reconcile documentation with reality 🟡

**Problem:** the docs describe a product that does not exist, and have been steering debugging in the wrong direction.

**Evidence:**
- `README.md:79` — cites `NOTEAI_TEST_REPORT.md` for "26 criteria, 100% pass"; that file was overwritten on 2026-07-28 with a Presenton debugging report
- `CHANGELOG.md:30` — claims "instant browser downloads" (broken until T-1.5) and "Presenton interactive slide editor" (broken until T-1.2; `SlideEditorModal` is a link launcher, not an editor)
- `README.md:39` — Python 3.14; `backend/pyproject.toml:5` — `>=3.11`
- `.env.lite.example` — still configures `PRESENTON_DOMAIN` / `NEXT_PUBLIC_PRESENTON_UI_URL` for a subdomain model the code no longer uses

**Change:**

1. Rewrite `README.md` to describe what the code does **as of the end of Phase 2**. Where a feature is partial, say so.
2. Correct `CHANGELOG.md` — do not rewrite history; add a correcting entry noting which v2.0.0 claims were aspirational and when they actually landed.
3. Reconcile `.env.lite.example` with the same-origin `/editor` decision; remove dead variables.
4. Add `docs/ARCHITECTURE.md`: the module map, both generation paths, the engine boundaries, and the `/editor` decision with its rationale — so the next person does not re-derive it from eight commits of Traefik iteration.
5. Fix the Python version discrepancy.

**Acceptance:**
- No documentation claim is false as of the Phase 2 commit
- No doc references a deleted file or dead variable
- `docs/ARCHITECTURE.md` exists and records the `/editor` decision

---

## Verification

```bash
# Backend
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
# expect: coverage >= 87% (llm.py 31%→70%+, new isolation + preflight tests)

# Frontend
cd frontend && npm run typecheck && npm run test:coverage

# E2E
npx playwright test

# Health through the proxy
curl -s https://<domain>/api/readyz | jq

# Migrations round-trip
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head

# No stale doc references
grep -rn "verify_noteai_revamp" . --exclude-dir=.git   # → empty
```

### Manual verification

1. **Isolation (T-2.1):** two projects with disjoint sources. Generate a guide for each. Confirm no cross-contamination in summaries or chat citations. **Screenshot both.**
2. **Metering (T-2.2):** note `/usage` count → generate a Studio deck → confirm it incremented.
3. **LLM diagnostics (T-2.3):** set `OPENROUTER_MODEL` to a nonsense slug → attempt generation → confirm the log names the cause.
4. **Health (T-2.4):** stop Presenton → `/api/readyz` reports it degraded while the app stays usable.

---

## Deliverable

`revamp/reports/PHASE-2-REPORT.md`, using [`TEST-REPORT-TEMPLATE.md`](TEST-REPORT-TEMPLATE.md).

Phase 2 is where the report format earns its keep — this is the first phase with all three test tiers, so §4.1/4.2/4.3 are all populated and the coverage delta becomes meaningful.

§8 (facts vs. assumptions) is critical for **T-2.1**: state precisely which isolation option was available, what was verified by test, and what remains inferred. If only post-filtering (Option B) was possible, the residual risk must be written down, not implied.

---

## Exit gate

| # | Criterion |
|---|---|
| **G1** | RAG retrieval is provably scoped to the project; engine-isolation tests pass |
| **G2** | Missing/unfilterable notebook ref yields empty grounding, never unscoped grounding |
| **G3** | Freeform generations appear in `/usage`; quota applies to both paths |
| **G4** | `LlmClient` extends `EngineClient`; failures are diagnosable from logs; coverage ≥ 70% |
| **G5** | `/api/readyz` reachable through Traefik, reporting per-dependency status; all services have healthchecks |
| **G6** | Frontend test tier runs in CI; thresholds met; would have caught T-1.2 |
| **G7** | Regex verification script deleted; 5 Playwright journeys pass against a live stack |
| **G8** | No documentation claim is false; `docs/ARCHITECTURE.md` exists |
| **G9** | Backend coverage ≥ 87%; no previously passing test regressed |

**G1 and G2 are the phase's reason for existing.** Until they pass, `LITE_MODE=false` must not be enabled in any environment holding more than one tenant's data.

---

## Notes for the executor

- **T-2.1 first, and treat it as a security fix**, not a feature. If Open Notebook cannot scope search at all, fail closed and escalate — do not ship unscoped retrieval with a comment acknowledging it.
- **T-2.6 will be uncomfortable.** Deleting a suite that reports 100% feels like losing coverage. It is not: it never tested anything. Five real journeys that can fail are worth more than 26 assertions that cannot.
- **Do not chase a global frontend coverage number.** Cover `api.ts`, `SlideEditorModal`, and `StudioPanel` well; the marketing pages can wait.
- The recurring theme across T-2.1, T-2.3, and T-2.6 is the same one from Phase 1: **this codebase hides failure**. Every change in this phase should make a failure louder than it was.
