# Phase B Test Report — Deck Planning (LD-5 .. LD-7)

Implements [`PLAN-LLM-DECK-PLANNING.md`](../PLAN-LLM-DECK-PLANNING.md) Phase B, per
[`ASSESSMENT-LLM-DECK-PLANNING.md`](../ASSESSMENT-LLM-DECK-PLANNING.md).

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `B — Deck planning` |
| Date | `2026-08-15` |
| Executed by | Claude Sonnet 5 (local workstation session) |
| Commit range | *(uncommitted — single commit planned at end of session)* |
| Branch | `revamp/phase-1` |
| Environment | `local` — same SQLite/Vitest harness as Phase A. No network egress; `plan_deck_from_catalog` is exercised only via `FakeLlm` and hand-built fakes, never a real model |

---

## 2. Gate summary

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| B1 | `DeckPlan` is a strict, validated contract: ordered `[(design_id, {anchor_id: text})]` plus notes | **PASS** | §4.1, §5 |
| B2 | One LLM call plans the whole deck (no separate content + layout calls) | **PASS** | §4.1 |
| B3 | Every `design_id`/`anchor_id` in a returned plan is real and belongs together; budgets are enforced with a truncation backstop | **PASS** | §4.1, §4.4 |
| B4 | A response with nothing usable is regenerated once, then surfaced — never rendered as an empty deck | **PASS** | §4.1, §4.4 |
| B5 | No previously-passing test regressed | **PASS** | §6 |

**Overall: PASS.**

---

## 3. Task results

| Task | Title | Sev | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `LD-5` | `deck/plan.py` — the `DeckPlan` contract | 🔴 | **DONE** | `tests/unit/test_deck_plan.py` (11) | `backend/src/deck/plan.py` |
| `LD-6` | `LlmClient.plan_deck_from_catalog` | 🔴 | **DONE** | same file | `backend/src/engines/llm.py` |
| `LD-7` | Plan validation + one retry | 🔴 | **DONE** | `test_retries_once_then_surfaces_when_nothing_is_ever_usable`, `test_recovers_on_the_retry_if_the_second_attempt_is_usable` | `backend/src/deck/plan.py::plan_deck` |

**All DONE.** No deviations from the task list itself, but one naming decision is worth stating plainly:

### Deviations

**`LlmClient.plan_deck_from_catalog`, not `LlmClient.plan_deck`.** The plan's LD-6 row literally says "`LlmClient.plan_deck`". The OLD role/budget-based `LlmClient.plan_deck` (RM-6 era) is still what `deck/planner.py` calls, and `deck/planner.py` is still what Phase A's untouched `generation/service.py` calls for every freeform generation today. Renaming the method out from under it would have broken the currently-working pipeline for the rest of this session, with no replacement wired in yet (that's Phase C's `LD-9`). So the new call lives under a distinct name until the cutover, at which point `LD-11` deletes the old `deck/planner.py`/`deck/matcher.py` and the new method is renamed back to `plan_deck`. Same reasoning as Phase A's dual-write decision — recorded there, and consistent here.

**"Capacity respected" needed no separate check.** LD-7 lists three things a plan must be validated against: `design_id` exists, `anchor_id` belongs to that design, and capacity is respected. Working through it (see `deck/plan.py`'s module docstring), capacity turns out to be structurally impossible to violate: `PlanSlide.anchor_texts` is keyed by `anchor_id`, and an anchor_id only exists if the catalogued design has one — there is no "capacity slot" to overflow, only anchors to reference or not. Capacity instead matters as a PROMPTING concern (L6's `(lanjutan)` splitting), which the system prompt states explicitly and `test_a_design_can_be_referenced_by_multiple_slides_for_lanjutan_splitting` confirms the validator has no problem with. Named here so "capacity respected" isn't read as a missing check — it's a check that turned out to already be implied by anchor-membership validation.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Baseline (Phase A) | This phase | Delta |
|---|---|---|---|
| Passed | 330 | 341 | **+11** |
| Failed | 0 | 0 | — |
| Skipped | 0 | 0 | — |
| Coverage (total) | 89% | 88% | −1pt |
| Duration | 17.2s | 16.4s | −0.8s |

**Raw tail of output:**

```
TOTAL                             4803    561    88%
341 passed, 205 warnings in 16.40s
```

**Coverage note:** the dip is `deck/plan.py`'s own new lines that the retry-exhaustion path exercises but coverage tooling counts conservatively across branches, plus `engines/llm.py` growing by one more full method. Every new branch in `deck/plan.py` (drop-unknown-design, drop-unknown-anchor, truncate-over-budget, retry-then-surface, retry-then-recover) has a dedicated test — see §4.4. Total coverage (88%) still clears this repo's 80% rule and the revamp programme's 87% floor.

`ruff check` on `src/` and `tests/`: clean.

### 4.2 Frontend

`N/A — Phase B has no frontend surface.` LD-5/6/7 are backend-only (a planning contract and an LLM call); the plan review UI question is deferred to Phase C's `LD-9`, once there is a real pipeline producing `DeckPlan`s to review. Frontend suite was not re-run for this phase (no frontend files touched); Phase A's run (121/121 passing) stands.

### 4.3 Manual / structural verification

Ran `plan_deck()` against the REAL BRI template's catalog (not a synthetic one) — `bri_catalog` in `test_deck_plan.py` is produced the same way Phase A's `test_deck_catalog.py` proves it, then fed through `plan_deck()` with `FakeLlm`:

