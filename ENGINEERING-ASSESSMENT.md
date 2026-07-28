# NoteAI — Engineering Assessment & Recovery Plan

**Assessed:** 2026-07-28
**Commit:** `b1e12de` (main, 31 commits) + 2 uncommitted working-tree changes
**Scope:** full repository, `NOTEAI_TEST_REPORT.md` validation, architecture & code quality, root-cause analysis, roadmap
**Method:** static reading of every source module, backend test suite executed locally, git history review. No VPS/runtime access — runtime-dependent claims are flagged.

---

## 1. Executive Summary

### Health score

| Layer | Score | Note |
|---|---|---|
| Backend core (config, errors, tenancy, repos, jobs, models) | **8 / 10** | Genuinely well-engineered. Clean, documented, tested. |
| Backend test suite | **7 / 10** | 61 pass, 1 skip, 83% coverage — but concentrated on governed paths. |
| Domain services (outline, registry, guide, chat) | **6.5 / 10** | Sound structure; several silent-failure paths. |
| **Engine integration seams (Presenton, Open Notebook, MinIO)** | **3 / 10** | Where every real failure lives. |
| **Frontend** | **4 / 10** | Zero tests. Two of the headline features are non-functional. |
| **Deployment / infra** | **2.5 / 10** | Core engine unversioned; no healthchecks; structurally impossible routing. |
| Documentation accuracy | **3 / 10** | README/CHANGELOG describe features that do not work as claimed. |
| **Overall** | **≈ 5 / 10** | Strong skeleton, broken joints. |

### The single most important finding

**The product's namesake feature is not wired up.** `brand_tokens` — every colour, font, and aspect-ratio value collected by the 4-section Template Configurator, plus the AI token-extraction onboarding — is written to Postgres (`backend/src/registry/service.py:108`) and **never sent to Presenton**. Neither mapper includes it:

- `backend/src/generation/mapper.py:56-68` (governed path) sends only `template: presenton_template_ref`
- `backend/src/generation/freeform_mapper.py:58-77` (Studio path) sends only `params["template"] = template_ref`
- `PresentonClient.register_template()` (`backend/src/engines/presenton.py:60-90`) accepts only `name` and `source_pptx_path`

The repository is called *notebookwithconfigurableslides*. The slides are not, in fact, configurable. This is a **wiring gap, not a design flaw** — the data is all there and correctly modelled.

### Main risks

1. **`presenton-custom` is not in version control.** `deploy/docker-compose.lite.yml:160` builds from `../presenton-custom`. That directory has *never* been tracked (`git log --all -- "*presenton-custom*"` is empty) and does not exist on this machine. The slide-rendering engine — the component consuming 8 of the last 10 commits — exists only as mutable state on one VPS. **If that box is lost, the product is unrecoverable.**
2. **RAG retrieval is globally scoped**, leaking content across projects (and, in SaaS mode, across tenants).
3. **Two Next.js applications cannot share one origin.** The routing approach the team is currently iterating on cannot be made to work.
4. **Documentation asserts quality that was never measured**, which has been steering debugging effort in the wrong direction.

### Overall recommendation

> **Do not rewrite. Repair six specific seams, then re-point the architecture at the actual product goal.**

The backend core is above average for a project of this age — unconditional tenant filtering by construction, a consistent error envelope, circuit-breaker + backoff on engine calls, immutable registry versioning, 83% coverage. That foundation is worth keeping.

Failures are **not distributed** — they cluster at a small number of integration boundaries. A rewrite would discard the good 70% to fix the bad 30%, and would reproduce the same integration bugs, because those bugs come from the *external* engines and the deployment topology, not from this codebase's structure.

The one genuine architectural question is **goal drift** (§5.4), and that is resolved by deleting scope, not by rewriting.

---

## 2. Repository Architecture Report

### 2.1 System overview

```
Browser
  │
  ▼
Traefik  ── PathPrefix(/)      p1  ──►  frontend      (Next.js 14, standalone)
           PathPrefix(/api)    p10 ──►  orchestrator  (FastAPI, /api/v1)
           PathPrefix(/editor) p20 ──►  presenton     (Next.js + Python — NOT IN REPO)
                    │
                    ▼
        ┌───────────┴──────────────────────────────┐
        │           orchestrator (system of record) │
        │  Postgres · Redis/Arq · MinIO             │
        └───────────┬──────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  open-notebook            presenton
  (SurrealDB, embeddings)  (deck rendering)
```

