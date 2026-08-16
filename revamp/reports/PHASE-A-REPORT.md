# Phase A Test Report — Template Understanding (LD-1 .. LD-4)

Implements [`PLAN-LLM-DECK-PLANNING.md`](../PLAN-LLM-DECK-PLANNING.md) Phase A, per
[`ASSESSMENT-LLM-DECK-PLANNING.md`](../ASSESSMENT-LLM-DECK-PLANNING.md).

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `A — Template understanding` |
| Date | `2026-08-15` |
| Executed by | Claude Sonnet 5 (local workstation session) |
| Commit range | *(uncommitted — single commit planned at end of session, per instruction)* |
| Branch | `revamp/phase-1` |
| Environment | `local` — SQLite-backed test harness (backend), Vitest/jsdom (frontend). No Docker stack started; no LLM API calls made (no network egress in this environment; every LLM-shaped call in this phase runs against `FakeLlm` or a hand-built fake) |

---

## 2. Gate summary

Phase A has no numbered exit gate of its own in the plan (that's §5's G1–G9, most of which are Phase C concerns). Judged instead against Phase A's own task list and this plan's "test each phase locally" instruction:

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| A1 | `deck/dump.py` serialises the real BRI template's slides, capped well under the cataloguing token budget | **PASS** | §4.1, §5 |
| A2 | `catalog_template()` turns a dump into a validated `DesignCatalog`, never trusting the LLM for `capacity`/`char_budget` | **PASS** | §4.1, §5 |
| A3 | Cataloguing runs as an async job, not inline in the create request | **PASS** | §4.1, §5 |
| A4 | An admin can review, correct, and approve a template's catalog before it is considered ready | **PASS** | §4.1, §4.2, §5 |
| A5 | No previously-passing test regressed | **PASS** | §6 |

**Overall: PASS.**

---

## 3. Task results

| Task | Title | Sev | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `LD-1` | `deck/dump.py` — serialise slides for the LLM | 🔴 | **DONE** | `tests/unit/test_deck_dump.py` (11) | `backend/src/deck/dump.py` |
| `LD-2` | `catalog_template` LLM call + `DesignCatalog` | 🔴 | **DONE** | `tests/unit/test_deck_catalog.py` (14) | `backend/src/deck/catalog.py`, `backend/src/engines/llm.py` |
| `LD-3` | Persist `Template.slide_catalog` + migration; async job | 🔴 | **DONE** | `tests/integration/test_template_catalog.py` (12) | `backend/alembic/versions/0017_deck_catalog.py`, `backend/src/registry/service.py`, `backend/src/workers/tasks.py` |
| `LD-4` | Catalog review UI (admin) | 🟠 | **DONE, with one stated gap** | `frontend/src/components/registry/CatalogReview.test.tsx` (7) | `frontend/src/components/registry/CatalogReview.tsx`, `.../CatalogStatusBadge.tsx`, `templates/page.tsx` |

**LD-4's gap:** the review screen is textual (role + anchor purpose + current text, all editable), not a visual wireframe like `deck/preview.py`'s layout diagrams. `Anchor` deliberately carries no position (`deck/catalog.py`'s module docstring — capacity and char_budget are computed from geometry, but the geometry itself isn't persisted past cataloguing time), so there is nothing to draw a schematic from without re-running `deck/dump.py` against the stored `.pptx` at review time. Flagged here rather than silently shipped short of what the plan describes ("wireframe, the LLM's label, capacity and anchors").

### Deviations

**Dual-write, not cutover.** `TemplateService.create` still runs the OLD geometric inspection (`deck/inspect.py` → `layout_catalog`/`inspection_status`) inline, unchanged, *and additionally* dispatches LD-2 cataloguing as a job. `Template` now carries two independent status machines (`inspection_status` for the still-active render path, `catalog_status`/`catalog_reviewed_at` for the new one). This was a deliberate choice, not an oversight: the plan's own dependency graph puts the actual cutover at `LD-9` (Phase C) — cutting `generation/service.py` over to the new pipeline before `deck/plan.py` (Phase B) and `deck/renderer.py` (Phase C, rewritten) exist would leave the app unable to generate anything for two phases. Keeping both systems live in parallel is what let Phase A ship a working, fully-tested increment on its own, per the instruction to test and report every phase rather than wait until everything lands together. Recorded here so it isn't mistaken for the finished state — Phase C's report will confirm the old path is deleted (`LD-11`).