```
content: "Ringkasan eksekutif. / Pertumbuhan pendapatan 12% YoY. / Risiko utama."
-> 3 slides planned, all referencing real BRI design_ids and real anchor_ids
-> usage.attempts == 1 (no retry needed on a well-formed fake response)
```

Every slide's `design_id` was checked against `bri_catalog.usable_designs` and every `anchor_id` against that specific design's own anchors — not just "some design in the catalog," which would have let a cross-design anchor id (same shape-id number reused across two different slides) slip through undetected.

### 4.4 Per-task test evidence

| Task | Test | Before | After |
|---|---|---|---|
| `LD-5` | `test_plans_the_real_bri_catalog_end_to_end` | module did not exist | `PASS` — 3 slides, valid `DeckPlan` |
| `LD-7` | `test_validate_slides_drops_unknown_design_id` | n/a | `PASS` — hallucinated `design_id` produces zero slides, not a crash |
| `LD-7` | `test_validate_slides_drops_unknown_anchor_id_but_keeps_known_ones` | n/a | `PASS` — one bad anchor doesn't sink the whole slide |
| `LD-7` | `test_validate_slides_truncates_over_budget_text_and_records_overflow` | n/a | `PASS` — 29-char text over a 10-char budget truncates to ≤10, recorded |
| `LD-7` | `test_retries_once_then_surfaces_when_nothing_is_ever_usable` | n/a | `PASS` — `AlwaysHallucinatingLlm` called exactly 2 times, then `ValidationError` |
| `LD-7` | `test_recovers_on_the_retry_if_the_second_attempt_is_usable` | n/a | `PASS` — first attempt fails validation, second succeeds, plan built from attempt 2 |
| L6 | `test_a_design_can_be_referenced_by_multiple_slides_for_lanjutan_splitting` | n/a | `PASS` — same `design_id` twice, both slides kept |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | Plan against the real BRI catalog with realistic multi-paragraph content | 3 slides, valid ids throughout | Confirmed (§4.3) | `PASS` |
| M2 | Feed a plan response with an unknown `design_id` | that slide dropped, not the whole plan | Confirmed | `PASS` |
| M3 | Feed a plan response entirely unusable, twice in a row | exactly 2 LLM calls, then `ValidationError` raised — not 1, not unbounded | Confirmed | `PASS` |
| M4 | Same, but the SECOND call is usable | plan built from the second attempt, `usage.attempts == 2` | Confirmed | `PASS` |
| M5 | Text far exceeding an anchor's `char_budget` | truncated at a word boundary, `≤ budget` length, overflow recorded | Confirmed | `PASS` |

**Artefacts:** raw pytest output above.

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | `PASS` | 330 → 341, 0 failed |
| Frontend suite | `PASS` (unchanged from Phase A) | no frontend files touched this phase |
| Coverage did not meaningfully decrease | `PASS` (−1pt, explained §4.1) | still ≥ 87% programme floor |
| No new `ruff` errors | `PASS` | |
| No previously working user journey broke | `PASS` | the OLD `deck/planner.py`/`LlmClient.plan_deck` path (still what `generation/service.py` uses) is completely untouched this phase |

---

## 7. Findings discovered during this phase

| # | Finding | Severity | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | Two `plan_deck`-shaped things now exist on `LlmClient` under different names (`plan_deck` and `plan_deck_from_catalog`) | ⚪ | `backend/src/engines/llm.py` | Resolved by design at `LD-11` (old one deleted, new one renamed) |
| F2 | `notes` (LD-5's free-text field) is threaded all the way through but has no consumer yet — nothing renders or logs it downstream | 🟡 | `backend/src/deck/plan.py::DeckPlan.notes` | `LD-9`: decide whether it surfaces in the admin/generation UI or stays operator-log-only |

---

## 8. Facts vs. assumptions

| Claim in this report | Basis |
|---|---|
| `plan_deck()` never lets an invalid `design_id`/`anchor_id` reach a `DeckPlan` | `verified by test` (§4.4) |
| The retry is bounded at exactly one extra attempt | `verified by test` (`AlwaysHallucinatingLlm.call_count == 2`) |
| Real Kimi K3 output would validate cleanly against this contract | **not verified** — same open item as Phase A §8; every test here runs against fakes |
| The prompt in `_build_catalog_plan_messages` is comprehensible/followable by a real model | **not verified by execution** — written to the same standard as the rest of the pipeline's prompts, but only a real run (assessment §4's "LD-2 is the spike") settles this |

**Anything not verifiable in this phase and why:** same as Phase A — no network egress in this environment, and Kimi K3 is past this assistant's knowledge cutoff, so its actual JSON-following behavior on this specific prompt is unverified. This is the same open item the assessment names in §7 and defers to deploy-time verification (`LD-10`).

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | `PASS` |
| Next phase authorised | `YES` |
| Blockers carried forward | The real-LLM spike (still unresolved, carried from Phase A); F2 (notes has no consumer yet, non-blocking) |
| Signed | Claude Sonnet 5, 2026-08-15 |

**Rationale:** Phase B delivers a planning call that turns a template's catalog plus source content into a fully-validated `DeckPlan` in one LLM round trip, with a retry that's bounded and a validator that structurally cannot let a broken reference (nonexistent design, nonexistent anchor, over-budget text) reach a caller. Nothing user-facing changed — this phase's output only becomes visible to a user once Phase C's renderer and generation-service wiring exist. What a developer can now do that they could not before: hand `plan_deck()` a real template's catalog and get back a plan `deck/renderer.py` (Phase C) can mechanically execute, with every reference in it guaranteed resolvable.