Only the orchestrator is a public API surface. Engine URLs, credentials, `presenton_presentation_id`, and MinIO keys are deliberately never serialized to clients — a well-held invariant (`backend/src/api/generations.py:39-54`).

### 2.2 Module map (backend, ~6,760 LOC src / 2,508 LOC tests)

| Package | Responsibility | Health |
|---|---|---|
| `core/` | config, db session, errors, logging, correlation, crypto, lite identity | **Strong.** `errors.py` is exemplary. |
| `auth/` | OIDC validation → `Principal`; lite-mode bypass | Strong; single authority for tenant. |
| `tenancy/` | `TenantScopedRepository` (isolation enforcement point), RBAC, BYOK config | **Strong.** Isolation holds by construction. |
| `models/` + `schemas/` | SQLAlchemy models / Pydantic DTOs | Clean split, portable column types. |
| `ingestion/` | project + source lifecycle, Open Notebook push, polling | Good, but `run_transformation` is a no-op. |
| `registry/` | immutable versioned profiles & templates, PPTX token extraction | Good governance logic; **template→engine link broken**. |
| `outline/` | schema, builder, validator, service | Sound; validator only 43% covered. |
| `generation/` | **two parallel pipelines**: governed + freeform; worker, consistency, artifact | **Divergent.** See §5.4. |
| `guide/`, `chat/` | NotebookLM-style overview + RAG Q&A | Clean services, **broken retrieval scoping**. |
| `metering/` | usage rollups, quota, alerts, audit | Correct, but **primary path never feeds it**. |
| `engines/` | `EngineClient` base (retry/breaker), Presenton, Open Notebook, LLM | Base is good; **`LlmClient` bypasses it**. |
| `jobs/`, `workers/` | idempotent enqueue + Arq tasks | **Enqueue-before-commit race.** |
| `storage/` | MinIO, tenant-prefixed keys | **Presigned URLs unreachable from browser.** |

### 2.3 Frontend map (~4,760 LOC, **0 tests**)

```
app/(app)/          projects · projects/[id] · templates · profiles · usage
components/project/ SourcesPanel · GuidePanel · ChatPanel · StudioPanel ·
                    OutlinePanel · GeneratePanel · VersionHistoryPanel · SlideEditorModal
components/registry/ ProfileEditor · SectionStructureBuilder · StatusBadge
services/           api.ts (single typed client) · auth · session · uiPrefs
lib/i18n/           en · id (Bahasa Indonesia default)
```

`services/api.ts` as the sole backend entry point is a good decision, consistently held.

### 2.4 Logical dependency graph

```
api/ ──► api/deps.py ──► services ──► repositories ──► models
                    └──► engines/  ──► EngineClient ──► CircuitBreaker
                    └──► storage/
workers/tasks.py ──► generation/worker.py, ingestion/service.py  (own SessionLocal)
```

**No circular dependencies.** Layering is respected throughout — dependencies point inward and `deps.py` is the single composition root. This is a real strength and a key reason a rewrite is unwarranted.

### 2.5 Runtime flow — Studio deck generation (the primary user path)

```
1. POST /api/v1/projects/{id}/generations  { content_source, tone, n_slides, ... }
2. api/generations.py:91  → content_source present → FreeformGenerationService
3. _resolve_content(): summary | notebook | chat | custom
4. build_freeform_request() → Presenton params        ⚠ brand_tokens dropped
5. INSERT Generation(status=queued)  [flush, NOT committed]
6. JobService.create + dispatch → Arq enqueue         ⚠ before commit — race
7. get_db() commits at dependency teardown
   ── worker ──
8. run_generate → generate_presentation
9. PresentonClient.generate → download bytes → MinIO
10. profile_id is None → skip consistency → status=ready
11. UI polls; on ready offers PPTX/PDF + "🎨 Editor"
                                          ⚠ download URL unreachable from browser
                                          ⚠ editor link carries the wrong id
```

Four of the eleven steps carry a defect.

### 2.6 Rendering flow

The orchestrator never renders slides. It builds a `params` dict and hands it to Presenton, which owns layout, theming, and export. **All visual configurability therefore depends entirely on what `params` carries** — and today that is `template` (an opaque ref, usually the string `"default"`), `tone`, `verbosity`, `n_slides`, `language`, and `slides_markdown`. No colours. No fonts.

---

## 3. NOTEAI_TEST_REPORT.md Validation

