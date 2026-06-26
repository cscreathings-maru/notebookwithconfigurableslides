# Deliverables Assessment & Test Plan — Presentation Notebook LLM (MVP)

**Date:** 2026-06-23 · **Scope:** `backend/`, `frontend/`, `deploy/`, `specs/001-presentation-notebook-llm/`, `metagpt/prompts/`
**Basis:** spec.md (FR-001…FR-020, SC-001…SC-006, US1–US5), plan.md, tasks.md (T001–T052), data-model.md, contracts/, MVP slices 0–5.

---

## Part 1 — Assessment

### 1.1 Evidence captured

| Signal | Result |
|--------|--------|
| Backend test suite (`pytest -q`) | **45 passed**, 0 failed (contract + integration + eval + unit) |
| Frontend production build (`npm run build`) | **Success**, 8 routes compiled, ~87 kB shared JS (within landing budget) |
| Backend source | 68 modules, ~5,167 LOC; all 6 slices represented |
| Frontend source | 27 modules, ~2,356 LOC; all 5 surfaces present |
| Alembic migrations | 4 files, 10 `create_table` — covers every entity in data-model.md |
| Docker Compose | All planned services (traefik, frontend, orchestrator, worker, postgres, redis, minio, ollama, surrealdb, open-notebook, presenton) with correct isolation topology |

### 1.2 Slice / user-story coverage

| Slice | User story | Status | Evidence |
|-------|-----------|--------|----------|
| 0 — Platform skeleton | US4 + foundation | ✅ Implemented | OIDC (real JWKS + dev HS256 fallback `auth/oidc.py`), tenant-scoped repo with 404-on-cross-tenant (`tenancy/repository.py`), RBAC (`tenancy/rbac.py`), Arq job framework (`jobs/service.py`, `workers/`), circuit-breaker engine clients (`engines/`), encrypted BYOK (`tenancy/llm_config.py`, `core/crypto.py`), Next.js shell |
| 1 — Ingestion | US1 inputs | ✅ Implemented | Project↔ON notebook, Source upload→MinIO→ingest job→analysis→status (`ingestion/`, `workers/tasks.py:run_ingest`), tenant-prefixed object keys |
| 2 — Registry | US2 | ✅ Implemented | Versioned profiles/templates, **immutability guard** (`VersionInUseError` 409), PPTX import via Presenton, approval gate (`registry/service.py`), admin frontend editors |
| 3 — Generation | US1 core | ✅ Implemented (1 gap) | Outline schema/validator, **deterministic** controlled builder (`outline/builder.py`), param mapper (`generation/mapper.py`), worker PPTX+PDF→MinIO (`generation/worker.py`), consistency checker, provenance + usage. **Gap: consistency check inspects the plan, not the artifact — see 1.4** |
| 4 — Refine + provenance | US3 | ✅ Implemented | Edit-outline→regenerate **without re-ingest** (proven by `test_refine_history.py:170`), version history with full provenance |
| 5 — Usage & audit | US5 | ✅ Implemented | Metering rollups, quota block/flag (`metering/quota.py`), audit events, usage/audit APIs, admin dashboard + quota indicator |

### 1.3 Requirement-level scorecard

