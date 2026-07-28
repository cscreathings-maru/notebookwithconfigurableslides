# Phase 1 — Critical Fixes: Make the Core Loop Work

**Duration:** 3–4 days · **Severity:** 🔴 Critical · **Requires:** Phase 0 gate `PASS`

---

## Role & context

**NoteAI** turns uploaded documents into branded slide decks.

- `frontend/` — Next.js 14 App Router, standalone output. Single API client at `src/services/api.ts`.
- `backend/` — FastAPI at `/api/v1`; Postgres (system of record), Redis/Arq (jobs), MinIO (artifacts).
- `presenton/` — slide-rendering engine (Next.js UI + Python API), vendored in Phase 0, served at `/editor`.
- `open-notebook` — embeddings + retrieval over SurrealDB.
- Traefik path-routes all services on one origin.

The core user journey — **upload → generate → download → edit** — is broken at four independent points. Phase 1 fixes all four.

---

## Architecture decision (locked — do not relitigate)

> **Presenton stays on the same origin under `/editor`.** One domain, one TLS certificate, one nginx rule, no cross-domain configuration.

**Mechanism: build-time `basePath: '/editor'` in Presenton's `next.config.mjs`.**

This is `NOTEAI_TEST_REPORT.md` §Solution 1. Solution 2 (expanding Traefik rules to catch root-level assets) is **not viable** and must not be attempted:

- Both the NoteAI frontend and Presenton are Next.js apps.
- Both serve static assets from `/_next`.
- Traefik cannot disambiguate two byte-identical prefixes at one origin — priority does not help.
- The current `docker-compose.lite.yml:178` is a failed attempt at Solution 2: seventeen `PathPrefix` alternatives with `/_next` necessarily absent. It cannot succeed by construction.

`basePath` makes Presenton emit `/editor/_next/...`. **The collision stops existing** rather than being arbitrated. Same destination as Solution 2 aimed at; a mechanism that works.

---

## Scope

### In scope

| Task | Fixes |
|---|---|
| T-1.1 | `/editor` routing via build-time `basePath` |
| T-1.2 | Editor deep-link passes an identifier Presenton cannot resolve |
| T-1.3 | **`brand_tokens` never reach the renderer — the headline feature** |
| T-1.4 | Jobs silently lost to an enqueue-before-commit race |
| T-1.5 | Deck downloads unreachable from the browser |
| T-1.6 | Template registration failure silently swallowed |

### Out of scope — defer, do not fix

- Open Notebook global search / cross-project leakage → **Phase 2 (T-2.1)**
- Quota + metering on the freeform path → **Phase 2 (T-2.2)**
- `LlmClient` resilience → **Phase 2 (T-2.3)**
- Frontend test tier → **Phase 2 (T-2.5)** *(exception: T-1.2 and T-1.5 each require one narrow unit test — write those, and only those)*
- Deleting the governed outline/profile pipeline → **Phase 3**
- Any documentation rewrite → **Phase 2 (T-2.7)**

---

## Tasks

Execute in order. T-1.2 depends on T-1.1; T-1.3 depends on Phase 0.

---

### T-1.1 — Serve Presenton correctly at `/editor` 🔴

**Problem:** `/editor/*` returns Next.js's 404 layout; static assets 404 against the wrong container.

**Evidence:**
- `deploy/docker-compose.lite.yml:178` — 17-alternative `PathPrefix` rule, no `/_next`
- `deploy/docker-compose.lite.yml:180-181` — `stripprefix` removes `/editor` before Next.js sees it
- Presenton's `next.config.mjs` — `output: 'standalone'` with no `basePath`

**Root cause:** in standalone mode Next.js does not read `next.config.mjs` at runtime, so `basePath` must be baked at **build** time. Presenton's `start.js` attempts to inject it at runtime, which the standalone `server.js` ignores. Next.js therefore believes it is mounted at `/`, receives `/template-preview` (post-strip), and emits root-relative asset URLs that Traefik hands to the NoteAI frontend.

**Change:**

1. In `presenton/servers/nextjs/next.config.mjs`, set `basePath` statically:
   ```js
   const nextConfig = {
     basePath: '/editor',
     output: 'standalone',
     // ...
   };
   ```
   Prefer a build arg (`NEXT_PUBLIC_BASE_PATH`) with `/editor` as the default, so the value is visible in compose rather than buried.