The file was **overwritten** on 2026-07-28. Until then it contained the 26-criteria automated verification report that `README.md:79` still cites. The prior version is recoverable via `git show 1188545:NOTEAI_TEST_REPORT.md`.

### 3.1 Claim-by-claim

| # | Report claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `/editor/*` returns 404; static assets 404 | **Verified** | Consistent with the routing configuration in `docker-compose.lite.yml:178-181`. |
| 2 | Next.js standalone requires build-time `basePath` | **Verified — correct and well-diagnosed** | This is accurate Next.js behaviour. The best technical reasoning in the report. |
| 3 | Runtime `next.config.mjs` mutation is ineffective in standalone | **Verified** (for the vendored Presenton; unverifiable here since the source is absent) | Mechanism is correct. |
| 4 | Assets 404 because Next.js emits root-relative URLs Traefik sends to the wrong container | **Verified** | `/_next` is absent from the Presenton router rule. |
| 5 | **Solution 1** — hardcode `basePath: '/editor'` at build time | **Sound, and the only viable path-based fix** | Would make Next.js emit `/editor/_next/...`, which the existing rule matches. |
| 6 | **Solution 2** — restore stripprefix + expand Traefik rules to catch root assets | **INVALID — technically unsound** | See §3.2. |
| 7 | Manual `userConfig.json` injection bypassed "Instance Not Configured" | **Plausible**, unverifiable without the Presenton source | Also a **red flag**: manual container mutation means the running state is not reproducible from any committed file. |
| 8 | Rebuild was needed to pick up `/template-preview` | **Plausible** | Consistent with standalone builds. |
| 9 | *(implicit)* Routing is the reason the editor does not work | **Incomplete — the critical omission** | See §3.3. |

### 3.2 Why Solution 2 cannot work — and why it was implemented anyway

The report proposes adding `PathPrefix('/_next')` to the Presenton router. **Both the NoteAI frontend and Presenton are Next.js applications, and both serve their assets from `/_next`.** Routing `/_next` to Presenton breaks the NoteAI frontend; routing it to the frontend breaks Presenton. There is no priority ordering that resolves this — the paths are byte-identical.

The current `docker-compose.lite.yml:178` shows Solution 2 was attempted: seventeen `PathPrefix` alternatives were added, `stripprefix` was restored (`5816e0f`), and `/_next` was — necessarily — omitted. **The configuration is therefore in a state that cannot succeed by construction.** The last eight commits are iterations inside an unsolvable space.

Worse, commit `cbb0721` had already deployed Presenton on a **dedicated subdomain** (`editor.umarsyukri.com`), which sidesteps the collision entirely. Commit `2d0d46a` reverted that to path-based routing. **The team moved away from the working design.**

**Recommended action:** revert to the subdomain approach (zero code change; a DNS record and a router rule), *or* apply Solution 1 (`basePath: '/editor'` baked at build time). Subdomain is strictly simpler and needs no Presenton source modification — which matters, because §4.1 shows that source is not under version control.

### 3.3 What the report missed entirely

**Even a perfectly working `/editor` route leaves the editor broken.**

`frontend/src/components/project/StudioPanel.tsx:348` sets `activeEditorGenId = g.id` — the NoteAI `Generation.id` (a Postgres UUID). Line 400 builds `/editor/presentation?id=${activeEditorGenId}`.

Presenton has never seen that identifier. The id it needs is `Generation.presenton_presentation_id` (`backend/src/generation/worker.py:59`), which is **deliberately excluded** from the API response: `_PUBLIC_PARAM_KEYS` (`api/generations.py:39-50`) strips it, and `GenerationResponse` (`schemas/generation.py:51-68`) has no field for it.

So the editor deep-link is architecturally impossible to satisfy from the current API. This requires a **backend contract change**, not a routing change. No amount of Traefik work will fix it.

A second, independent defect stacks on top: `frontend/Dockerfile:12-19` declares `NEXT_PUBLIC_DEV_MODE`, `NEXT_PUBLIC_LITE_MODE`, and `NEXT_PUBLIC_DEFAULT_TENANT_NAME` as build args — but **not** `NEXT_PUBLIC_PRESENTON_UI_URL`, which `docker-compose.lite.yml:56` passes. Next.js inlines `NEXT_PUBLIC_*` at build time from the build environment, so `process.env.NEXT_PUBLIC_PRESENTON_UI_URL` in `SlideEditorModal.tsx:23` is **always `undefined`**. The configured subdomain has been silently ignored for every build.

