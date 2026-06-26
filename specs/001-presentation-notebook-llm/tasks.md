---
description: "Task list for Presentation Notebook LLM (MVP)"
---

# Tasks: Presentation Notebook LLM Platform (MVP)

**Input**: Design documents from `/specs/001-presentation-notebook-llm/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — the constitution mandates contract tests and an eval suite (Principle IV).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency)
- **[Story]**: US1–US5 from spec.md
- Web-app paths: `backend/src/`, `frontend/src/`, `deploy/`

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create `backend/`, `frontend/`, `deploy/` structure per plan.md
- [ ] T002 Init FastAPI backend (Python 3.11, pyproject, SQLAlchemy, Alembic, httpx, Arq/Celery)
- [ ] T003 [P] Init Next.js + TypeScript + Tailwind frontend
- [ ] T004 [P] Configure linting/formatting/type-checks (ruff, mypy, eslint, prettier)
- [ ] T005 Author `deploy/docker-compose.yml` (orchestrator, postgres, redis, minio, traefik, open-notebook+surrealdb, presenton) and `.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ No user story work begins until this phase is complete.**

- [ ] T006 Postgres schema + Alembic migrations for all entities in `backend/src/models/` (data-model.md)
- [ ] T007 [P] OIDC auth + session validation; `GET /auth/me` in `backend/src/api/auth.py`
- [ ] T008 Tenant-context middleware + RBAC guard (admin/author/viewer); server-side tenant resolution in `backend/src/services/tenancy/`
- [ ] T009 [P] Tenant-scoped repository base (mandatory `tenant_id` filter; 404 on cross-tenant)
- [ ] T010 [P] Engine clients with timeout/retry/circuit-breaker in `backend/src/services/ingestion/on_client.py` and `backend/src/services/generation/presenton_client.py`
- [ ] T011 Async job framework (Arq/Celery + Redis): `Job` model, idempotency, progress, `GET /jobs/{id}`
- [ ] T012 [P] Structured logging + tracing (correlation id) + error handling in `backend/src/core/`
- [ ] T013 [P] Encrypted per-tenant LLM config storage (BYOK) in `backend/src/services/tenancy/secrets.py`
- [ ] T014 MinIO client + tenant-prefixed object storage helper
- [ ] T015 Contract-test harness scaffolding (pinned ON + Presenton versions) in `backend/tests/contract/`

**Checkpoint**: foundation ready → user stories can proceed.

---

## Phase 3: User Story 4 — Multi-tenant onboarding, access, isolation (P1) 🎯 Foundation-critical

> Implemented first because isolation is a release blocker and all other stories depend on it.

- [ ] T016 [P] [US4] Contract test: cross-tenant access returns 404 in `backend/tests/contract/test_isolation.py`
- [ ] T017 [P] [US4] Integration test: viewer cannot mutate in `backend/tests/integration/test_rbac.py`
- [ ] T018 [US4] Tenant + User APIs and onboarding/seed script in `backend/src/api/tenants.py`, `backend/scripts/seed_tenant.py`
- [ ] T019 [US4] RBAC enforcement across routers; audit on auth events
- [ ] T020 [P] [US4] Frontend: login (OIDC), tenant switcher, role-aware nav in `frontend/src/app/`

**Checkpoint**: auth + isolation verifiable.

---

## Phase 4: User Story 1 — Generate a stakeholder-tailored deck (P1) 🎯 MVP

**Goal**: documents → on-template, stakeholder-appropriate PPTX/PDF.

Depends on US2 registry (profiles/templates) and ingestion; build ingestion here, registry in US2.

### Tests

- [ ] T021 [P] [US1] Contract test: Presenton generate mapping in `backend/tests/contract/test_presenton.py`
- [ ] T022 [P] [US1] Contract test: Open Notebook ingest/analyze in `backend/tests/contract/test_open_notebook.py`
- [ ] T023 [P] [US1] Eval: same project+profile+template version → identical section structure in `backend/tests/eval/test_consistency.py`
- [ ] T024 [P] [US1] Integration test: upload→analyze→outline→generate→download in `backend/tests/integration/test_pipeline.py`

### Implementation — ingestion

- [ ] T025 [P] [US1] `Project` + `Source` models/services; project creates ON notebook
- [ ] T026 [US1] Source upload API + ingest job (status, errors) in `backend/src/api/sources.py`, `backend/src/workers/ingest.py`
- [ ] T027 [US1] Block generation unless all sources `ready`