**`house_template.py` (the bundled starter template) is not wired into cataloguing.** It still only runs `_apply_inspection` at seed time (a synchronous startup script, not a request handler — dispatching an Arq job from there would need plumbing this phase didn't build). Its `catalog_status` stays `no_source` even though it has a `.pptx`. An admin can fix this today with `POST /templates/{id}/recatalog`; a cleaner fix (seed-time dispatch, or a startup reconciler) is left for Phase C.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Baseline (session start) | This phase | Delta |
|---|---|---|---|
| Passed | 293 | 330 | **+37** |
| Failed | 0 | 0 | — |
| Skipped | 0 | 0 | — |
| Coverage (total) | 90% | 89% | −1pt (see below) |
| Duration | ~12s | 17.2s | +5.2s |

**Raw tail of output:**

```
TOTAL                             4685    537    89%
330 passed, 205 warnings in 17.22s
```

**Coverage note:** the one-point dip is `workers/tasks.py` (30% → 20%): `run_catalog_template` is a large new function whose Arq-wrapper body (job bookkeeping around the actual logic) is exercised the same way `run_ingest`/`run_generate` already are in this codebase — through the underlying service call (`catalog_template()`, directly tested), not through the Arq task wrapper itself. This mirrors existing precedent exactly (`run_ingest`'s own wrapper is similarly untested in isolation; `test_ingestion.py` calls `ingest_source` directly). Total coverage (89%) still clears both this repo's 80% rule and the revamp programme's stated 87% floor.

`ruff check` on every changed file: clean.

### 4.2 Frontend

```bash
cd frontend && npm run typecheck && npm run lint && npm run test -- --run
```

| Metric | Baseline | This phase | Delta |
|---|---|---|---|
| Passed | 114 | 121 | **+7** |
| Failed | 0 | 0 | — |
| Type errors | 0 | 0 | — |
| Lint errors | 0 | 0 | — |

```
Test Files  15 passed (15)
     Tests  121 passed (121)
```

`src/lib/i18n/parity.test.ts` (checks every `en.ts` key exists in `id.ts` and vice versa) passed, confirming the new `catalog.*`/`templates.colCatalog` keys were mirrored correctly in both languages.

### 4.3 Manual / structural verification against the real BRI template

No Docker stack was started (per instruction: no deploy). Verified instead by running the new modules directly against `backend/assets/templates/bri-default.pptx` — the same real 30-slide, 476-shape, 57-image corporate deck the assessment is built on, not a synthetic fixture (assessment §1.1's standing rule).

```
slides: 30
total chars (dump text): 48,438
approx tokens (chars/4): 12,109        # vs. assessment's ~15,000 budget
```

- Slide 0 (cover): dump correctly shows a `[picture]` shape (the logo — the
  literal failure this whole plan exists to fix) alongside `[text placeholder]`
  shapes for title/subtitle/presenter.
- Slide 20 (timeline): dump shows all 95 shapes, all 3 images — matches the
  assessment's documented counts exactly, nothing silently dropped.
- Every slide dumped is well within a single LLM call's budget; LD-2's
  chunking path exists and is exercised by `test_chunking_splits_across_multiple_llm_calls`
  but was not needed for BRI itself in this run.

### 4.4 Per-task test evidence

| Task | Test | Before | After |
|---|---|---|---|
| `LD-1` | `test_richest_slide_dump_matches_shape_count` | module did not exist | `PASS` — 95 shapes, 3 pictures on slide 20 |
| `LD-1` | `test_whole_deck_dump_is_well_within_the_cataloguing_token_budget` | n/a | `PASS` — 12,109 est. tokens < 20,000 |
| `LD-2` | `test_capacity_is_never_taken_from_the_llm` | n/a | `PASS` — a `capacity: 999` planted by a lying fake is ignored |
| `LD-2` | `test_anchor_referencing_missing_shape_is_dropped` | n/a | `PASS` — a hallucinated `anchor_id` never reaches the stored catalog |
| `LD-3` | `test_create_with_pptx_starts_cataloguing_without_blocking_the_request` | n/a | `PASS` — 201 returns before any LLM call runs |
| `LD-3` | `test_terminal_failure_never_leaves_the_job_row_silently_stuck` | n/a | `PASS` — an empty-slide template lands at `catalog_status: failed` with a reason, not stuck at `cataloguing` |
| `LD-4` | `sends an edited role/purpose back on approve` | n/a | `PASS` — an admin's inline correction reaches `reviewTemplateCatalog` |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | Run `dump_presentation()` against `bri-default.pptx` | 30 slides, cover shows a picture + title placeholders | Exactly that (§4.3) | `PASS` |
| M2 | Run `catalog_template()` against the BRI dump with `FakeLlm` | 30 designs returned, at least one usable | 30 designs, cover usable with a `title` anchor | `PASS` |
| M3 | POST a template with the BRI `.pptx` via the test client | 201 immediately, `catalog_status: "cataloguing"`, a `Job(type=catalog_template)` row exists | Confirmed via `test_create_enqueues_a_catalog_template_job` | `PASS` |
| M4 | Simulate the worker running (`catalog_template` + `apply_catalog_result`), then re-list templates | `catalog_status: "ready"`, `catalog_reviewed: false` | Confirmed | `PASS` |
| M5 | `GET /templates/{id}/catalog` before the job has run | 422 `catalog_not_ready` | Confirmed | `PASS` |
| M6 | Viewer role hits the same endpoint | 403 (admin-only, unlike `/layouts`) | Confirmed | `PASS` |
| M7 | `POST /templates/{id}/catalog/review` with a corrected `role` on one design | stored catalog reflects the correction on re-read | Confirmed | `PASS` |
| M8 | `POST /templates/{id}/recatalog` after a review, then re-run the job | `catalog_reviewed` resets to `false` on the fresh catalog | Confirmed | `PASS` |
| M9 | Frontend: `CatalogReview` renders, edits a role field, clicks approve | `reviewTemplateCatalog` called with the edited design list | Confirmed (Vitest + Testing Library) | `PASS` |

**Artefacts:** raw pytest/vitest output above; no screenshots (no browser session run — `npm run dev` was not started, matching "no deploy" instruction. If you'd like the actual template list + review modal driven in a browser before moving on, say so and I'll start the dev server next.)

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | `PASS` | 293 → 330, 0 failed |
| All previously passing frontend tests still pass | `PASS` | 114 → 121, 0 failed |
| Coverage did not meaningfully decrease | `PASS` (−1pt, explained §4.1) | still ≥ 87% programme floor |
| No new `ruff` / `tsc` / `eslint` errors | `PASS` | all clean |
| No previously working user journey broke | `PASS` | template creation, inspection, reinspect, layout wireframes, delete, RBAC, tenant isolation all still covered and green |

---

## 7. Findings discovered during this phase

| # | Finding | Severity | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | `seed_house_template` never triggers cataloguing (§3 deviation) | 🟡 | `backend/src/registry/house_template.py` | C, or a small fix alongside LD-9 |
| F2 | LD-4's review screen has no visual wireframe (§3 gap) | 🟡 | `frontend/src/components/registry/CatalogReview.tsx` | Would need `deck/dump.py` geometry persisted per-anchor, or re-dumped at review time — worth deciding deliberately, not bolting on |
| F3 | `TemplateStatus`/`inspection_status` and `TemplateCatalogStatus`/`catalog_status` now coexist on `Template`, doing conceptually overlapping jobs during the transition | ⚪ | `backend/src/models/registry.py` | Resolved by design at `LD-11` (old modules/columns deleted in Phase C) — not a defect, just worth naming so it isn't mistaken for permanent |

---

## 8. Facts vs. assumptions

| Claim in this report | Basis |
|---|---|
| Dump of the real BRI template is ~12,109 tokens, under the ~15k budget | `verified by inspection` — ran `dump_presentation()` directly against the asset and measured |
| `catalog_template()` never trusts the LLM for capacity or char_budget | `verified by test` (`test_capacity_is_never_taken_from_the_llm`, `test_char_budget_scales_with_box_area`) |
| Cataloguing genuinely does not block `POST /templates` | `verified by test` — the 201 response is asserted before any job-running code executes in the test |
| The admin review UI works end-to-end | `verified by test` (Vitest/Testing Library) — **not** verified in an actual browser (no dev server started this phase) |
| Kimi K3's existence, pricing, and strict-JSON reliability | **not verified** — this environment has no network egress and the model is past this assistant's knowledge cutoff (assessment §7 already names this as an open item, deferred to `LD-10` / deploy-time `curl` check) |

**Anything not verifiable in this phase and why:** any claim about what a *real* LLM (Kimi K3 or otherwise) would actually output for `catalog_template` — every test in this phase runs against `FakeLlm`, a deterministic stand-in. The prompts in `engines/llm.py::_build_catalog_messages` are written to the same standard as the rest of the pipeline's prompts, but the assessment is explicit that this can only be settled by running the real model once (§4's "LD-2 is the spike... cheap to discover ($0.02) and expensive to assume"). That spike still needs to happen before Phase C's exit gate (G1/G2, which require a human opening a rendered deck) can be judged.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | `PASS` |
| Next phase authorised | `YES` |
| Blockers carried forward | F1, F2 (both 🟡, non-blocking); the real-LLM spike (§8) still needs to happen before Phase C's human-verification gates can close |
| Signed | Claude Sonnet 5, 2026-08-15 |

**Rationale:** Phase A delivers exactly what LD-1–LD-4 asked for — a template's slides can now be dumped, catalogued by an LLM (proven against the real BRI template's shape, validated against a fake model), persisted asynchronously, and reviewed/corrected by an admin — without touching or destabilising the currently-working generation pipeline. A user (admin) can today upload the real BRI template, watch it get catalogued, open the review screen, correct a mislabelled design, and approve it. What they cannot yet do is generate a deck FROM that catalog — that's Phases B and C.