### 3.4 Verdict on the report

Competent on the narrow question it asked (~70% correct on Next.js/Traefik mechanics), but it **framed a product bug as an infrastructure bug** and then recommended an approach that cannot work. Debugging effort has been misdirected for roughly eight commits.

---

## 4. Technical Debt Report

### 🔴 CRITICAL

**C1 — The slide engine is not in version control**
`deploy/docker-compose.lite.yml:160` → `build: context: ../presenton-custom`. Never tracked; absent from this machine. Existential risk: the VPS is the only copy, and it has been hand-mutated (`docker exec` writes to `/app_data/userConfig.json`, per the report). Rebuilding from scratch is currently impossible.
**Action:** vendor it as a git submodule or fork it into the org today. Nothing else in this document matters if this box dies.

**C2 — `brand_tokens` never reach the renderer**
`registry/service.py:108` stores; `generation/mapper.py:56-68` and `generation/freeform_mapper.py:58-77` never send. The `/templates` wizard, the colour pickers, the typography selectors, and the AI extraction onboarding are all write-only. The product's headline capability does not function.
**Action:** extend both mappers to pass brand tokens; confirm the Presenton payload key first (blocked on C1).

**C3 — RAG retrieval is not scoped to the project or tenant**
`engines/open_notebook.py:127-169`: `search()` takes `notebook_id` and **never uses it** — the request body is `{query, type, limit, search_sources, search_notes, minimum_score}`, with no notebook filter. The docstring concedes "Open Notebook search is global (not notebook-scoped)".
Callers: `chat/service.py:45`, `guide/service.py:48`, `generation/freeform_service.py:155`.
Consequence: Project A's guide, chat answers, and generated decks can be grounded in Project B's documents. In SaaS mode (`LITE_MODE=false`) this is **cross-tenant data leakage**, directly violating User Story 4, which the spec designates a release blocker.
`tests/contract/test_tenant_isolation.py` cannot catch this — it only exercises the Postgres repository layer.
**Action:** filter results by notebook server-side, or maintain one Open Notebook instance/namespace per tenant. Add an engine-level isolation test.

**C4 — Editor deep-link passes an identifier Presenton cannot resolve**
See §3.3. `StudioPanel.tsx:348,400`.

**C5 — Path-based routing for two Next.js apps is unsolvable**
See §3.2. `docker-compose.lite.yml:178`.

### 🟠 HIGH

**H1 — Enqueue-before-commit race silently drops jobs**
`get_db()` (`core/db.py:29-39`) commits at dependency teardown, *after* the handler returns. `JobService.dispatch()` (`jobs/service.py:63-74`) enqueues to Redis *inside* the handler. If the worker dequeues before the commit lands, `_load_job` (`workers/tasks.py:28-34`) finds nothing and **returns silently** — no error, no retry, no log beyond a warning.
It is then **permanent**: dispatch passes `_job_id=job.idempotency_key`, and with `keep_result=3600` (`workers/settings.py:26`) Arq refuses to re-enqueue that id for an hour.
Symptom: a generation stuck at `queued` forever, with no diagnostic. Mechanism confidence **high**; frequency depends on commit latency vs. Arq poll interval — needs runtime confirmation.
**Action:** commit before dispatch (transactional outbox, or an `after_commit` hook).

**H2 — Deck downloads are unreachable from the browser**
`object_store.py:101-109` presigns against `MINIO_ENDPOINT=http://minio:9000` — an internal Docker hostname. `api/generations.py:140` returns that URL to the client; `StudioPanel.tsx:141` calls `window.open()` on it. In `docker-compose.lite.yml`, MinIO is on `appnet` only, has no Traefik labels, and its ports are commented out (`:126-127`). The browser cannot resolve it.
(The *ingestion* presign works — Open Notebook is on `appnet`.)
**Action:** add `MINIO_PUBLIC_ENDPOINT` and presign browser-facing URLs against it, or proxy downloads through the orchestrator.

**H3 — The primary generation path bypasses quota and metering**
`generation/service.py` calls `QuotaService.enforce` (`:108`) and `MeteringService.record` (`:143`). `generation/freeform_service.py:53-124` calls **neither**. Since `UsageReportService` counts `action == "generation.created"` (`metering/aggregation.py:20,34`), the `/usage` dashboard reports **zero generations** for the path users actually use. The README's "Usage Dashboard & Quotas" feature is structurally unable to observe the product.
**Action:** move quota + metering into a shared pre-flight both services call.