2. Remove the runtime `next.config.mjs` mutation from `start.js` if present — it is inert in standalone mode and actively misleading to the next reader.

3. In `deploy/docker-compose.lite.yml`, **delete the `stripprefix` middleware**. With `basePath`, Next.js expects the full `/editor/...` path:
   ```yaml
   # DELETE both:
   # - "traefik.http.middlewares.presenton-strip.stripprefix.prefixes=/editor"
   # - "traefik.http.routers.presenton.middlewares=presenton-strip"
   ```

4. Simplify the router rule. `/editor` now covers the UI **and** its assets:
   ```yaml
   - "traefik.http.routers.presenton.rule=PathPrefix(`/editor`) || <presenton-api-allowlist>"
   - "traefik.http.routers.presenton.priority=20"
   ```

**On the API allowlist.** Presenton is not purely Next.js — it has a Python API the browser calls at root paths (`/api/v1/ppt/...`, `/api/can-change-keys`, …). `basePath` does **not** rewrite client-side `fetch()` calls, only `Link`/`Image`/router navigation. Two options:

| | Approach | Effort | Result |
|---|---|---|---|
| **1A — minimum viable** | Keep the explicit root-API allowlist; add the collision guard in step 5 | Low | Works. Rule stays long and fragile. |
| **1B — target** | Also prefix Presenton's client-side API base to `/editor/api/...` | Medium | A single `PathPrefix('/editor')` rule covers everything; allowlist retired |

**Do 1A in this phase.** Record 1B as a Phase 4 candidate. Shipping the working loop matters more than rule elegance right now.

5. **Add a collision guard.** The allowlist steals paths from the orchestrator and the frontend at priority 20 — today `/api/v1/admin`, `/api/v1/auth/token`, `/images`, `/fonts`, `/uploads`, `/app_data`. Nothing collides *yet*, which is exactly why it will regress silently. Add a test that enumerates the orchestrator's registered routes and asserts disjointness from the allowlist:
   ```python
   # backend/tests/contract/test_route_collisions.py
   def test_orchestrator_routes_do_not_collide_with_presenton_allowlist():
       ...
   ```

**Acceptance:**
- `https://<domain>/editor` renders the Presenton UI, HTTP 200
- Browser devtools show **zero** 404s; assets load from `/editor/_next/...`
- `https://<domain>/` still renders NoteAI with its own assets intact
- `/api/v1/projects` still reaches the orchestrator
- The collision test passes

---

### T-1.2 — Fix the editor deep-link identifier 🔴

**Problem:** even with T-1.1 correct, "🎨 Editor" opens a 404. **`NOTEAI_TEST_REPORT.md` missed this entirely** — it is a backend contract defect, not a routing one, and no amount of Traefik work resolves it.

**Evidence:**
- `frontend/src/components/project/StudioPanel.tsx:348` — `setActiveEditorGenId(g.id)` — the **NoteAI** `Generation.id`, a Postgres UUID
- `frontend/src/components/project/StudioPanel.tsx:400` — `editorUrl={/editor/presentation?id=${activeEditorGenId}}`
- `backend/src/generation/worker.py:59` — the id Presenton needs is `gen.presenton_presentation_id`
- `backend/src/api/generations.py:39-50` — `_PUBLIC_PARAM_KEYS` strips it
- `backend/src/schemas/generation.py:51-68` — `GenerationResponse` has no field for it

Presenton has never seen the identifier being sent. It is also **architecturally unavailable** to the client by deliberate design.

A second, independent defect stacks on top:
- `frontend/Dockerfile:12-19` declares `NEXT_PUBLIC_DEV_MODE`, `NEXT_PUBLIC_LITE_MODE`, `NEXT_PUBLIC_DEFAULT_TENANT_NAME` as build args — **not** `NEXT_PUBLIC_PRESENTON_UI_URL`
- `deploy/docker-compose.lite.yml:56` passes it anyway
- Next.js inlines `NEXT_PUBLIC_*` at build time from the build environment, so `process.env.NEXT_PUBLIC_PRESENTON_UI_URL` at `SlideEditorModal.tsx:23` is **always `undefined`**

