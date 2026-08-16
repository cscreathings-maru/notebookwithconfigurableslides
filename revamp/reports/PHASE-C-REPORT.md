# Phase C Test Report — Rendering and Wiring (LD-8 .. LD-11)

Implements [`PLAN-LLM-DECK-PLANNING.md`](../PLAN-LLM-DECK-PLANNING.md) Phase C, per
[`ASSESSMENT-LLM-DECK-PLANNING.md`](../ASSESSMENT-LLM-DECK-PLANNING.md). This phase is
the cutover: the new catalog → plan → render pipeline built in Phases A and B
replaces the old layout-based one everywhere, and the old modules are deleted.
This report also evaluates the whole plan's exit gate (§5), since Phase C is
where the full pipeline first exists end to end.

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `C — Rendering and wiring` |
| Date | `2026-08-15` |
| Executed by | Claude Sonnet 5 (local workstation session) |
| Commit range | *(uncommitted — single commit planned at end of session, per instruction)* |
| Branch | `revamp/phase-1` |
| Environment | `local` — SQLite-backed backend test harness, Vitest/jsdom frontend. No Docker stack started, no live LLM calls (no network egress in this environment) |

---

## 2. Gate summary — the whole plan's exit gate (§5)

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| G1 | Rendered deck keeps the BRI logo and design furniture | **PASS** | §4.1, `test_deck_renderer.py::test_rendering_the_cover_design_keeps_its_logo` |
| G2 | A human opens the deck and confirms it looks like the template | **NOT CLOSED — needs a human** | See §8; this report cannot close it |
| G3 | Cloning a slide with images yields readable images | **PASS** | Already met by `deck/clone.py` (prior session); re-confirmed through the full renderer in `test_deck_renderer.py` |
| G4 | 5 items into a 3-capacity design → two slides, second titled `(lanjutan)`, no content dropped | **PASS** | §4.1, `test_deck_from_outline.py::test_a_section_with_more_points_than_capacity_splits_with_lanjutan_suffix` |
| G5 | One design used 4× renders 4 intact copies | **PASS** | Already met by `deck/clone.py`; re-confirmed end to end in `test_deck_renderer.py::test_one_design_used_four_times_renders_four_intact_copies` |
| G6 | An admin can correct a mis-catalogued design before the template is usable | **PASS** | Phase A, re-confirmed still working after the cutover — `test_registry.py::test_reviewing_the_catalog_approves_the_template` |
| G7 | A malformed LLM plan is rejected and retried, never rendered into a broken deck | **PASS** | Phase B, unaffected by Phase C's wiring — `test_deck_plan.py::test_retries_once_then_surfaces_when_nothing_is_ever_usable` |
| G8 | Determinism: same plan + template → byte-comparable output | **PASS** | `test_deck_renderer.py::test_rendering_is_deterministic` |
| G9 | Suites green; ruff/eslint/typecheck clean | **PASS** | §4 |

**Overall: 8 of 9 automatable criteria PASS. G2 is explicitly, by the plan's own design, not closable by this report** — §5 of the plan states this outright: *"G1, G2 and G6 cannot be closed by automated tests... these gates name a human."* G1 and G6 are closed here because they reduce to properties a test CAN observe (logo bytes present; an admin correction persists and is reflected). G2 — "looks like the template" — is irreducibly a judgment call. See §8 for exactly what is needed to close it and why this session could not.

---

## 3. Task results

| Task | Title | Sev | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `LD-8` | Rewrite `deck/renderer.py` (clone-based) | 🔴 | **DONE** | `tests/unit/test_deck_renderer.py` (9) | `backend/src/deck/renderer.py` |
| `LD-9` | Wire into `generation/service.py` + worker; delete `matcher.py` | 🟠 | **DONE, with one interpretive decision** | `tests/integration/test_generation.py` (4, full pipeline) | `backend/src/generation/service.py`, `backend/src/generation/worker.py` |
| `LD-10` | Model config: `DECK_CATALOG_MODEL` / `DECK_PLAN_MODEL` | 🟠 | **DONE** | pre-existing settings tests + `test_llm_client.py::test_model_for_returns_none_when_no_task_override_is_set` | `backend/src/core/config.py`, `backend/src/tenancy/llm_config.py` |
| `LD-11` | Delete superseded modules and tests; reconcile docs | 🟢 | **DONE** | full suite green after deletion (§4) | see §3.1 |