**H4 — `NEXT_PUBLIC_PRESENTON_UI_URL` is never inlined**
`frontend/Dockerfile:12-19` vs `docker-compose.lite.yml:56`. See §3.3.

**H5 — No health monitoring anywhere**
`api/health.py` registers `/healthz` and `/readyz` at the root, outside the `/api/v1` prefix (`api/router.py:24`). Traefik routes `/` to the frontend — so **both endpoints are unreachable in the deployed stack**. Independently, `grep -c healthcheck` returns **0** for both compose files, and `init` uses `depends_on: [postgres]` without a readiness condition (`:45`), so `alembic upgrade head` races Postgres startup.
**Action:** move health under `/api`, add compose healthchecks, gate `init` on Postgres readiness.

**H6 — Template registration failure is doubly swallowed**
`PresentonClient.register_template` returns `"default"` on any error (`engines/presenton.py:74-90`), and the caller wraps it in another `except` that also returns `"default"` (`registry/service.py:91-100`). A tenant uploads a branded PPTX, sees "Template created ✅", and silently receives Presenton's stock theme forever. Introduced by `04c573c` ("resilient fallback") — resilience implemented as concealment.
**Action:** persist a `registration_status` and surface degradation in the UI.

**H7 — `LlmClient` bypasses the resilience layer**
`engines/llm.py:37-84` calls `httpx` directly: no retry, no backoff, no circuit breaker — unlike every other engine client. Worse, `:82-83` raises `EngineError("LLM provider request failed.")`, discarding the status code and body. OpenRouter's distinct failure modes (401 bad key, 402 no credits, 429 rate-limited, 404 unknown model slug) all collapse into one opaque message. This is why LLM failures are hard to diagnose.
**Action:** subclass `EngineClient`; log status + body snippet server-side.

### 🟡 MEDIUM

- **M1 — Zero frontend tests.** ~4,760 LOC, no framework installed (`frontend/package.json`). Every defect in §3.3 is trivially unit-testable and would have been caught.
- **M2 — The "automated verification suite" is a grep script.** `automation/verify_noteai_revamp.py:34-49` asserts that files *contain regex patterns* (e.g. `2563EB` in `tailwind.config.ts`). It executes no application code and cannot detect any defect in this report. `README.md:79` presents its "100% pass rate across 26 criteria" as quality evidence. **This is the most damaging item in the repo** — it manufactures false confidence.
- **M3 — Documentation drift.** `README.md:79` cites a file that no longer exists in that form. `CHANGELOG.md:30` claims "Live Studio Generation… instant browser downloads" (H2) and "Presenton interactive slide editor" (C4). `README.md:39` says Python 3.14; `pyproject.toml:5` says `>=3.11`.
- **M4 — Dead abstraction.** `open_notebook.run_transformation` (`:113-125`) is a documented no-op returning its input, and `add_source` accepts `provider_config` only to discard it (`:57-81`). `provider_config` is threaded through five call layers to be thrown away. The spec's "analyzes them with Open Notebook" is really "embeds and retrieves".
- **M5 — Polymorphic endpoint.** `POST /projects/{id}/generations` dispatches to two services based on which nullable field is present (`api/generations.py:91-102`). Works, but couples two lifecycles to one contract and makes the OpenAPI schema ambiguous.
- **M6 — Traefik steals frontend paths.** `/images`, `/fonts`, `/uploads`, `/app_data` route to Presenton at priority 20 (`:178`). The NoteAI frontend currently ships nothing under those prefixes, but any future asset there will silently 404.
- **M7 — Two deployment models half-configured.** `.env.lite.example` still sets `PRESENTON_DOMAIN`/`NEXT_PUBLIC_PRESENTON_UI_URL` for the subdomain model while code and compose assume path-based. Pick one.
- **M8 — Goal drift.** See §5.4.

### ⚪ LOW

- **L1** `backend/.coverage` is tracked. Add to `.gitignore`.
- **L2** `metagpt/` and `.specify/` are unused scaffolding from earlier workflows (~15 files).
- **L3** Two uncommitted working-tree changes (`StudioPanel.tsx`, `NOTEAI_TEST_REPORT.md`) — deployed state does not match any commit.
- **L4** `deploy/.env.lite.example` ships `PRESENTON_AUTH_PASSWORD=change-me123`; `DISABLE_AUTH: "true"` in compose makes it simultaneously required and irrelevant.

