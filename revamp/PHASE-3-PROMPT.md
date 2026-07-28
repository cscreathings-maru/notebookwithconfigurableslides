# Phase 3 — Scope Resolution: One Pipeline, One Set of Guarantees

**Duration:** 5–8 days · **Severity:** 🟡 Medium (architectural) · **Requires:** Phase 2 gate `PASS`

---

## Role & context

**NoteAI** turns uploaded documents into branded slide decks.

- `frontend/` — Next.js 14 App Router; single API client at `src/services/api.ts`
- `backend/` — FastAPI at `/api/v1`; Postgres, Redis/Arq, MinIO
- `presenton/` — slide renderer, vendored, served same-origin at `/editor`
- `open-notebook` — embeddings + retrieval, scoped per project as of Phase 2

After Phases 0–2 the product **works and is trustworthy**. Phase 3 addresses the one genuine architectural problem in the codebase: **it is two products wearing one repository.**

This phase is mostly **deletion**. That is intentional and it is the point.

---

## The problem: goal drift

`specs/001-presentation-notebook-llm/spec.md` (2026-06-19) defines a **multi-tenant SaaS for Indonesian corporate teams**: governed stakeholder profiles → validated outline → consistency-enforced deck, with RBAC, quotas, and audit as **release blockers**.

The architecture implements that faithfully — immutable profile/template versions, an outline validator, a post-generation consistency gate, per-tenant BYOK, quota enforcement, metering.

**The product has since pivoted** to a NotebookLM-style single-tenant tool with configurable slides. Evidence: the last 15 commits, Bahasa Indonesia as the default output language, `LITE_MODE=true` as the shipping default, and the repository's own name.

The Studio path — the one users actually use — routes around essentially all of the governance:

| Governance mechanism | Governed path | Studio (freeform) path |
|---|---|---|
| Stakeholder profile | required | **none** |
| Outline validation | required | **bypassed** |
| Consistency gate | enforced | **skipped** (`generation/worker.py:77-87`) |
| Quota enforcement | enforced | *(unified in Phase 2)* |
| Usage metering | recorded | *(unified in Phase 2)* |
| Template governance | approved versions only | falls back to any version (`freeform_service.py:77-79`) |

**Cost of the split:**

- ~800 LOC of governance machinery maintained for a path few users take
- Test effort inverted: `generation/service.py` sits at 94% coverage while `freeform_service.py` — the path users exercise — sits at 38%
- Every new feature must be built, tested, and reasoned about twice
- Two divergent sets of guarantees behind one endpoint (`api/generations.py:91-102`)

Paying for both and getting the guarantees of neither.

---

## The decision (make it before writing code)

This phase **requires a product decision**. It is not the executor's to make alone — confirm with the product owner and record it in the report.

### Option A — NotebookLM-style is the product ✅ Recommended

Make freeform the only path. Delete outline/profile/consistency. Keep templates for branding. **Keep tenancy scoping** — it costs nothing at runtime and preserves the option to sell multi-tenant later.

**Evidence for:** the last 15 commits, the Bahasa Indonesia default, `LITE_MODE=true` shipping, the repository name, and the stated goal of a NotebookLM-like product with configurable slides.

**Deletes:** `outline/` (5 modules), `generation/service.py`, `generation/mapper.py`, `generation/consistency.py`, `registry/` profile half, `OutlinePanel.tsx`, `GeneratePanel.tsx`, `ProfileEditor.tsx`, `SectionStructureBuilder.tsx`, `/profiles`

**Keeps:** freeform generation, templates + branding, guide, chat, sources, usage, tenancy

### Option B — Governed enterprise decks are the product

Make the Studio path *inherit* profile governance rather than bypass it. Freeform becomes a governed mode with a default profile.

**Evidence for:** the original spec, the consistency-enforcement differentiator, "stakeholder-tailored" as the core value proposition.

**Cost:** significantly more work than A. Requires a UX that makes governance feel light rather than bureaucratic — the reason it was bypassed in the first place.