| FR | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-001 | Create project, attach multi-format sources | ✅ | pdf/office/csv/text/url in `ingestion/kinds.py` |
| FR-002 | Ingest/analyze via Open Notebook, reusable artifacts | ✅ | `analysis_ref` stored; scoped to project/tenant |
| FR-003 | Per-source status; block generation if not ready | ✅ (fixed) | Now blocks only while analysis is *in progress*; proceeds from ready sources, skips failed ones with a logged warning, blocks if none ready (`generation/service.py`) |
| FR-004 | Define stakeholder profiles (all fields) | ✅ | Full field set in model + editor |
| FR-005 | Versioned registry; edits never mutate used versions | ✅ | New-version-on-edit + in-use immutability |
| FR-006 | Register templates incl. import-from-PPTX | ✅ | `TemplateService.create` w/ presigned PPTX → Presenton import |
| FR-007 | Profiles/templates tenant-scoped | ✅ | Enforced by base repo |
| FR-008 | Structured outline + schema validation | ✅ | `outline/schema.py`, `validator.py`, repair path |
| FR-009 | Generate via Presenton w/ profile params, PPTX+PDF | ✅ | Mapper + worker; pptx then pdf export |
| FR-010 | Consistency check on each **generated deck** | ✅ (fixed) | Now parses the produced PPTX (`generation/artifact.py`) and verifies real slide count, section titles in order, and banned content against the deck; corrupt/unreadable decks fail the gate (`generation/consistency.py`) |
| FR-011 | Preview/edit outline + instructions, regenerate w/o re-ingest | ✅ | Slice 4 |
| FR-012 | Persist provenance + version history | ✅ | Generation stores sources/profile_v/template_v/model/params |
| FR-013 | Async, visible progress, idempotent, resumable | ✅ | Arq + Job model + idempotency key + resumable worker |
| FR-014 | OIDC SSO, admin/author/viewer roles | ✅ | Real JWKS validation; dev mode for local |
| FR-015 | Server-side tenant resolution, no cross-tenant access | ✅ | Tenant derived from token; 404 on cross-tenant |
| FR-016 | Engines on private network only | ✅ | Compose: only traefik publishes a port |
| FR-017 | Per-tenant BYOK, encrypted, region routing | ✅ | Encrypted config; provider passed per-call |
| FR-018 | Audit trail of generation + admin actions | ⚠️ | Generation + registry + quota audited; **auth/login events not audited** (T019) — deferred: login is handled by the external OIDC IdP, so there is no login event inside the orchestrator to audit (see Remediation log G5) |
| FR-019 | Meter tokens/cost per generation + tenant, quotas + alerts | ✅ | Metering + quota + alert sink |
| FR-020 | Editable PPTX + PDF in tenant-isolated storage, signed retrieval | ✅ | Signed presigned GET, tenant-prefixed keys |

### 1.4 Gaps, risks, and deviations

| # | Finding | Severity | Detail | Recommendation |
|---|---------|----------|--------|----------------|
| G1 | **Consistency check validates the plan, not the artifact** | **HIGH** | `generation/worker.py` calls `check_consistency` with `n_slides` = *requested* count and `template_ref_applied == template_ref_requested` (same value → trivially passes). Section presence is checked against the deterministic outline, not the PPTX Presenton returned. FR-010/SC-003 intend a check on the *produced deck*. | Parse the returned PPTX (e.g. `python-pptx`): assert actual slide count, section/title slides, and template/theme markers. Keep the plan-check as a pre-flight, add an artifact-check post-download. |
| G2 | **Partial-ingest policy conflict** | MEDIUM | Spec edge case: generation "proceeds only from successfully processed sources, with a warning." Implementation blocks if *any* source is not `ready`. FR-003 is satisfied; the edge-case behavior is not. | Decide product intent. If proceed-with-warning is wanted, filter to `ready` sources and attach a warning to the generation; else update spec to reflect strict block. |
| G3 | **No frontend E2E tests** | MEDIUM | Plan/tasks call for Playwright E2E (`frontend/tests/`, T020/T034/T039/T043/T047); no `frontend/tests` dir and Playwright is not a dependency. | Add Playwright with the smoke flows in Part 2 (TC-E01…E06). |
| G4 | **Coverage target not verified** | MEDIUM | Constitution/testing rule sets 80% min; suite passes but no coverage report is produced/recorded. | Run `pytest --cov=src --cov-report=term-missing`; record %; close gaps. |
| G5 | **Auth events not audited** | LOW-MED | `api/auth.py` writes no AuditEvent on login; T019/FR-018 mention auth audit. | Emit `auth.login` / `auth.denied` audit events. |
| G6 | **Generation status granularity** | LOW | data-model defines `analyzing/building_outline/validating`; worker only uses `generating→ready/failed`. Progress UX is coarser than modeled. | Set intermediate statuses for richer progress polling. |
| G7 | **Quota counts may include failed generations** | LOW | `QuotaService.used_this_month` counts all `Generation` rows in month, incl. failed/flagged. | Decide whether failed decks consume quota; filter by status if not. |
| G8 | **Edge cases not demonstrably handled in orchestrator** | LOW | OCR for scanned PDFs, large-corpus retrieval fallback, Presenton "queue position" are engine-side or unproven. | Confirm engine behavior; add orchestrator-side messaging/tests where it owns the UX. |

### 1.4a Remediation log (fixes applied this session)