---

## 5. Architecture Review

### 5.1 Strengths (keep these)

1. **Tenant isolation by construction.** `TenantScopedRepository._scoped()` (`tenancy/repository.py:36-38`) makes an unfiltered query impossible at the Postgres layer. Cross-tenant reads surface as 404, not 403 — correct anti-enumeration design.
2. **Consistent error envelope.** `core/errors.py` is textbook: typed domain errors, stable machine codes, correlation-id propagation, no leaked internals. The frontend `ApiError` mirrors it exactly.
3. **Engine resilience.** `EngineClient` (`engines/base.py`) centralises timeout, bounded exponential backoff on 5xx/429 only, and a circuit breaker. Correctly *not* retrying 4xx.
4. **Immutable registry versioning.** Edits create versions; versions in use are frozen (`registry/service.py`). Real governance, and generations remain traceable to what produced them.
5. **Clean layering, no cycles.** `deps.py` as sole composition root; dependencies point inward throughout.
6. **Idempotent, resumable workers.** Ready entities are no-ops; partially-completed work is not redone (`generation/worker.py:44-57`, `ingestion/service.py:162-190`).
7. **Honest code comments.** Nearly every module header explains *why*. `open_notebook.py:119-125` openly documents its own no-op. Documentation quality *inside* the code far exceeds the docs *about* it.

### 5.2 Weaknesses

1. **Every engine boundary is under-specified and under-tested.** Coverage: `llm.py` 31%, `open_notebook.py` 32%, `presenton.py` 54%, `object_store.py` 46%. These are exactly where all production failures occur. The contract tests assert against *fakes* (`tests/fakes.py`), so they validate the orchestrator's assumptions rather than the engines' behaviour.
2. **Silent degradation as a house style.** `register_template` → `"default"`; `search()` → `[]`; `_is_embedded` → `False`; `_load_job` → `return`. Individually defensible; collectively they make the system fail invisibly. The team's debugging difficulty is a direct consequence.
3. **Two generation pipelines with divergent guarantees** (§5.4).
4. **No frontend test tier at all.**
5. **The deployment topology is not derivable from the repository.** An outer nginx, TLS, DNS, and the entire Presenton build live outside version control.

### 5.3 Scalability / maintainability / extensibility

| Dimension | Verdict |
|---|---|
| **Scalability** | Adequate for the current goal. Sync SQLAlchemy in a threadpool is a deliberate, documented trade-off. Arq scales horizontally. Real limits: `ingest_source` blocks a worker slot polling for up to 2 minutes (`config.py:116-117`), and `StudioPanel.pollUntilDone` (`:91-105`) does up to 200 sequential fetches per deck. Both fine at demo scale, both need attention before real load. |
| **Maintainability** | **Good in core, poor at the edges.** Files are small (largest backend module 273 lines), naming is consistent, comments explain intent. Undermined by documentation that actively misleads. |
| **Extensibility** | **Good.** Adding an engine means subclassing `EngineClient`; adding an entity means a model + a scoped repo. The abstractions are the right ones — which is the strongest single argument against a rewrite. |
| **Testability** | **Structurally excellent, unevenly exploited.** `deps.py` makes every collaborator injectable and `tests/fakes.py` uses it well. The gap is engine-contract and frontend coverage, not test *design*. |

### 5.4 The one genuine architectural problem: goal drift

`specs/001-presentation-notebook-llm/spec.md` defines a **multi-tenant SaaS for Indonesian corporate teams**: governed stakeholder profiles → validated outline → consistency-enforced deck, with RBAC, quotas, and audit as release blockers.

The architecture faithfully implements that: immutable profile/template versions, an outline validator, a post-generation consistency gate, per-tenant BYOK, quota enforcement, metering.

**The product has since pivoted to a NotebookLM-style single-tenant tool with configurable slides.** The Studio path — the one users actually use — routes around essentially all of it:

| Governance mechanism | Governed path | Studio (freeform) path |
|---|---|---|
| Stakeholder profile | required | **none** |
| Outline validation | required | **bypassed** |
| Consistency gate | enforced | **skipped** (`worker.py:77-87`) |
| Quota enforcement | enforced | **absent** |
| Usage metering | recorded | **absent** |
| Template governance | approved versions only | falls back to any version (`freeform_service.py:77-79`) |