**Change:**

1. **Decide the exposure, deliberately.** The codebase holds a strong invariant: engine ids never reach the client (`api/generations.py:37-38`, `schemas/generation.py:3-5`). Two ways to honour the intent:

   | Option | Shape | Assessment |
   |---|---|---|
   | **A — server-built URL** | Add `editor_url: str \| None` to `GenerationResponse`; backend composes `/editor/presentation/{presenton_presentation_id}` | **Recommended.** The engine id stays an implementation detail; the client receives a capability, not an identifier. Changing Presenton's URL shape later is a backend-only edit. |
   | **B — expose the raw id** | Add `presenton_presentation_id` to the response | Simpler, but leaks an engine primitive into a public contract and invites clients to construct URLs themselves. |

   **Take Option A.** Document it as a reviewed, intentional narrowing of the invariant — the client gets a URL it cannot forge meaning from, not an engine handle.

2. Confirm Presenton's actual editor route from the now-vendored source. Do not guess between `/presentation/{id}`, `/presentation?id={id}`, and `/editor/{id}` — **read the route file.** The uncommitted change from Phase 0 flipped between two forms without establishing which is real.

3. `StudioPanel.tsx` — use `generation.editor_url` directly. Hide the Editor button when it is `null` (deck not yet rendered, or engine id missing).

4. `SlideEditorModal.tsx:22-28` — delete the `defaultBaseUrl` / `/presenton` rewriting logic entirely. It exists to compensate for an env var that never arrives.

5. Either add `NEXT_PUBLIC_PRESENTON_UI_URL` to `frontend/Dockerfile` **or** remove it from `docker-compose.lite.yml:56` and `.env.lite.example`. With same-origin `/editor`, **removing it is correct** — a base URL is no longer needed.

6. **Unit test** (`frontend/`, the one exception to the Phase 2 deferral): given a generation with `editor_url`, the modal renders that exact href; given `null`, the button does not render.

**Acceptance:**
- Clicking "🎨 Editor" on a ready deck opens the Presenton editor **with that deck loaded**
- No `NEXT_PUBLIC_PRESENTON_UI_URL` reference survives in the frontend
- `presenton_presentation_id` still does not appear in any API response
- The unit test covers both branches

---

### T-1.3 — Wire `brand_tokens` through to the renderer 🔴

**Problem:** **the product's headline feature does not function.** Every colour, font, and aspect ratio from the 4-section Template Configurator — plus the AI token-extraction onboarding — is stored and never used. The repository is named *notebookwithconfigurableslides*; the slides are not configurable.

**Evidence:**
- `backend/src/registry/service.py:108` — `brand_tokens=brand_tokens` persisted on the `Template` row
- `backend/src/generation/mapper.py:56-68` — governed path sends only `template: presenton_template_ref`
- `backend/src/generation/freeform_mapper.py:58-77` — Studio path sends only `params["template"] = template_ref`
- `backend/src/engines/presenton.py:60-90` — `register_template()` accepts only `name` and `source_pptx_path`

The data is fully modelled and correctly stored. **This is a wiring gap, not a design flaw** — which is why it is cheap to fix and why fixing it delivers the most visible improvement in the programme.

**Change:**

1. **Read Presenton's generate endpoint from the vendored source** and determine how theming is actually accepted. Likely candidates: a `theme`/`brand` object on `POST /api/v1/ppt/presentation/generate`, or template-registration-time colour/font parameters, or a generated custom layout. **Establish this from the code before writing any mapper change.** Record the finding in the report — it is reusable knowledge the team currently does not have.

2. Add a shared translator, e.g. `backend/src/generation/brand.py`:
   ```python
   def brand_params(template: Template) -> dict[str, Any]:
       """Translate stored brand_tokens into Presenton's theming contract."""
   ```
   One function, both mappers. Do not duplicate the mapping — divergence between the two pipelines is already this codebase's recurring failure mode.

3. Call it from **both** `mapper.py` and `freeform_mapper.py`.

4. If theming is applied at registration rather than generation, extend `PresentonClient.register_template()` to carry brand tokens and re-register when a template version changes.