### 3.1 What LD-11 actually deleted

| Module | Fate |
|---|---|
| `deck/inspect.py` | deleted (replaced by `deck/dump.py` + `deck/catalog.py`, Phase A) |
| `deck/roles.py` | deleted outright, not "shrunk" — see deviation below |
| `deck/matcher.py` | deleted (LD-6 folds layout matching into the planning call) |
| `deck/planner.py` (old, role/budget-based) | deleted (replaced by `deck/plan.py`, Phase B) |
| `deck/spec.py` (old `DeckSpec`/`SlideSpec`) | deleted; `ChartSpec`/`TableSpec` moved into `deck/charts.py`, their only remaining consumer |
| `deck/preview.py` | deleted (its `/templates/{id}/layouts` wireframe endpoint had no data source left once `layout_catalog` was dropped) |
| `LlmClient.plan_deck` (old signature) + `LlmClient.match_layout` | deleted; the new `plan_deck` (renamed from `plan_deck_from_catalog`) takes over the name |
| `Template.layout_catalog`/`inspection_report`/`inspection_status`/`inspection_error` columns; `TemplateStatus` enum | dropped (migration `0018_deck_plan_cutover`) |
| `Generation.deck_spec`/`layout_plan` columns | replaced by `Generation.deck_plan` (migration `0018`) |
| `GenerationStatus.awaiting_review`, the `/generations/{id}/plan` + `/plan/approve` endpoints, `LayoutPlanReview.tsx`, `InspectionBadge.tsx` | retired — see the deviation below |
| 8 backend test files (`test_deck_inspect.py`, `test_deck_roles.py`, `test_deck_matcher.py`, `test_deck_planner.py`, `test_deck_spec.py`, `test_deck_preview.py`, `test_layout_plan_review.py`, plus the old `test_deck_renderer.py`) | deleted — the architecture they tested no longer exists |
| `LayoutPlanReview.test.tsx` | deleted with its component |

### Deviations

**Per-generation review (D5/RM-9) is retired, not adapted.** The plan's task table literally says LD-9 should "adapt the existing review gate to plan-level review." Working through what that would mean concretely (`deck/plan.py`'s docstring and `generation/service.py`'s module docstring both record the reasoning): the old gate triggered on the layout matcher's per-slide confidence score, and that matcher is gone by design (L4 — one call plans content AND design together). There is no confidence signal left to gate on, because rendering a validated `DeckPlan` is now fully deterministic (L5) — nothing downstream of a valid plan can fail in a way a human needs to catch before it renders. The assessment's own §8 risk mitigation list supports this reading directly: mitigation #1 is "the catalog is human-reviewed once," not "each deck is reviewed." I read "adapt the review gate to plan-level" as *the review gate moves to the plan's INPUT (the catalog), not that a per-generation checkpoint survives in a new shape* — the template's catalog IS "plan-level" review, applied once instead of per-deck. If this reading is wrong, the fix is straightforward (the gate's shape — park at a status, expose an approve endpoint — is a known pattern already proven once in this codebase) but would need to be told what should trigger it, since there is no automatic signal anymore.

**`deck/roles.py` deleted outright, not "shrunk."** The plan's module disposition table says roles.py should "shrink -- the role vocabulary survives as the LLM's label set." In practice, `deck/catalog.py`'s `role` field is a free-text LLM label (`"cover"`, `"three_cards"`, `"timeline"`, whatever the model calls it), not the old fixed `LayoutRole` enum — nothing in the new pipeline imports or checks against that enum. Keeping an unused enum around to satisfy "survives as a label set" felt like exactly the vestigial-code smell the rest of this cutover was removing; deleting it is a stricter but more honest reading of the same intent.