The result is a heavyweight governance architecture that the primary use case does not touch — carried as maintenance cost, tested at 94% while the path users exercise sits at 38%.

**This is the decision to make.** It is not a code problem; it is a scope problem, and the resolution is subtraction:

- **If NotebookLM-style is the product** (which the last 15 commits, the Bahasa Indonesia default, and the repo name all indicate): make freeform the *only* path. Delete outline/profile/consistency (~800 LOC). Keep templates for branding. Keep tenancy scoping — it costs nothing and preserves optionality. **Recommended.**
- **If governed enterprise decks are the product:** make the Studio path inherit profile governance rather than bypass it.

Choosing neither — the current state — pays for both and gets the guarantees of neither.

---

## 6. Refactoring Opportunities (ranked by impact ÷ effort)

| # | Change | Benefit | Effort | Risk |
|---|---|---|---|---|
| 1 | Vendor `presenton-custom` into version control | Removes existential risk; makes every other fix possible | 0.5d | None |
| 2 | Presenton on its own subdomain; drop path routing | Kills C5 + M6 permanently; reverts to a design that worked | 0.5d | Low (DNS/TLS) |
| 3 | Pass `brand_tokens` through both mappers | **Delivers the headline feature** | 1–2d | Low (blocked on #1) |
| 4 | Expose `presenton_presentation_id`; fix the editor link | Makes the editor reachable | 0.5d | Low — a deliberate exposure decision |
| 5 | Commit before dispatch | Eliminates silently-lost jobs | 0.5d | Low |
| 6 | `MINIO_PUBLIC_ENDPOINT` for browser presigns | Downloads actually work | 0.5d | Low |
| 7 | Scope Open Notebook search per notebook | Closes the leakage hole | 1–2d | Medium — depends on engine capability |
| 8 | Shared quota+metering pre-flight for both paths | `/usage` becomes truthful | 0.5d | Low |
| 9 | `LlmClient extends EngineClient`; log status+body | Makes LLM failures diagnosable | 0.5d | Low |
| 10 | Vitest + RTL; test `SlideEditorModal`, `StudioPanel`, `api.ts` | Closes the tier that produced C4/H4 | 1–2d | None |
| 11 | Replace `verify_noteai_revamp.py` with Playwright smoke tests | Real signal instead of false confidence | 2d | None |
| 12 | Surface `register_template` failure instead of `"default"` | Users learn their branding didn't apply | 0.5d | Low |
| 13 | Health under `/api` + compose healthchecks + `init` gating | Observability and reliable startup | 0.5d | Low |
| 14 | Reconcile README/CHANGELOG with reality | Stops misdirected debugging | 0.5d | None |
| 15 | Resolve the §5.4 scope decision | Halves the maintained surface | 2–3d | Medium |

---

## 7. Revamp Proposal

**A rewrite is not recommended.** Justification:

1. Failures are **localised** (six seams), not systemic. Every one has a bounded fix listed above.
2. The expensive-to-get-right parts are **already right**: tenant isolation, error contracts, versioning, resilience, layering.
3. The hardest problems — Presenton's behaviour, Open Notebook's global search, Next.js standalone `basePath` — are **external**. A rewrite inherits all of them unchanged.
4. 83% backend coverage and 61 green tests are real assets that a rewrite discards.

**What is warranted is a scope reduction plus seam repair** — described in §5.4 and §6. That is *targeted revamp*, not a rebuild.

### Target architecture (deltas only)

```
edge:      app.<domain>     → frontend  (Next.js)
           app.<domain>/api → orchestrator
           editor.<domain>  → presenton  (own origin — no /_next collision)
           files.<domain>   → MinIO      (browser-reachable presigns)

backend:   generation/  ── ONE pipeline (freeform), with:
                            · shared quota + metering pre-flight
                            · brand_tokens → Presenton params
                            · commit-then-dispatch
           engines/     ── LlmClient extends EngineClient
                        ── OpenNotebookClient.search scoped by notebook
           api/         ── GenerationResponse exposes editor_url

repo:      presenton-custom/ vendored as a submodule
frontend:  vitest + RTL; Playwright smoke path
```

**Backward compatibility:** all changes are additive at the API layer (one new response field, one new env var). No client migration needed. The only breaking change is deleting the governed outline path — which is unused in lite mode, so nothing in production depends on it.

---

## 8. Prioritized Roadmap

### Phase 0 — Stop the bleeding (0.5 day, do today)

| Task | Depends on |
|---|---|
| Vendor `presenton-custom` into git (submodule or fork) | — |
| Snapshot the VPS `presenton_data` volume and `/app_data/userConfig.json` | — |
| Commit or revert the two working-tree changes | — |

**Gate:** the full stack can be rebuilt from a fresh clone.

### Phase 1 — Critical fixes (3–4 days)

| Task | Fixes | Depends on |
|---|---|---|
| Move Presenton to `editor.<domain>`; delete the 17-alternative Traefik rule | C5, M6, M7 | Phase 0 |
| Expose `presenton_presentation_id` (or a server-built `editor_url`); fix `StudioPanel` + `SlideEditorModal` | C4, H4 | ↑ |
| Wire `brand_tokens` into both mappers + `register_template` | **C2** | Phase 0 |
| Commit-then-dispatch in `JobService` | H1 | — |
| `MINIO_PUBLIC_ENDPOINT` for browser-facing presigns | H2 | — |
| Surface template-registration failure | H6 | — |

**Gate:** upload → generate → download → open in editor works end-to-end, with a branded template visibly applied.

### Phase 2 — Architecture stabilisation (4–5 days)

| Task | Fixes |
|---|---|
| Scope Open Notebook retrieval per notebook + engine-isolation test | **C3** |
| Shared quota + metering pre-flight across both generation paths | H3 |
| `LlmClient extends EngineClient`; log status + body | H7 |
| Health under `/api`; compose healthchecks; gate `init` on Postgres readiness | H5 |
| Vitest + RTL; cover `api.ts`, `SlideEditorModal`, `StudioPanel` | M1 |
| Retire `verify_noteai_revamp.py`; add a Playwright smoke path | M2 |
| Reconcile README / CHANGELOG / TEST_REPORT with reality | M3 |

**Gate:** CI runs backend + frontend + one E2E smoke test. No documented feature is untrue.

### Phase 3 — Scope resolution & feature work (5–8 days)

| Task | Fixes |
|---|---|
| **Decide §5.4.** If NotebookLM-style: delete outline/profile/consistency (~800 LOC) | M8 |
| Collapse the polymorphic `/generations` endpoint into explicit routes | M5 |
| Remove the `run_transformation` / `provider_config` dead abstraction | M4 |
| Replace `StudioPanel` polling with SSE or backoff | perf |
| Real template preview (thumbnail from the registered Presenton template) | product |

**Gate:** one generation pipeline, one set of guarantees.

### Phase 4 — Long-term (ongoing)

- Engine contract tests against real containers in CI (not fakes)
- Structured error taxonomy for engine failures surfaced in the UI
- Multi-tenant re-enablement checklist (`LITE_MODE=false` is currently **unsafe** until C3 is fixed)
- Move `ingest_source` polling to a scheduled re-enqueue so workers aren't blocked
- Retire `metagpt/` and `.specify/`; clean `.gitignore`

### Dependency graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
   │            │
   │            └─ C2 and C4 both require the vendored Presenton source
   └─ everything downstream requires a reproducible build
```

**Total to a genuinely working product: ~13–18 working days.**
A rewrite would cost 8–12 weeks and reproduce every external-integration bug listed here.

---

## Appendix A — Facts vs. assumptions

**Verified from source (high confidence):**
C1, C2, C3, C4, C5, H3, H4, H5, H6, H7, M1–M8, L1–L4 — all read directly from the files cited.

**Verified by execution:**
Backend suite: 61 passed, 1 skipped, 83% coverage (`pytest --cov`, 1.96s).
`presenton-custom` absent from git history and filesystem (`git log --all --`, `find /`).

**High-confidence inference, runtime confirmation recommended:**
- **H1** — mechanism proven from source; *frequency* depends on commit latency vs. Arq poll interval. Confirm by grepping worker logs for `worker_job_missing`.
- **H2** — network topology conclusive from compose; confirm by inspecting a returned download URL in the browser.

**Not verifiable without the Presenton source (blocked on C1):**
- Report claims 3, 7, 8.
- The exact payload key Presenton expects for brand tokens (needed for C2's fix).
- Whether Presenton exposes a per-presentation editor route at all (needed for C4's fix).

**Not inspected:**
The outer nginx/TLS layer referenced by `deploy/DEPLOY-VPS-HOSTINGER.md` — outside this repository.