| # | Status | What changed | Tests |
|---|--------|-------------|-------|
| G1 | ✅ Fixed | Added `generation/artifact.py` (`inspect_pptx` → `DeckFacts`); rewrote `generation/consistency.py` to judge the **produced PPTX** (real slide count, section titles in order, banned content in deck text, template-applied, corrupt-deck rejection); worker reads bytes back via new `ObjectStore.get_bytes` and sets a `validating` status. `python-pptx` added to deps. | `tests/unit/test_consistency_artifact.py` (6 cases); `FakePresenton` now emits a real PPTX honoring `n_slides` so existing pipeline tests exercise the real check |
| G2 | ✅ Fixed | `generation/service.py`: block only while sources are *in progress*; proceed from ready sources skipping failed ones (logged + recorded in audit as `skipped_failed_source_ids`); new `no_ready_sources` 409 when nothing is ready. Provenance records only ready sources. | `test_generation.py`: `…proceeds_from_ready_and_skips_failed_sources`, `…blocked_when_no_source_is_ready` |
| G4 | ✅ Measured | Ran `pytest --cov`: **85%** overall (≥ 80% target). Remaining gaps are infra boundaries (Arq `workers/tasks.py`, MinIO client) covered via fakes/integration. | coverage report |
| G6 | ◑ Partial | Worker now sets intermediate `validating` status before the consistency gate. `analyzing`/`building_outline` still unused (outline is built in a separate synchronous endpoint, not the generate job). | existing |
| G7 | ✅ Fixed | `metering/quota.py`: `used_this_month` now excludes `failed` generations so a failed deck does not consume quota. | existing usage/audit suite still green |
| G3 | ▢ Deferred | Frontend Playwright E2E not added (requires a running stack + new tooling); smoke specs are enumerated in Part 2 TC-E01…E06 as the implementation guide. | — |
| G5 | ▢ Deferred (by design) | Auth/login events are owned by the external OIDC IdP; there is no in-orchestrator login callback to audit. Could add `auth.denied` audit on RBAC 403s if desired. | — |
| G8 | ▢ Deferred | Engine-side edge behaviors (OCR, large-corpus fallback, Presenton queue position) — verify against live engines. | live-engine pass |

**Suite after fixes: 53 passed (was 45). Backend coverage 85%. Frontend build still clean.**

### 1.5 Quality & readiness