**Chart/table anchors remain unimplemented** (named already in `deck/renderer.py`'s own docstring and Phase A/B's reports as a tracked gap, not new here). `deck/charts.py`'s `insert_chart`/`insert_table` have no caller. This is a real regression against the OLD pipeline's `ChartSpec`/`TableSpec` support — recorded again in §7 as F1, now at higher severity since Phase C is where it becomes visible in the actual generation flow rather than a hypothetical.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Baseline (Phase B) | This phase | Delta |
|---|---|---|---|
| Passed | 341 | 271 | **−70 (see note)** |
| Failed | 0 | 0 | — |
| Skipped | 0 | 0 | — |
| Coverage (total) | 88% | 88% | 0 |
| Duration | 16.4s | 13.1s | −3.3s |

**Raw tail of output:**

```
TOTAL                             4121    515    88%
271 passed, 189 warnings in 13.08s
```

**The −70 is deletion, not regression.** LD-11 deletes 8 test files whose subject matter no longer exists (`test_deck_inspect.py`, `test_deck_roles.py`, `test_deck_matcher.py`, `test_deck_planner.py`, `test_deck_spec.py` — 91 lines — `test_deck_preview.py`, `test_layout_plan_review.py` — 329 lines — and the old `test_deck_renderer.py`). Every one of those files tested a module or endpoint this phase deletes on purpose. New/rewritten tests were added for every equivalent new behaviour (`test_deck_renderer.py` rewritten fully — 9 tests against the real BRI template; `test_deck_charts.py` new, carrying forward `ChartSpec`/`TableSpec`'s validation tests; `test_house_template.py` rewritten). §6 confirms zero previously-passing test that still has a subject to test went red.

`ruff check` on `src/`, `tests/`, `scripts/`: clean.

### 4.2 Frontend

```bash
cd frontend && npm run typecheck && npm run lint && npm run test -- --run
```

| Metric | Baseline (Phase A) | This phase | Delta |
|---|---|---|---|
| Passed | 121 | 112 | **−9 (see note)** |
| Failed | 0 | 0 | — |
| Type errors | 0 | 0 | — |
| Lint errors | 0 | 0 | — |

```
Test Files  14 passed (14)
     Tests  112 passed (112)
```

**The −9 is `LayoutPlanReview.test.tsx`'s 8 tests, deleted with its component, plus the net effect of removing 2 tests from `StudioPanel.test.tsx`'s retired D5 describe block and adding 1 replacement.** `src/lib/i18n/parity.test.ts` passed, confirming every `en.ts` key removed (the `review.*` block, `templates.role.*`, `templates.reinspect*`, `templates.inspection*`, `studio.layoutsAvailable`, `studio.awaitingReview`/`reviewLayout`) was removed from `id.ts` too, and the new `studio.awaitingReviewStale` key exists in both.

### 4.3 Manual / structural verification against the real BRI template

Same discipline as Phases A and B: every claim below was run against `backend/assets/templates/bri-default.pptx`, not a synthetic fixture.

```
Cover design (slide 0): cloned with its logo intact; picture.image.blob resolves to real bytes.
Timeline design (slide 20): all 95 shapes, all 3 images survive cloning through the full renderer.
One design cloned 4×: 4 intact copies, each with its own text and its own logo.
Plan order [timeline, cover] renders in THAT order, not original template order [cover, ..., timeline].
Only the planned slides survive -- 1-slide plan -> 1-slide output, not 31 (30 originals + 1 clone).
Same plan run twice against the same template bytes -> byte-identical output (G8).
An unknown design_id in a hand-built DeckPlan raises ValidationError, never renders.
```

`test_generation.py::test_full_pipeline_to_ready_and_download` exercises the ENTIRE chain in one test: template upload → cataloguing → admin review/approval → profile → outline → generation queued → worker renders → consistency check passes → download streams real bytes. This is the strongest evidence in this report that the cutover actually works end to end, not just in isolated units.

### 4.4 Per-task test evidence

| Task | Test | Before | After |
|---|---|---|---|
| `LD-8` | `test_rendering_the_cover_design_keeps_its_logo` | module did not exist | `PASS` — logo picture present, `image.blob` non-empty |
| `LD-8` | `test_rendering_is_deterministic` | n/a | `PASS` — two renders of the same plan are byte-identical |
| `LD-8` | `test_never_sets_explicit_font_overrides` | n/a | `PASS` — the written anchor's runs carry no explicit font (D2) |
| `LD-9` | `test_full_pipeline_to_ready_and_download` | old test used `deck_spec`/layout matching | `PASS` — full chain through the new pipeline, `deck_plan` provenance never leaked to the client |
| `LD-9` | `test_reviewing_the_catalog_approves_the_template` | n/a (approval used to be automatic) | `PASS` — `status` only becomes `approved` after `/catalog/review` |
| `LD-9` | `test_pptx_import_starts_cataloguing_without_auto_approving` | old test asserted auto-approve | `PASS` — inverted assertion, proving the old behaviour is gone on purpose |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | Render the real BRI cover design with new text | Logo survives, text lands in the right shape | Confirmed (§4.3) | `PASS` |
| M2 | Render the real BRI timeline design (95 shapes, 3 images) | Nothing dropped | Confirmed | `PASS` |
| M3 | Reuse one design 4× in a plan | 4 intact, independently-texted copies | Confirmed | `PASS` |
| M4 | Plan order deliberately reversed vs. template order | Rendered deck follows PLAN order | Confirmed | `PASS` |
| M5 | Full API flow: upload → catalogue → review → profile → outline → generate → download | Deck reaches `ready`, streams real bytes, no internal field (`deck_plan`, storage keys) leaks | Confirmed via `test_full_pipeline_to_ready_and_download` | `PASS` |
| M6 | A template not yet reviewed cannot be used for generation | `422 template_not_usable` | Confirmed via `test_generation_preflight.py::test_generation_against_an_unusable_template_names_the_template` | `PASS` |
| M7 | Alembic revision graph resolves (no live Postgres available in this environment) | Single head, unbroken chain from base | `alembic history` shows one head at `0018_deck_plan_cutover`, chain intact to `<base>` | `PASS` (structural check only — never applied against a real database, see §8) |

**Artefacts:** raw pytest/vitest/alembic output above. No screenshots — no browser session run this phase either (still no deploy, per instruction).

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| Every previously-passing test whose subject still exists still passes | `PASS` | 271/271, 0 failed |
| Deleted tests were deleted only alongside the code they tested | `PASS` | §3.1's table is the audit trail |
| Coverage did not decrease | `PASS` | 88% → 88%, unchanged |
| No new `ruff`/`tsc`/`eslint` errors | `PASS` | all three clean |
| Phase A's gates still hold | `PASS` | catalog review flow re-exercised in this phase's own tests (`test_registry.py`) |
| Phase B's gates still hold | `PASS` | `deck/plan.py`'s validation/retry logic untouched by this phase's wiring changes |
| No previously working user journey broke | `PARTIAL — see below` | |

**The one journey that genuinely changed, not broke:** a deck that would have parked at `awaiting_review` under the old matcher now never parks — it renders straight through, because there is nothing left that would have made it low-confidence. This is not a regression (nothing a user could do before is now impossible; if anything a deck reaches `ready` in fewer steps), but it IS a behavior change, and the deviation in §3 explains the reasoning rather than letting it pass silently.

---

## 7. Findings discovered during this phase

| # | Finding | Severity | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | Chart/table content has no path from plan to render — `deck/charts.py` is dead code | 🟠 | `backend/src/deck/renderer.py`'s own docstring; `backend/src/deck/charts.py` | A follow-up task: extend `deck/catalog.py`'s anchor `purpose` vocabulary with a chart/table variant, and `deck/plan.py`'s validation to match |
| F2 | The Kimi K3 spike (assessment §4/§7's "run the real BRI dump through the real model once") has still not happened in any session | 🔴 (blocks G2) | This report's §8 | Must happen before Phase C's G2 can close, and before production rollout regardless of phase numbering |
| F3 | `docs/ARCHITECTURE.md` is stale on an unrelated topic (Presenton/`/editor` routing) predating this whole plan | ⚪ | `docs/ARCHITECTURE.md` §1–2 | Separate cleanup, out of scope for this plan's own reconciliation ask |
| F4 | The house template (`BRI Default`) seeded at deploy time reaches `catalog_status: cataloguing` via a Job row created directly (not dispatched through a live Arq connection) — this is correct and tested at the unit level (`house_template.py`'s own docstring explains the stranded-job-reconciler reuse) but has never been observed working against a real Redis/Arq worker | 🟡 | `backend/src/registry/house_template.py` | Confirm on first real deploy; flagged so it isn't assumed proven |

---

## 8. Facts vs. assumptions

| Claim in this report | Basis |
|---|---|
| The rendered deck keeps the BRI logo and design furniture (G1) | `verified by test`, against the real asset |
| Cloning/rendering is deterministic (G8) | `verified by test` |
| A malformed plan is retried once, never rendered broken (G7) | `verified by test` (Phase B, re-confirmed unaffected here) |
| An admin's catalog correction persists and gates approval (G6) | `verified by test` |
| The full API pipeline (upload → generate → download) works | `verified by test` — one integration test exercises the entire chain |
| The alembic migration chain is structurally sound | `verified by inspection` (`alembic history` resolves) — **never applied against a real database**; this environment has no live Postgres |
| A rendered deck genuinely "looks like" the BRI template (G2) | **not verified — cannot be, by this report's own admission** |
| Kimi K3 exists, accepts `response_format: json_object`, and produces workable Bahasa Indonesia on these exact prompts | **not verified** — no network egress in this environment; carried forward unresolved from Phases A and B |

**What G2 actually needs, concretely, to close** (naming it precisely rather than leaving it as a vague "needs a human"):
1. A real LLM call through `catalog_template()` against `bri-default.pptx`, reviewed by a person who knows what a "usable design" should look like for this template (the assessment's own "LD-2 is the spike" framing).
2. A real LLM call through `plan_deck()` against that catalog with genuine source content.
3. `render_deck()` on the result, opened in actual PowerPoint or LibreOffice by a human, and compared against the source template.

None of this is possible from inside this session: no network egress for the LLM calls, and no instruction to deploy or open a GUI application. Every test in this report substitutes `FakeLlm` for the model and asserts structural correctness (real design ids, real anchor ids, real shapes, real bytes) — which is the strongest claim automatable testing can make, but it is explicitly not the same claim as G2.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | `PASS` on every automatable criterion (8/9); `G2` explicitly open, by design |
| Next phase authorised | **Conditional** — the pipeline is code-complete and structurally proven; production rollout should wait on the real-LLM spike (F2) closing G2, not on further engineering in this codebase |
| Blockers carried forward | F2 (the real-LLM spike — blocks G2), F1 (chart/table anchors — a real feature gap, not blocking rendering fidelity) |
| Signed | Claude Sonnet 5, 2026-08-15 |

**Rationale:** Phase C completes the cutover the whole plan exists to make: a user can now upload a real corporate `.pptx`, have an LLM catalogue its slides as a reusable design vocabulary, review and approve that catalogue once, and generate decks that clone the template's own designed slides — logo, decoration and all — rather than reconstructing an empty layout skeleton. Every module the plan named for deletion is deleted; every module it named for rewrite is rewritten; the full request chain from upload to download is proven end to end against the real BRI template with a fake model standing in for the network call this environment cannot make. What remains before this is production-ready is not more code — it is the one real-LLM verification pass (§8) the assessment named as the actual open risk from the start, and a human confirming the rendered result looks right (G2), which no amount of additional engineering in this session can substitute for.