### Option C — Keep both

**Not recommended.** This is the status quo, and §"The problem" is the bill for it.

> **The tasks below assume Option A.** If B is chosen, stop and request a rewritten phase prompt — the task list inverts.

---

## Scope

### In scope (Option A)

| Task | Purpose |
|---|---|
| T-3.0 | Record the decision |
| T-3.1 | Retire the governed pipeline |
| T-3.2 | Split the polymorphic `/generations` endpoint |
| T-3.3 | Remove the `run_transformation` / `provider_config` dead abstraction |
| T-3.4 | Replace polling with server-pushed status |
| T-3.5 | Real template preview |
| T-3.6 | Raise freeform-path coverage to match what it replaced |

### Out of scope

- Engine contract tests against real containers → **Phase 4**
- Multi-tenant re-enablement → **Phase 4**
- Ingestion worker-blocking rework → **Phase 4**

---

## Tasks

### T-3.0 — Record the decision 📋

**Before any code changes.** Write `docs/adr/001-single-generation-pipeline.md`:

- Which option was chosen and by whom
- Evidence considered (this document's table)
- What is deleted, what is kept, what becomes harder
- What would have to be true to revisit it

**Acceptance:** ADR committed and approved by the product owner. **No deletion begins before this exists** — a future maintainer must be able to learn why 800 lines vanished without reading a diff.

---

### T-3.1 — Retire the governed pipeline 🟡

**Depends on:** T-3.0

**Remove (backend):**

| Path | Note |
|---|---|
| `src/outline/` | builder, validator, schema, service, repository |
| `src/generation/service.py` | governed generation service |
| `src/generation/mapper.py` | **migrate brand-token logic first** (Phase 1 T-1.3 put shared code in `generation/brand.py` — verify nothing governed-only remains) |
| `src/generation/consistency.py` | consistency gate |
| `src/generation/artifact.py` | PPTX inspection — **only if** used solely by the consistency gate. Verify. |
| `src/api/outlines.py` | route + router registration |
| `src/api/profiles.py` | route + router registration |
| `src/registry/` profile half | `ProfileService`, `ProfileRepository` — keep the template half |
| `src/models/outline.py` | see migration note |
| `src/schemas/outline.py` | |

**Remove (frontend):** `OutlinePanel.tsx`, `GeneratePanel.tsx`, `VersionHistoryPanel.tsx` *(verify — it may serve freeform history too)*, `registry/ProfileEditor.tsx`, `registry/SectionStructureBuilder.tsx`, `app/(app)/profiles/page.tsx`, profile/outline methods in `services/api.ts`, `/profiles` nav entry.

**Data migration — handle carefully:**

1. `Generation` keeps `outline_id`, `profile_id`, `profile_version` as **nullable** columns. **Do not drop them.** Historical generations reference them, and the spec's traceability requirement (User Story 3) is worth preserving even for a retired path.
2. Retain `outlines` and `stakeholder_profiles` tables as read-only history, or export before dropping. **Never drop a table holding tenant data without an exported backup and explicit sign-off.**
3. Alembic migration must be reversible and tested both directions.

**Simplify `generation/worker.py`:** with `profile_id` always `NULL` for new generations, the branch at `:75-87` becomes the only path. Keep the branch **only** if historical generations still need re-processing — otherwise delete it and the consistency import.

**Remove the now-dead tests** — `test_outline_determinism.py`, `test_registry_versioning.py` (profile half), governed-path integration tests. **Removing a test for deleted code is correct; state it explicitly in the report** so the count drop is not read as a regression.

**Acceptance:**
- Governed modules deleted; no dangling imports (`ruff` clean)
- Backend suite green; every removed test maps to removed code, itemised in the report
- Historical generations still readable via `/generations/{id}`
- Migration round-trips
- ~700–900 LOC net removed

---

### T-3.2 — Split the polymorphic endpoint 🟡

**Depends on:** T-3.1

**Problem:** `POST /projects/{id}/generations` dispatches to two services based on which nullable field is present (`api/generations.py:91-102`), and `GenerationCreate` (`schemas/generation.py:21-43`) carries both paths' fields with everything optional. The OpenAPI schema cannot express "exactly one of these groups".

With one pipeline, this collapses naturally.

**Change:**

1. `GenerationCreate` keeps only freeform fields. Drop `outline_id`. Make `content_source` **required** — the `if/elif/else` dispatch disappears.
2. Tighten validation with a discriminated union on `content_source`, so `custom_markdown` is required for `custom` and `chat_message_id` for `chat` — enforced by Pydantic rather than by the runtime checks currently in `freeform_service._resolve_content` (`:126-180`).
3. Rename `FreeformGenerationService` → `GenerationService`. "Freeform" only meant "not the other one"; with one pipeline the qualifier is noise.
4. Update `services/api.ts` — remove `createGeneration`, keep `generateDeck`.

**Acceptance:**
- One request schema; `content_source` required
- Invalid combinations rejected at validation, not at runtime
- OpenAPI expresses the contract accurately
- No `if content_source is not None` dispatch remains

---

### T-3.3 — Remove the dead analysis abstraction 🟡

**Problem:** `open_notebook.run_transformation` (`:113-125`) is a documented no-op that returns its input. `add_source` (`:57-81`) accepts `provider_config` only to discard it. `provider_config` is threaded through five call layers to be thrown away.

The docstring is honest — *"The transformation step is intentionally a no-op"* — but the abstraction still costs every reader a trace to discover it. The spec's "analyzes them with Open Notebook" is really "embeds and retrieves".

**Change:**

1. Delete `run_transformation`. At `ingestion/service.py:200-202`, set `analysis_ref = source.on_source_id` directly with a comment stating why.
2. Remove `provider_config` from `OpenNotebookClient.add_source` and every caller that only forwards it. **Keep it** where genuinely used (`LlmClient`, `TenantLlmConfigService`).
3. Consider dropping `Source.analysis_ref` if nothing reads it — verify with a grep before deciding.
4. Correct the module docstring (`open_notebook.py:1-9`) to describe what the client does: embed and retrieve.

**Acceptance:**
- No no-op engine method remains
- `provider_config` appears only where consumed
- Docstrings match behaviour
- `ruff` clean; suite green

---

### T-3.4 — Replace polling with server-pushed status 🟡

**Problem:** `StudioPanel.pollUntilDone` (`:91-105`) issues up to **200 sequential requests** per deck at 2.5s intervals, each triggering a `listGenerations` refetch — so roughly 400 requests per generation. Acceptable at demo scale; not at ten concurrent users.

**Change:**

1. Add SSE at `GET /api/v1/generations/{id}/events`, emitting status transitions.
2. `StudioPanel` subscribes; falls back to polling if SSE fails.
3. If SSE proves awkward behind Traefik, exponential backoff (2s → 30s cap) is an acceptable smaller win. **Record which was chosen and why.**
4. Remove the redundant `loadDecks()` on every poll tick (`:96`).

**Acceptance:**
- A generation completes with ≤ 5 status requests (SSE) or demonstrably fewer (backoff)
- Terminal states still update the UI promptly
- Fallback verified by disabling SSE

---

### T-3.5 — Real template preview 🟡

**Problem:** `/templates` shows colour swatches from stored `brand_tokens` — a preview of *configuration*, not of *output*. After Phase 1, branding genuinely reaches the renderer, so a real preview is now possible and is the natural payoff.

**Change:**

1. On template approval, generate a 2–3 slide sample deck via Presenton using that template.
2. Render the first slide to an image; store in MinIO under the tenant prefix.
3. Add `preview_image_url` to `TemplateResponse`; render a thumbnail in the templates table.
4. Regenerate on new version; handle failure per Phase 1's T-1.6 posture — **visible degradation, never a silent default**.

**Acceptance:**
- An approved template shows a thumbnail of an actual rendered slide
- Preview generation failure is visible, not silent
- Preview generation does not block approval (async)

---

### T-3.6 — Raise coverage on the surviving path 🟡

**Problem:** coverage is inverted. The retired governed path sat at 94%; `freeform_service.py` — now the *only* path — sits at **38%** (`:56-124` and `:134-180` uncovered).

**Change:**

1. Cover all four `content_source` branches in `_resolve_content`: `summary`, `notebook`, `chat`, `custom`.
2. Cover error paths: missing `custom_markdown`, missing `chat_message_id`, no guide yet, no indexed content.
3. Cover template resolution including the approved-vs-latest fallback (`:77-79`) — **which becomes the sole governance point once profiles are gone**, so it needs real coverage.
4. Cover `generation/worker.py` end to end with a fake Presenton.

**Acceptance:**
- `generation/` package coverage ≥ 85%
- Every `content_source` branch covered, success and failure
- Overall backend coverage ≥ 88%

---

## Verification

```bash
# Backend
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
# expect: coverage >= 88%; test count DOWN (deleted code) but every deletion itemised

# Dead code
cd backend && ./.venv/bin/ruff check src/
cd frontend && npx knip   # unused exports/files after deletion

# Migration round-trip
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head

# Frontend
cd frontend && npm run typecheck && npm run test:coverage

# E2E — must still pass unchanged
npx playwright test

# LOC delta
git diff --stat <phase-2-sha>..HEAD | tail -1
```

### Manual verification

1. **Historical data:** open a generation created before Phase 3 → still renders, provenance intact
2. **Full journey:** the Phase 1 nine-step journey passes unchanged
3. **Removed surfaces:** `/profiles` returns 404; nav no longer links it
4. **Preview:** approve a template → thumbnail appears

---

## Deliverable

`revamp/reports/PHASE-3-REPORT.md`, using [`TEST-REPORT-TEMPLATE.md`](TEST-REPORT-TEMPLATE.md).

**Phase 3 reports differently from every other phase: test count goes *down*.** §4.1 must therefore include a deletion ledger:

| Deleted test | Covered code that was deleted | Justified |
|---|---|---|
| `test_outline_determinism.py` | `src/outline/builder.py` | ✅ |

Without it, the phase reads as a coverage regression. §6 must explicitly confirm that **no test was deleted whose subject survived**.

§3 must link the ADR from T-3.0.

---

## Exit gate

| # | Criterion |
|---|---|
| **G1** | ADR committed and approved before any deletion |
| **G2** | One generation pipeline; no dual-path dispatch remains |
| **G3** | Every deleted test maps to deleted code, itemised in the ledger |
| **G4** | Historical generations still readable with provenance intact |
| **G5** | Migration round-trips; no tenant data dropped without exported backup |
| **G6** | `generation/` coverage ≥ 85%; overall ≥ 88% |
| **G7** | Phase 1 nine-step journey and all Playwright smoke journeys still pass |
| **G8** | `ruff` and `knip` report no dead code |
| **G9** | Net LOC reduced by ≥ 500 |

**G3 and G4 are the risky ones.** Deleting a pipeline is easy; deleting it without silently dropping coverage or orphaning historical data is the actual work.

---

## Notes for the executor

- **Do not start without T-3.0.** A future maintainer finding 800 deleted lines with no ADR will assume it was a mistake and consider reverting it.
- **Deletion is the deliverable.** Resist replacing the governed pipeline with a lighter abstraction "just in case" — YAGNI. The ADR records how to bring it back if the product turns.
- **Never drop a table with tenant data** without an exported backup and written sign-off. Nullable columns cost nothing; keep them.
- **Verify before deleting `artifact.py` and `VersionHistoryPanel.tsx`.** Both are plausibly shared with the surviving path. Grep first.
- If the product owner picks **Option B**, stop and request a rewritten prompt. Do not attempt to translate this task list — it inverts.
- Expect this phase to feel unproductive: no new user-facing capability except T-3.5. Its value is that every subsequent feature costs half as much to build and test.