- **Architecture quality: high.** Clean separation (api / service / repository / engines), tenant isolation enforced by construction, immutability guards, idempotent resumable workers, structured logging + correlation id, consistent error envelope. Matches the constitution's 5 principles.
- **Code style:** small focused modules (well under the 800-line cap), typed signatures, docstrings explaining intent and invariants.
- **Readiness verdict:** **Pilot-ready for the happy path** of all five stories, contingent on closing **G1** (artifact-level consistency is the product's core differentiator and SC-003 metric) and validating against the **live** Open Notebook / Presenton engines (current tests use fakes/stubs — see Assumption A2). Multi-tenant isolation, RBAC, versioning, and provenance are robust and well-tested.

---

## Part 2 — Test Plan

### 2.1 Test objectives

1. Verify each FR and user-story acceptance scenario against the implemented deliverables.
2. Validate the MVP success criteria (SC-001…SC-006), especially determinism (SC-002) and consistency (SC-003).
3. Prove tenant isolation and RBAC have no bypass (SC-005).
4. Exercise edge and negative cases from spec §Edge Cases.
5. Surface the gaps in 1.4 as explicit failing/blocked test cases so they are tracked.

### 2.2 Scope

**In scope:** orchestrator API + services, async workers, tenant isolation/RBAC, registry versioning, outline determinism, generation pipeline, consistency gate, refine/provenance, metering/quota/audit, frontend smoke flows, deployment bring-up.

**Out of scope:** internal behavior of Open Notebook and Presenton (treated as pinned external engines, covered only at the contract boundary); load/scale beyond pilot targets; penetration testing beyond cross-tenant/RBAC.

### 2.3 Assumptions & dependencies

| ID | Assumption / dependency |
|----|--------------------------|
| A1 | `OIDC_DEV_MODE=true` available for test auth; HS256 token signed with `ORCH_SECRET_KEY`. |
| A2 | Contract/integration tests run against **fakes** (`tests/fakes.py`); a separate **live-engine** pass against pinned Open Notebook `v1-latest` + Presenton `latest` is required before pilot sign-off. |
| A3 | Postgres, Redis, MinIO reachable (or SQLite/in-memory + fakes per existing `conftest.py`). |
| A4 | A tenant is seeded with BYOK provider config (`scripts/seed_tenant.py`). |
| A5 | At least one approved Template and approved Profile exist before generation tests. |
| A6 | DeepSeek (or OpenAI-compatible) endpoint reachable for live-engine pass only. |

### 2.4 Test scenarios (high level)

| Scenario | Maps to |
|----------|---------|
| S1 Multi-tenant isolation & RBAC | US4, FR-014/015, SC-005 |
| S2 Ingestion lifecycle & status | US1-inputs, FR-001/002/003 |
| S3 Registry versioning & immutability | US2, FR-004/005/006/007 |
| S4 Outline build & determinism | US1, FR-008, SC-002 |
| S5 Generation, artifacts & consistency | US1, FR-009/010/020, SC-001/003 |
| S6 Refine & provenance | US3, FR-011/012/013 |
| S7 Usage, quota & audit | US5, FR-018/019 |
| S8 Security / engine isolation / BYOK | FR-016/017, SC-005 |
| S9 Frontend smoke & accessibility | US1–US5 UI |
| S10 Deployment bring-up | tasks T005/T052 |

### 2.5 Detailed test cases

> Priority: **H**igh / **M**edium / **L**ow. Each case maps to a requirement/story/slice.

#### S1 — Multi-tenant isolation & RBAC (US4)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S1-01 | FR-015, SC-005, US4-AS1 | Tenants A & B, each with 1 project | As A's token, `GET /projects/{B_project_id}` | `404` (not 403); attempt logged | H |
| TC-S1-02 | FR-015 | Same | As A, try `GET /generations/{B_gen_id}`, `/sources/{B_src}`, `/outlines/{B_outline}` | All `404` | H |
| TC-S1-03 | FR-014, US4-AS2 | Viewer user in A | Viewer `POST /projects`, `POST /profiles`, `POST /generations` | `403` RBAC denied | H |
| TC-S1-04 | FR-014 | Author user in A | Author `POST /profiles` (admin-only) | `403` | H |
| TC-S1-05 | FR-014 | Valid admin token | `GET /auth/me` | Returns user, tenant, role | H |
| TC-S1-06 (neg) | FR-014 | — | Call any endpoint with expired/garbage bearer | `401` UnauthorizedError | H |
| TC-S1-07 (edge) | FR-015 | A & B share a logical profile name | Author in A lists profiles | Only A's profiles returned; never B's | M |

#### S2 — Ingestion (US1 inputs)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S2-01 | FR-001/002 | Author, project, BYOK set | Upload a PDF → poll source | Source `queued`→`processing`→`ready`; `analysis_ref` stored | H |
| TC-S2-02 | FR-001 | Author, project | `POST /sources {url}` | URL source created + ingest job enqueued | M |
| TC-S2-03 | FR-003 | Source in `processing` | `POST /generations` | `409 sources_not_ready` | H |
| TC-S2-04 (neg) | Edge: corrupt file | Author, project | Upload corrupt/unsupported file | Source `failed` with `error`; project remains usable | H |
| TC-S2-05 (neg) | FR-002 | Tenant w/o BYOK config | Upload + ingest | Source `failed` "No LLM provider configured" (terminal, not retried) | M |
| TC-S2-06 | FR-013 | Transient ON error injected | Run ingest job | Job retries (attempts↑); leaves resumable state, no corrupt source | H |
| TC-S2-07 (sec) | data-model inv.5 | Ready source | `GET /sources/{id}` body | No `on_source_id`/`on_notebook_id` exposed | H |
| TC-S2-08 (edge) | Edge: mixed language | ID + EN source, profile language=EN | Build outline | Output language follows profile, not source | M |

#### S3 — Registry versioning (US2)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S3-01 | FR-005, US2-AS1 | Admin | Create profile → `PUT` edit | New `version` row; prior version unchanged | H |
| TC-S3-02 | FR-005, US2-AS3 | Profile v1 used by a Generation | `POST /profiles/{id}/approve` on the in-use version | `409 version_in_use` | H |
| TC-S3-03 | FR-006, US2-AS2 | Admin + PPTX file | `POST /templates` with PPTX | Template registered; `presenton_template_ref` stored, not exposed | H |
| TC-S3-04 | FR-004 | Admin | Create profile binding a **draft** template | `400 template_not_approved` | M |
| TC-S3-05 | FR-007 | Author | `GET /profiles` | Only `approved` profiles returned to author | M |
| TC-S3-06 (neg) | governance | Admin | Approve an `archived` version | `409 invalid_transition` | L |
| TC-S3-07 (sec) | inv.5 | Any | Template/profile response bodies | No engine refs leaked | H |

#### S4 — Outline & determinism (US1)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S4-01 | SC-002, FR-008 | Profile w/ 4-section structure, ready sources | `POST /projects/{id}/outline {profile_id}` twice | Identical section set **and order** both runs (wording may differ) | H |
| TC-S4-02 | FR-008 | LLM returns malformed JSON | Build outline | Validator repairs onto required structure or fails cleanly (no partial) | H |
| TC-S4-03 | FR-008 | Profile w/ empty `section_structure` | Build outline | `ValidationError` — cannot build | M |
| TC-S4-04 | FR-008 | Built outline | `PUT /outlines/{id} {content}` invalid (extra/renamed section) | Re-validated; `valid=false` returned, generation blocked | H |
| TC-S4-05 | inv.5 | Built outline | Inspect talking points | Every `talking_point.section_id` references a real section | M |

#### S5 — Generation, artifacts & consistency (US1)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S5-01 | FR-009/020, SC-001, US1-AS1 | Valid outline, ready sources, approved template | `POST /generations` → poll → download | PPTX + PDF produced; `GET /download?format=pptx\|pdf` returns signed URL | H |
| TC-S5-02 | SC-002, US1-AS2 | Same project+profile+template_v | Generate twice | Same slide sections + ordering both decks | H |
| TC-S5-03 | FR-010, SC-003 | **Artifact-level** (G1) | Generate, then inspect the actual PPTX | Slide count within range, required sections present **in the deck**, template/theme applied | H |
| TC-S5-04 | FR-010 | Outline w/ banned term ("TBD") | Generate | Consistency `passed=false`; status `failed`, flagged for review | H |
| TC-S5-05 | FR-010 | n_slides outside profile range | Generate | `slide_count_in_range` check fails → blocked | M |
| TC-S5-06 | FR-013 | Transient Presenton error injected | Run generate job | Retries; no corrupt artifact; resumes without re-calling generate if `presenton_presentation_id` already set | H |
| TC-S5-07 | US1-AS3 | A source still `processing` | `POST /generations` | `409`, no partial deck | H |
| TC-S5-08 (neg) | FR-020 | Generation not ready | `GET /download` | `400` "not ready for download" | M |
| TC-S5-09 (sec) | inv.5 | Ready generation | Response + history bodies | `edit_path`, `presenton_*`, `template` ref never exposed | H |
| TC-S5-10 (perf) | SC-001 | 15–25 page source set | Time upload→download (live pass) | p50 < 5 min, p95 < 10 min | M |

#### S6 — Refine & provenance (US3)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S6-01 | FR-011, US3-AS1 | Generated deck | Edit one section title + reduce slides → regenerate | New deck reflects edit; **no** new `add_source` (no re-ingest) | H |
| TC-S6-02 | FR-012, US3-AS2 | ≥2 generations | `GET /projects/{id}/generations` | History lists profile_v, template_v, model, provider, params, created_by/at, status | H |
| TC-S6-03 | Edge: version pinning | Profile edited mid-flight | Regenerate from old outline | Uses versions pinned at job start; past generations unchanged | M |
| TC-S6-04 | US3 | Two generations | Structural diff (frontend) | Section set/order diff shown | L |

#### S7 — Usage, quota & audit (US5)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S7-01 | FR-019, US5-AS1 | Several generations | `GET /usage?from=&to=` | Correct per-user & per-tenant counts, tokens, est. cost | H |
| TC-S7-02 | FR-019, US5-AS2 | Tenant at `quota_monthly_generations`, policy=block | `POST /generations` | `429 quota_exceeded`; `quota.exceeded` audit written; alert emitted | H |
| TC-S7-03 | FR-019 | Same, policy=flag | `POST /generations` | Allowed but flagged; event recorded | M |
| TC-S7-04 | FR-018 | Any mutating/admin action | `GET /audit?from=&to=` | Each action present (actor, tenant, action, resource+versions, ts) | H |
| TC-S7-05 (sec) | slice-5 constraint | Audit log | Inspect entries | No secrets/keys logged | H |
| TC-S7-06 (edge) | G7 | Failed generation in month | Check quota usage | Confirm policy: does a failed deck consume quota? | L |

#### S8 — Security, engine isolation & BYOK

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-S8-01 | FR-016 | Compose up | Attempt to reach open-notebook/presenton from host | No published port; unreachable | H |
| TC-S8-02 | FR-017 | Tenant BYOK | Inspect DB `llm_config_enc` | Stored encrypted; decrypts only server-side | H |
| TC-S8-03 | FR-017 | 2 tenants, different providers | Generate in each | Each routed to its own provider config | M |
| TC-S8-04 (sec) | SC-005 | — | Fuzz resource IDs across tenants via API | 100% 404, zero cross-tenant leakage | H |

#### S9 — Frontend smoke (Playwright — to be added, G3)

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-E01 | US4 | App running | Visit `/login`, authenticate | Redirect to authenticated layout; role-aware nav | H |
| TC-E02 | US1 | Author | Project → upload → see status | Source status renders live | H |
| TC-E03 | US1 | Author | Pick profile → preview outline → Generate → download | Deck downloads | H |
| TC-E04 | US2 | Admin | Create profile (section builder) + import template | Saved + selectable | M |
| TC-E05 | US5 | Admin | Open usage dashboard + quota indicator | Counts/cost render | M |
| TC-E06 (a11y) | web/testing | Any | Keyboard nav + reduced-motion + contrast at 320/768/1024/1440 | No overflow; passes automated a11y | M |

#### S10 — Deployment bring-up

| ID | Req/Story | Preconditions | Steps | Expected result | Pri |
|----|-----------|---------------|-------|-----------------|-----|
| TC-D01 | T005/T052 | Filled `deploy/.env` | `docker compose up -d` + run `quickstart.md` | All services healthy; only port 80 published | H |
| TC-D02 | T006 | DB up | `alembic upgrade head` | All 10 tables created | H |
| TC-D03 | T018 | Stack up | `seed_tenant.py` | Tenant + admin user + BYOK seeded | M |

### 2.6 Edge cases (consolidated from spec §Edge Cases)

| Edge | Covered by | Status |
|------|-----------|--------|
| Source fails to ingest | TC-S2-04 | Implemented (per-source fail) — but "proceed with warning" path G2 open |
| LLM timeout / rate-limit mid-generation | TC-S5-06 | Retry/backoff + resumable implemented |
| Presenton busy/unavailable (queue position) | TC-S5-06 (partial) | Retry yes; "report queue position" unverified (G8) |
| Scanned/image-only PDF (OCR) | TC-S2-04 variant | Engine-side; orchestrator flags non-analyzable — verify (G8) |
| Corpus exceeds model context | — | Retrieval fallback unproven (G8) |
| Mixed-language sources | TC-S2-08 | Output language from profile — covered |
| Template/profile edited mid-generation | TC-S6-03 | Version pinned at job start — covered |

### 2.7 Negative test cases (consolidated)

TC-S1-03/04/06, TC-S2-03/04/05, TC-S3-02/04/06, TC-S4-02/03/04, TC-S5-04/05/07/08, TC-S7-02.

### 2.8 Acceptance criteria (exit gate for pilot sign-off)

| AC | Criterion | Tied to |
|----|-----------|---------|
| AC-1 | All **High** cases pass; no cross-tenant leak in TC-S8-04 | SC-005 |
| AC-2 | TC-S4-01 + TC-S5-02 show identical structure across ≥20 runs (≥95%) | SC-002 |
| AC-3 | **Artifact-level** consistency (TC-S5-03) passes for ≥90% of generated decks after G1 fix | SC-003 |
| AC-4 | TC-S5-01 + TC-S5-10 complete document→deck p95 < 10 min (live pass) | SC-001 |
| AC-5 | Every generation in TC-S6-02 carries complete provenance | SC-005 |
| AC-6 | No failed job left in corrupt state across TC-S2-06/TC-S5-06 | SC-006 |
| AC-7 | Backend coverage ≥ 80% (G4); frontend smoke E2E (G3) green | testing rule |
| AC-8 | G1 (artifact consistency) and G2 (partial-ingest policy) resolved or formally accepted | 1.4 |