### Implementation — outline + generation

- [ ] T028 [US1] Outline JSON schema + validator in `backend/src/schemas/outline.py`
- [ ] T029 [US1] Outline builder (controlled prompt: analysis + profile) in `backend/src/services/outline/`
- [ ] T030 [US1] Profile→Presenton param mapper in `backend/src/services/generation/mapper.py`
- [ ] T031 [US1] Generation API + generate job (PPTX+PDF → MinIO) in `backend/src/api/generations.py`, `backend/src/workers/generate.py`
- [ ] T032 [US1] Consistency checker (sections, slide-count, template, banned content) in `backend/src/services/consistency/`
- [ ] T033 [US1] Provenance + UsageRecord on every generation
- [ ] T034 [P] [US1] Frontend: uploader, profile picker, outline preview, generate, download in `frontend/src/app/projects/`

**Checkpoint**: core value loop works end-to-end.

---

## Phase 5: User Story 2 — Profiles & templates registry (P1)

### Tests

- [ ] T035 [P] [US2] Contract test: profile/template versioning immutability in `backend/tests/contract/test_registry.py`

### Implementation

- [ ] T036 [P] [US2] Versioned `StakeholderProfile` model/service (new version on edit) in `backend/src/services/registry/`
- [ ] T037 [P] [US2] Versioned `Template` model/service + Presenton template registration (incl. import-from-PPTX)
- [ ] T038 [US2] Profiles/Templates admin APIs + approval gate in `backend/src/api/profiles.py`, `backend/src/api/templates.py`
- [ ] T039 [P] [US2] Frontend: profile editor (structure, tone, verbosity, language), template manager in `frontend/src/app/admin/`

**Checkpoint**: governed profiles/templates drive US1.

---

## Phase 6: User Story 3 — Review, refine, re-generate (P2)

- [ ] T040 [P] [US3] Integration test: edit outline → regenerate reuses analysis in `backend/tests/integration/test_refine.py`
- [ ] T041 [US3] Outline edit API (re-validate) + regenerate without re-ingest
- [ ] T042 [US3] Generation version history + provenance view API
- [ ] T043 [P] [US3] Frontend: outline editor, version history, deck preview/diff

**Checkpoint**: iteration without re-analysis.

---

## Phase 7: User Story 5 — Usage, cost, audit (P3)

- [ ] T044 [P] [US5] Token/cost metering per generation + per-tenant rollup in `backend/src/services/metering/`
- [ ] T045 [US5] Quota enforcement (block/flag) + alerts
- [ ] T046 [US5] Usage + Audit APIs in `backend/src/api/usage.py`
- [ ] T047 [P] [US5] Frontend: admin usage/audit dashboard

---

## Phase 8: Polish & Cross-Cutting

- [ ] T048 [P] Backups for postgres, surrealdb, minio, presenton `app_data` in `deploy/ops/`
- [ ] T049 Presenton instance pool + queue concurrency tuning
- [ ] T050 [P] Observability dashboards (latency, cost, job success) 
- [ ] T051 Security hardening (secrets, network policy, signed download URLs)
- [ ] T052 Run `quickstart.md` validation end-to-end

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2, blocking)** → user stories.
- **US4 (isolation)** first — everything depends on tenant context + RBAC.
- **US1** needs ingestion (built in US1) and the registry from **US2**; in practice build US2 in
  parallel with US1's outline/generation, landing T036–T038 before T029–T031 are fully wired.
- **US3** depends on US1; **US5** depends on US1 (for events to meter).
- **Polish** last.

### Parallel opportunities

- All `[P]` tasks touch different files and can run concurrently.
- After Phase 2, US2 and US1-ingestion can be staffed in parallel; US3/US5 after US1.

## MetaGPT mapping

Each phase/story maps to a prompt in `metagpt/prompts/` (slice-0 … slice-5). Generate per slice,
review against the relevant `contracts/` + this list, then integrate. See `metagpt/OPERATOR-GUIDE.md`.

## Notes

- Write tests first; verify they fail before implementing (constitution Principle IV).
- Never expose engine ids/URLs to clients.
- Commit per task or logical group; stop at each checkpoint to validate the story independently.