5. **Contract test** asserting the built params carry the configured colours/fonts. Extend `backend/tests/contract/test_presenton_mapping.py`.

6. **Visual proof.** Generate one deck with a deliberately unmistakable palette (magenta primary, lime accent) and attach a screenshot of a rendered slide to the report. A passing unit test proves the payload; only the screenshot proves the renderer honoured it.

**Acceptance:**
- A template with primary `#FF00FF` produces a deck visibly using that colour
- Both governed and freeform paths apply branding identically
- Contract test asserts brand tokens are present in the payload
- Screenshot attached to the report

---

### T-1.4 — Eliminate the enqueue-before-commit race 🟠

**Problem:** generations can stick at `queued` forever with no error, no retry, and no diagnostic.

**Evidence:**
- `backend/src/core/db.py:29-39` — `get_db()` commits at **dependency teardown**, after the handler returns
- `backend/src/jobs/service.py:63-74` — `dispatch()` enqueues to Redis **inside** the handler
- `backend/src/workers/tasks.py:28-34` — `_load_job()` returns `None` on a miss and the task **returns silently**

**Failure sequence:**
1. Handler inserts `Generation` + `Job` (flushed, uncommitted)
2. `dispatch()` pushes to Redis — visible to workers immediately
3. Worker dequeues before the commit lands; `db.get(Job, id)` → `None`
4. `run_generate` returns; job stays `queued` forever

It is then **permanent**: `dispatch()` passes `_job_id=job.idempotency_key`, and with `keep_result=3600` (`workers/settings.py:26`) Arq refuses to re-enqueue that id for an hour.

**Change:**

1. Move dispatch after commit. Cleanest fit for this codebase: register an `after_commit` hook, or collect pending dispatches on the request and flush them in `get_db()` after `db.commit()` succeeds.
2. Make the worker's miss **loud**: if the job row is absent, log at `error` with the id and raise so Arq retries, rather than returning silently.
3. **Regression test:** simulate dequeue-before-commit and assert the job is not silently dropped.

**Acceptance:**
- No Arq enqueue occurs before its DB transaction commits
- A missing job row produces an error-level log and a retry, never a silent return
- Test fails against the old ordering, passes against the new

---

### T-1.5 — Make deck downloads reachable from the browser 🟠

**Problem:** the download button hands the browser a URL it cannot resolve.

**Evidence:**
- `backend/src/storage/object_store.py:101-109` — presigns against `MINIO_ENDPOINT` = `http://minio:9000`, an internal Docker hostname
- `backend/src/api/generations.py:140` — returns that URL to the client
- `frontend/src/components/project/StudioPanel.tsx:141` — `window.open(url)`
- `deploy/docker-compose.lite.yml:117-127` — MinIO is on `appnet` only, has no Traefik labels, ports commented out

The *ingestion* presign works because Open Notebook is on `appnet`. Only browser-facing URLs are broken.

**Change:** pick one and record why.

| Option | Shape | Trade-off |
|---|---|---|
| **A — public endpoint** | Add `MINIO_PUBLIC_ENDPOINT`; presign browser-facing URLs against it; route `/files` to MinIO via Traefik | Keeps large transfers off the API process. Exposes MinIO on the origin. |
| **B — proxy through the orchestrator** | `GET /api/v1/generations/{id}/download` streams bytes directly | Nothing new exposed; artifacts stay behind existing auth. API process carries the transfer. |

> **Recommendation: Option B** for this phase. It needs no new routing, no new surface, and no second signing domain — and it composes with the `/editor` same-origin decision you have already made. Revisit A only if deck sizes make streaming a bottleneck.

Keep two presign paths clearly separated — engine-internal (Open Notebook fetching a source) and browser-facing. Conflating them is what caused this.

**Acceptance:**
- Clicking PPTX or PDF on a ready deck downloads a valid, openable file **in a real browser**
- Ingestion still works (Open Notebook can still fetch uploaded sources)
- Test covers the browser-facing path

---

### T-1.6 — Surface template registration failure 🟠

**Problem:** a user uploads a branded PPTX, sees "Template created ✅", and silently receives Presenton's stock theme forever.

**Evidence:**
- `backend/src/engines/presenton.py:74-90` — returns `"default"` on any error
- `backend/src/registry/service.py:91-100` — caller wraps it in a second `except` that **also** returns `"default"`

Two independent swallows. Introduced by `04c573c` ("resilient fallback") — resilience implemented as concealment. This directly undermines T-1.3: branding can be wired perfectly and still appear not to work, with nothing in the UI explaining why.

**Change:**

1. Add `registration_status` to the `Template` model: `registered` | `fallback` | `failed`, plus `registration_error`. Alembic migration required.
2. Keep the fallback — creation should not hard-fail — but **record** it.
3. Surface it in `TemplateResponse` and render a warning badge in `frontend/src/app/(app)/templates/page.tsx`.
4. Remove the redundant outer `try/except` at `registry/service.py:95-100`. One handler, one place.
5. Test: registration failure → template created with `status=fallback` and a non-null error.

**Acceptance:**
- A failed registration is visible in the API response and in the UI
- Template creation still succeeds (no hard failure)
- Exactly one fallback handler remains

---

## Verification

```bash
# Backend
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
# expect: >= 61 passed (new tests added), coverage >= 83%

# Frontend
cd frontend && npm run typecheck && npm run test -- --run   # 2 tests from T-1.2

# Routing (T-1.1)
curl -sI https://<domain>/editor            | head -1   # 200
curl -sI https://<domain>/                  | head -1   # 200
curl -sI https://<domain>/api/v1/languages  | head -1   # 200

# Migration (T-1.6)
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

### Manual journey — must be walked end to end

1. Create a template with primary `#FF00FF`; upload a base PPTX
2. Approve it
3. Create a project; upload a source; wait for `ready`
4. Generate the guide
5. Studio → generate a deck with that template
6. Deck reaches `ready`
7. **Download PPTX** → opens, **uses magenta** ← T-1.3 + T-1.5
8. **Click "🎨 Editor"** → Presenton opens **with that deck loaded** ← T-1.1 + T-1.2
9. Devtools console: **zero** 404s ← T-1.1

Every step needs a screenshot in the report.

---

## Deliverable

`revamp/reports/PHASE-1-REPORT.md`, using [`TEST-REPORT-TEMPLATE.md`](TEST-REPORT-TEMPLATE.md).

Phase 1 is the most visible phase — §5 (manual verification) carries the real weight. All nine journey steps must appear with observed output. §4.4 must show before/after for every task.

§7 will matter here: T-1.3 requires reading Presenton's generate contract for the first time, and that reading will surface things nobody has documented. Record them.

---

## Exit gate

| # | Criterion |
|---|---|
| **G1** | `/editor` serves Presenton at 200 with zero asset 404s; NoteAI frontend unaffected |
| **G2** | "🎨 Editor" opens the correct deck in Presenton |
| **G3** | **A template's brand colours are visibly applied to a generated deck** (screenshot attached) |
| **G4** | No Arq enqueue precedes its DB commit; a missing job logs an error and retries |
| **G5** | PPTX and PDF download successfully in a real browser |
| **G6** | Template registration failure is visible in API and UI |
| **G7** | Backend suite green, coverage ≥ 83%; frontend typecheck clean |
| **G8** | The full 9-step manual journey passes, with screenshots |

**G3 is the phase's reason for existing.** If every other gate passes and G3 fails, the phase has not delivered its purpose.

---

## Notes for the executor

- **Order matters.** T-1.1 before T-1.2 (the URL must be reachable before you can verify the id resolves). Phase 0 before T-1.3 (you cannot read a contract from a repo you do not have).
- **Do not attempt Solution 2 routing.** If you find yourself adding `PathPrefix` alternatives to catch assets, stop — that path was already explored across eight commits and cannot work.
- **T-1.3 is the win.** If time runs short, land T-1.3 and defer T-1.6. Branding that visibly works changes the product's story; a registration badge does not.
- **Watch for the codebase's signature failure mode.** Several defects here share one shape: something fails, gets replaced with a plausible default, and reports success. When adding error handling, make failure *visible* — that is the standing instruction, not a preference.
- Landing T-1.3 without T-1.6 risks a confusing state: branding works for templates that registered, silently does not for those that fell back. If you must defer T-1.6, at minimum log the fallback at `warning` with the template id.
