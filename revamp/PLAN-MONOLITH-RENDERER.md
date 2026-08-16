# Plan — In-process deck renderer, and the removal of Presenton

Implements the recommendation in
[`ASSESSMENT-ARCHITECTURE-2026-08-15.md`](./ASSESSMENT-ARCHITECTURE-2026-08-15.md):
bring slide rendering in-process with `python-pptx`, delete the Presenton service, and
collapse the two generation paths into one.

**Written:** 2026-08-15 · **Revised:** 2026-08-15 (layout-plan review step, model routing) ·
**Branch base:** `revamp/phase-1` (`9814ee9`)

Cost and model decisions live in
[`COST-AND-MODEL-STRATEGY.md`](./COST-AND-MODEL-STRATEGY.md).

> **This supersedes the locked architecture decision in [`README.md`](./README.md).**
> That decision — *"Presenton is hosted on the same origin under `/editor`"* — was the
> correct answer to the question *"how do we host two Next.js apps on one origin?"*. This
> plan removes the question. `README.md` §"Architecture decision" must be rewritten by
> `RM-16`, not left to contradict this file.

---

## 1. Locked decisions

Confirmed by the user, 2026-08-15. These are inputs, not proposals.

| # | Decision | Consequence |
|---|---|---|
| **D1** | **No browser WYSIWYG editor.** Generate → download `.pptx` → edit in PowerPoint | `/editor`, `basePath`, the Traefik allowlist, `editor_url`, `SlideEditorModal` and `studio_opened_at` all go. Closes `TD-05`, `TD-06`, `TD-24` by deletion |
| **D2** | **Exact fidelity.** The output deck is built from the uploaded `.pptx`'s real slide masters and layouts | The LLM produces content only, never layout or style. Rendering becomes deterministic and golden-file testable |
| **D3** | **Charts and tables from data**, not AI or stock photography | `python-pptx` native charts. No image provider, no Pexels key, no image budget |
| **D4** | **Single tenant, one VPS** | Postgres tenant scoping stays (it is sound and free). No new multi-tenant work. `TD-23` stays backlog |
| **D5** | **A layout plan is produced and reviewable before rendering** | New pipeline stage, new statuses, new review UI. §2.3 |
| **D6** | **Per-task model routing, cheapest-credible by default** | One global model is what let the deck engine silently follow the chat model. `COST-AND-MODEL-STRATEGY` §6 |

### 1.1 Still open — answer before the task that needs it

| # | Question | Needed by | Default if unanswered |
|---|---|---|---|
| **Q1** | Is **PDF export** required? PDF needs LibreOffice headless in the worker image (~400MB) | `RM-14` | Assume **PPTX only**; `RM-14` skipped, `pdf` removed from `export_as` |
| **Q2** | Keep the **governed path** (profile → outline → consistency), or delete it? It cannot run on the lite stack today — `seed_lite.py` seeds no approved `StakeholderProfile` | `RM-11` | Assume **keep the model, one service** — unify the code path without deleting governance |
| **Q3** | Should layout review be **mandatory** or **auto-approve when confident**? | `RM-9` | Assume **auto-approve when no slide is low-confidence**, with review always reachable. §2.3 |

---

## 2. Target architecture

### 2.1 Services: 11 → 10

```
traefik · frontend · orchestrator · worker · init · postgres · redis · minio
surrealdb · open-notebook
                                                    ✗ presenton   (removed)
```

Traefik's config collapses to two routers — frontend and orchestrator — with no allowlist,
no priority arbitration, and no `/_next` collision. The route-collision contract test
becomes trivially satisfiable instead of guarding a rule that cannot be made correct.

### 2.2 The generation pipeline

```
content (sources | chat | guide | custom markdown)
    │
    ▼
outline                    OutlineContent — exists today (outline/schema.py)
    │
    ▼  ── LLM call 1 ── deck/planner.py
DeckSpec                   Content only: titles, bullets, chart series, notes.
    │                      No layout. No colour. No font. Enforced by the type.
    │
    ▼  ── deterministic scoring + LLM call 2 (tie-break only) ── deck/matcher.py
LayoutPlan                 Per slide: chosen layout, reason, confidence, alternatives[]
    │
    ▼  ══ D5: USER REVIEW ══  ← auto-approved when every slide is high-confidence
    │
    ▼  ── no LLM ── deck/renderer.py
deck.pptx                  Pure function. (DeckSpec, LayoutPlan, template bytes) → bytes
    │
    ▼
MinIO → GET /generations/{id}/artifact
```

**Why the split matters beyond UX.** Content generation and layout selection are different
reasoning tasks with different quality bars and different costs. Fusing them, as today's
`slides_markdown` blob does, means you cannot inspect, override, test or price either one
separately. Separating them gives a reviewable artifact, a cheap second call, and — for the
first time in this codebase — **honest progress reporting**, because there are now real
observable stages between "queued" and "done" (`ASSESSMENT-DECK-GENERATION-REVAMP` §3
called this impossible while Presenton owned the opaque middle; in-process, it is not).

### 2.3 The layout plan and its review — D5

**Matching is deterministic first, LLM second.** For each slide, score every catalogued
layout:

```
score(slide, layout) =
    role_match         hard filter — a chart slide needs a layout with a large
                       content/picture placeholder; without one the layout is excluded
  + capacity_fit       do the bullets fit the placeholder character budgets? penalise overflow
  + placeholder_waste  penalise layouts leaving many placeholders unfilled
  + variety            penalise the same layout used many times consecutively
  + position_hint      slide 1 → title role; section breaks → section role
```

Every component contributes to a **reason string**, so each choice is explainable without
an LLM having to explain itself.

| Top-2 gap | Confidence | Action |
|---|---|---|
| Clear winner | `high` | Deterministic. **No LLM call.** |
| Within threshold | `medium` | LLM call 2 tie-breaks the shortlist (2–3 candidates only) |
| No layout scores above the floor | `low` | Best-effort + a warning naming what the template lacks |

**Review behaviour (Q3 default):** if no slide is `low`, the plan auto-approves and
rendering proceeds — a user regenerating ten times is not forced through ten review
screens. If any slide is `low`, the generation parks at `awaiting_review` and the user is
shown what is wrong. Review is always reachable on demand via a "review layout plan"
toggle on the generate action.

This is a **cost control as much as a UX feature** — catching "slide 7 has no home in this
template" in a review screen is free; discovering it after a full regenerate is not
(`COST-AND-MODEL-STRATEGY` §4.5).

### 2.4 Generation statuses — real ones, at last

`GenerationStatus.analyzing` and `.building_outline` are declared, mirrored in the frontend
type, and **never assigned anywhere in `src/`**. Rather than deleting them as originally
planned, the pipeline now has real stages to bind:

```
queued → planning → matching → awaiting_review → rendering → ready
                                     │                          └→ failed
                                     └─ skipped when auto-approved
```

Each is written by a step that genuinely just finished. No timers, no fabricated progress —
the standing rule in `revamp/README.md` rule 5 and `ARCHITECTURE.md` §8.

### 2.5 New module

```
backend/src/deck/
├── inspect.py          # .pptx bytes → LayoutCatalog (roles, placeholders, geometry, budgets)
├── roles.py            # layout classification + the role vocabulary
├── spec.py             # DeckSpec / SlideSpec pydantic contract
├── planner.py          # content + catalog → DeckSpec           (LLM call 1)
├── matcher.py          # DeckSpec + catalog → LayoutPlan        (scoring + LLM call 2)
├── renderer.py         # DeckSpec + LayoutPlan + template → bytes  (pure, no LLM)
├── charts.py           # ChartSpec → python-pptx native chart
├── preview.py          # LayoutCatalog → SVG wireframes
└── export.py           # pptx → pdf via LibreOffice             (RM-14 only, gated on Q1)
```

---

## 3. Tasks

Severity: 🔴 blocks everything · 🟠 blocks the phase · 🟡 improvement · 🟢 tidy-up

### Phase A — evidence and foundations

---

#### RM-0 — Baseline, backup, and stop the stack falling over 🔴

*Depends: nothing.*

1. **Fix the restart policies** — the 2026-08-15 outage. `traefik`, `frontend`,
   `orchestrator` and `worker` have **no `restart:` policy**, so Docker defaults them to
   `no`. The data tier (`postgres`, `redis`, `minio`, `surrealdb`, `open-notebook`,
   `presenton`) all declare `restart: always` and came back; the app tier did not, and
   Traefik being down is the 502. Add `restart: unless-stopped` to those four across
   `docker-compose.lite.yml`, `.yml` and `.local.yml`.
2. **Back up `presenton_data` and Postgres off-host.** `TD-03` is still `PARTIAL` —
   archives exist *on the host they exist to survive*. Run the `scp`. Do this before any
   deletion task.
3. Dump `template` rows with `registration_error`; capture orchestrator + worker logs from
   one failing upload and one failing generation. Save verbatim to
   `revamp/reports/RM-0-BASELINE.md`.

**Gate:** a reboot brings the whole stack back unattended; backups verified off-host; the
current failure mode recorded as observed fact, not inference.

> If the observed errors are **not** on the Presenton seam, stop and say so. The plan
> assumes the assessment; the assessment assumes the seam. Contradicting evidence
> outranks both.

---

#### RM-1 — Spike: what do the real BRI templates contain? 🔴

*Depends: RM-0. The plan's load-bearing unknown (`ASSESSMENT` §5.4, U1).*

Throwaway script — **not** committed to `src/` — over the two real `.pptx` files from
MinIO. For every master and layout: name, placeholder count, each placeholder's `idx` /
type / position / size, and whether the layout is static shapes only.

| Finding | Consequence |
|---|---|
| ≥ 4 layouts with real title + body placeholders | Proceed as written |
| 1–3 usable layouts | Proceed, but `RM-15` (house template) becomes **required** |
| No placeholders — all static text boxes | **Stop and re-plan.** §7 |

**Gate:** inventory recorded in the baseline report; the branch chosen explicitly, in
writing.

---

#### RM-2 — `deck/inspect.py` + `deck/roles.py` 🔴

*Depends: RM-1.*

- `inspect_template(pptx_bytes) -> LayoutCatalog`, iterating
  **`prs.slide_masters[*].slide_layouts`** — not `prs.slide_layouts`, which sees only the
  first master. Corporate templates commonly ship several.
- Classify each layout by placeholder composition into a role: `title`, `section`,
  `bullets`, `two_content`, `content_with_visual`, `blank`, `unusable`. Deterministic,
  unit-tested against committed fixtures.
- Per placeholder: `idx`, type, EMU geometry, and a derived **character budget** from
  geometry and the layout's font size. This is the input to both the overflow mitigation
  and the matcher's `capacity_fit` — build it now, not later.
- `InspectionReport`: roles covered, roles missing, and a human-readable reason per
  unusable layout.

**Gate:** both BRI templates inspect without raising; catalogue asserted against fixtures;
a zero-usable-layout template reports *why*, not a boolean.

---

#### RM-3 — Template model migration 🟠

*Depends: RM-2.*

- Migration (id ≤ 32 chars — `ARCHITECTURE.md` §8): drop `presenton_template_ref` and
  `slide_image_urls`; add `layout_catalog` and `inspection_report` (JSON).
- Replace `RegistrationStatus` with `TemplateStatus`: `ready` / `rejected` / `no_source`.
  `pending` disappears — inspection is synchronous and sub-second.
- Delete `registry/registration.py`, `JobType.register_template`, `run_register_template`,
  and the `template_registration_poll_*` settings. That machinery existed to survive a
  multi-minute engine call that no longer happens.
- `TemplateService.create` inspects inline. `reregister` → `reinspect`, still useful as
  inspection improves.
- **Backfill:** re-inspect stored `.pptx` files where present; rows without one become
  `no_source`. Do not repeat `TD-15` — never backfill a row to a health it has not earned.

**Gate:** `POST /templates` returns a terminal state in one round trip; both BRI rows land
`ready` with a populated catalogue; no `pending` anywhere.

---

#### RM-4 — `deck/preview.py` — SVG wireframes 🟡

*Depends: RM-2.*

Each layout drawn as an SVG wireframe from placeholder geometry: true aspect ratio, each
placeholder a labelled rectangle at its real position. No LibreOffice, no engine round
trip, no `slide_image_urls`.

A schematic, not a screenshot — and honest about being one, which the current permanently
empty thumbnail is not (`TD-32`). **Feeds the RM-10 review UI**, so it is now on the
critical path rather than cosmetic.

**Gate:** the templates page renders one wireframe per layout for both BRI templates.

---

### Phase B — the pipeline

---

#### RM-5 — `deck/spec.py` — the content contract 🔴

*Depends: RM-2.*

`DeckSpec` / `SlideSpec` in pydantic, following `outline/schema.py`'s style. A `SlideSpec`
carries `role`, `title`, `bullets[]`, optional `chart`, optional `table`, optional `notes`.

**No layout field. No colour field. No font field.** D2 enforced by the type, not by a
convention someone has to remember.

**Gate:** the schema round-trips; a spec carrying styling information is a type error.

---

#### RM-6 — `deck/planner.py` — content generation (LLM call 1) 🔴

*Depends: RM-5.*

- `plan_deck(content, catalog, ...) -> DeckSpec` on `LlmClient`, following the exact shape
  of `talking_points` and `draft_outline` (`llm.py:122`, `:151`) —
  `response_format={"type":"json_object"}`, then coerce and validate.
- The prompt is told **only the roles this template offers** and the **character budget per
  field**. The model cannot request a layout that does not exist, and is steered away from
  overflow at the source.
- **Feed the outline, not raw sources** — `COST-AND-MODEL-STRATEGY` §4.1, the single
  largest cost lever (up to 10× on input). Architectural, not a tuning knob.
- **Order the prompt cache-friendly**: stable prefix (system + schema + catalogue) first,
  variable content last (§4.3). Free now, expensive to retrofit.
- **One call per deck**, not per slide (§4.2).
- Deterministic backstop: over-budget text truncated at a word boundary, the overflow
  **recorded on the generation**, never silently dropped.

**Gate:** malformed responses raise a clear `ValidationError` rather than producing a
half-deck; budget enforcement unit-tested; the planner never emits a role absent from the
catalogue; retries capped at 2 and the resolved model id logged on every call.

---

#### RM-7 — `deck/matcher.py` — the layout plan 🔴 *(D5)*

*Depends: RM-6.*

- Deterministic scoring per §2.3, producing a `LayoutPlan`: per slide the chosen layout, a
  **reason string built from the score components**, a confidence, and the ranked
  alternatives.
- LLM call 2 **only** when the top two are within threshold, and only over the 2–3 shortlisted
  candidates — a few hundred tokens, on the cheapest reliable JSON model
  (`COST-AND-MODEL-STRATEGY` §6).
- **Graceful degradation:** if the LLM is unavailable or returns junk, fall back to the top
  deterministic match and mark the slide `medium`. A tie-break failure must never fail a
  generation.
- `low` confidence carries a message naming what the template lacks
  ("no layout with a content area large enough for a chart").

**Gate:** matching is deterministic and unit-tested with no LLM in the loop; the LLM path
is exercised by a fake; every slide has a non-empty reason string; an LLM outage still
produces a complete plan.

---

#### RM-8 — `deck/renderer.py` + `deck/charts.py` 🔴

*Depends: RM-3, RM-7.*

- `render_deck(spec, plan, template_pptx) -> bytes`. Open the template, **strip its example
  slides** (remove from `sldIdLst`, drop the relationships), then `add_slide` per
  `SlideSpec` using the layout the `LayoutPlan` assigned.
- Fill placeholders by `idx` from the catalogue. **Never set fonts or colours explicitly** —
  that is what makes the theme apply and D2 hold. Comment it in the code, and add a test
  that fails if someone adds a `font.name` later.
- Charts via `add_chart` — real editable PowerPoint charts, per D3. Tables via `add_table`.
  Both placed into the assigned layout's placeholder geometry.
- Speaker notes to the notes slide.
- **Pure function**: no network, no LLM, no object store. Everything injected.

**Gate:** golden-file test — a fixed `DeckSpec` + `LayoutPlan` + fixture template produces
a deck whose `inspect_pptx()` facts (`generation/artifact.py`) match an asserted
expectation. Rendering the same inputs twice produces byte-comparable output. **A deck from
a real BRI template opens in PowerPoint with brand fonts, logo and colours intact —
verified by a human opening the file.**

---

### Phase C — integration and cutover

---

#### RM-9 — Plan persistence, statuses, and the review API 🟠 *(D5, Q3)*

*Depends: RM-7.*

- Persist `DeckSpec` and `LayoutPlan` on the `Generation` row (JSON). No new table — the
  plan is bound to exactly one generation and dies with it, unlike `Outline` which is
  reusable.
- Implement the status machine in §2.4. Bind `analyzing`/`building_outline` to real stages
  or rename them — either way, no status is ever declared and unassigned again.
- `GET /generations/{id}/plan` returns the plan with reasons and alternatives.
  `PATCH /generations/{id}/plan` accepts per-slide layout overrides, validated against the
  catalogue, then resumes rendering.
- Auto-approve per Q3: no `low` slides → proceed without parking. Any `low` → park at
  `awaiting_review`.
- **Add `job_id` to `GenerationResponse`** — `ASSESSMENT-DECK-GENERATION-REVAMP` §3.3
  records that the client cannot reach the job at all today. One field, and the progress
  panel becomes possible.

**Gate:** a generation with a `low`-confidence slide parks and waits; an override renders
the overridden layout; an override naming a layout absent from the catalogue is rejected;
auto-approve does not park.

---

#### RM-10 — Layout review UI 🟠 *(D5)*

*Depends: RM-4, RM-9.*

Per slide: the SVG wireframe of the chosen layout, the slide's title and bullets, the
reason string, the confidence, and a dropdown of alternatives. `low`-confidence slides
surfaced first with their warning. Approve-all, or override then approve.

Reachable on demand even when auto-approved, so a user can inspect a plan they were not
forced to review.

**Gate:** a `low`-confidence plan is reviewable and overridable end-to-end in a browser;
tests cover the auto-approve and parked paths; both locales carry the new strings.

---

#### RM-11 — Wire the worker; collapse the two generation paths 🟠

*Depends: RM-8, RM-9.*

- In `generation/worker.py`, replace `presenton.generate(...)` + `presenton.download(...)`
  (`:58`, `:61`) with `plan_deck` → `match_layouts` → (review gate) → `render_deck` →
  `object_store.put_bytes`. Idempotency, resumability and the consistency gate stay.
- Retire `presenton_presentation_id` as the resumability key; use `pptx_uri` presence.
- **One generation service.** Per Q2's default, `GenerationService` and
  `FreeformGenerationService` merge behind one entry point: governed = a profile is pinned
  and the consistency gate runs; freeform = no profile. `ARCHITECTURE.md` §3 names the
  divergence between these two as this codebase's recurring failure mode — this is the
  moment it stops being two implementations.
- Delete `generation/mapper.py` and `generation/freeform_mapper.py`; their job no longer
  exists. `slides_markdown_from_outline` is replaced by outline → `DeckSpec`.
- `preflight.py` (quota, metering) is called once, in the merged path, by construction.

**Gate:** both governed and freeform generations produce a downloadable deck through one
code path; quota/metering integration tests pass unchanged; nothing under `generation/`
imports `engines/presenton`.

---

#### RM-12 — Model routing and the eval 🟠 *(D6)*

*Depends: RM-6, RM-7.*

- Extend `TenantLlmConfigService` with optional **per-task model overrides**, defaulting to
  the tenant model when unset (`COST-AND-MODEL-STRATEGY` §6). Pin the OpenRouter provider
  where it matters — one model id served by several providers with different quantisation
  and JSON-mode support is invisible quality drift.
- **Log the resolved model id and token counts on every call.** You cannot cost-attribute
  what you do not record.
- Run the eval in `COST-AND-MODEL-STRATEGY` §7: 5 committed fixture documents × 3 candidate
  models, scored on JSON validity, budget compliance, **human-rated Indonesian fluency**,
  role validity, cost and latency. Under $1 total. Report to
  `revamp/reports/RM-12-MODEL-EVAL.md`.

**Gate:** per-task routing works and is tested; the eval report exists with a chosen model
and the evidence for it. **The fluency rating is not skippable** — it is the one metric
that cannot be automated and the one users will actually judge.

---

#### RM-13 — Delete Presenton 🟠

*Depends: RM-11. RM-0's off-host backup confirmed first.*

| Layer | Items |
|---|---|
| Compose | the `presenton` service, `presenton_data` volume, the 17-way Traefik allowlist and `presenton-auth` middleware (`docker-compose.lite.yml:218-269`), across all three compose files |
| Env | `PRESENTON_URL`, `PRESENTON_AUTH_*`, `PRESENTON_BASIC_AUTH_B64`, `PRESENTON_MODEL`, `PRESENTON_EXPOSED_PORT`, `PRESENTON_CAN_CHANGE_KEYS`, `IMAGE_PROVIDER`, `PEXELS_API_KEY` |
| Backend | `engines/presenton.py`, its `deps.py` wiring, its health check, `config.py:104-106` and `:123-124` |
| API | `editor_url` / `_editor_url` (`api/generations.py:70-84`), `studio_opened_at` and the DG-4 artifact cutover, `preview_url` on templates |
| Frontend | `SlideEditorModal.tsx` (+ test), the editor button in `StudioPanel.tsx`, `editorUrl` in `services/api.ts`, related i18n keys in `en.ts` / `id.ts` |
| Tests | `test_presenton_mapping.py`, `test_presenton_template_registration.py`, `test_editor_url.py`, `test_template_preview_url.py`, `test_studio_opened_cutover.py`, `test_template_thumbnails.py`, the `FakePresenton` fake |
| Docs | `ARCHITECTURE.md` §2 and §5's editor rows; `README.md`'s locked decision |

**Gate:** `grep -ri presenton backend/src frontend/src deploy` returns **nothing**;
`docker compose build` succeeds for **all** services, closing `TD-04`; the stack starts
with 10 services; a full generation round trip passes on the VPS.

---

### Phase D — optional and closing

---

#### RM-14 — PDF export via LibreOffice 🟡 *(gated on Q1)*

*Depends: RM-11. Skip entirely if PPTX-only.*

`soffice --headless --convert-to pdf` in the worker image, from `deck/export.py`, with a
timeout and a temp dir per call. ~400MB image growth, which is why it is optional. If
skipped, **remove `pdf` from `export_as`** rather than leaving an option that fails.

**Gate:** a generated PDF opens and matches the PPTX — or `export_as` honestly offers only
`pptx`.

---

#### RM-15 — Ship a house template 🟡 *(required if RM-1 found < 4 usable layouts)*

*Depends: RM-2.*

An 8–10 layout `.pptx` committed to the repo and seeded by `seed_lite.py`: a fresh install
can generate a decent deck before anyone uploads anything, `RM-8`'s golden tests get a
stable committed fixture, and the "decks look uniform" tradeoff (`ASSESSMENT` §6) is
mitigated.

**Gate:** a clean `docker compose up` on an empty database generates a deck with no manual
template upload.

---

#### RM-16 — Reconcile the documentation 🟢

*Depends: RM-13.*

`ARCHITECTURE.md` §2/§5/§7 rewritten. `README.md`'s locked decision replaced **as a
superseded-with-reason note, not a deletion** — the `/editor` reasoning was correct, and
the record of why it stopped mattering is worth more than a clean file. `TECH-DEBT.md`
reconciled per its own §5: `TD-01`, `TD-02`, `TD-04`, `TD-05`, `TD-06`, `TD-07`, `TD-08`,
`TD-09`, `TD-24`, `TD-25`, `TD-26`, `TD-32` move to §6 Closed, each annotated **"closed by
removal"** — resolved by deleting the boundary, not by fixing the defect, and that
distinction matters to whoever reads this next.

Report to `revamp/reports/RM-REPORT.md` per `TEST-REPORT-TEMPLATE.md`.

---

## 4. Order

```
RM-0 ──► RM-1 ──► RM-2 ──┬──► RM-3 ─────────────┐
 (baseline) (spike)      │                      │
                         ├──► RM-4 ────────┐    │
                         │                 │    │
                         └──► RM-5 ──► RM-6 ──► RM-7 ──► RM-8 ──┐
                                             │        │         │
                                             │        └──► RM-9 ──► RM-10 ──┐
                                             │                              │
                                             └──► RM-12                     │
                                                                            ▼
                                                            RM-11 ──► RM-13 ──► RM-16
                                                                        │
                                                                        ├──► RM-14 (Q1)
                                                                        └──► RM-15 (cond.)
```

**Critical path:** `RM-0 → RM-1 → RM-2 → RM-3 → RM-5 → RM-6 → RM-7 → RM-8 → RM-11 → RM-13`
— *"my BRI template produces a BRI-looking deck."*

`RM-4`, `RM-9`, `RM-10` are the review feature (D5) and can land after a first
render works end-to-end. `RM-12`, `RM-14`, `RM-15` are parallel or optional.

**Do not start `RM-2` before `RM-1` reports.** The spike exists to kill the plan cheaply.

### 4.1 Revised effort

| Phase | Content | Estimate |
|---|---|---|
| A | RM-0…RM-4 — baseline, spike, inspection, migration, previews | 1.5–2 sessions |
| B | RM-5…RM-8 — spec, planner, matcher, renderer | 3–4 sessions |
| C | RM-9…RM-13 — review, worker, routing, deletion | 2.5–3.5 sessions |
| D | RM-14…RM-16 — optional + docs | 1–2 sessions |

The layout-plan review (D5) adds roughly **1–1.5 sessions** over the original plan. It buys
a reviewable artifact, honest progress reporting, a cheaper second model call, and a
regeneration-loop cost control.

---

## 5. Exit gate

| # | Criterion |
|---|---|
| G1 | A real BRI `.pptx` uploads, inspects and reports its layouts in under a second |
| G2 | A generated deck opens in PowerPoint with the template's fonts, logo, colours and layouts intact — **confirmed by a human opening the file** |
| G3 | The same `DeckSpec` + `LayoutPlan` + template renders byte-comparable output twice |
| G4 | Every slide's layout choice carries a human-readable reason; a `low`-confidence plan is reviewable and overridable in a browser |
| G5 | `grep -ri presenton backend/src frontend/src deploy` returns nothing |
| G6 | `docker compose build` succeeds for every service (`TD-04` closed); a host reboot restores the full stack unattended (RM-0) |
| G7 | Backend and frontend suites green; `ruff` clean; typecheck clean; coverage not below current |
| G8 | One generation code path — quota and metering cannot be bypassed by construction, not by review |
| G9 | Text overflow is detected and recorded on the generation, never silently shipped |
| G10 | `RM-12-MODEL-EVAL.md` exists with a chosen model and the evidence, including the human fluency rating |

G2, G4, G9 and G10's fluency rating **cannot be closed by automated tests.** They need a
human with PowerPoint open. `TD-10` and `TD-11` have been waiting on exactly that for two
phases — do not let this report carry the same debt forward again.

---

## 6. What this plan does not touch

- **Open Notebook / SurrealDB.** Same shape of problem (`ASSESSMENT` §7), deliberately not
  bundled. One boundary at a time.
- **Chat, guide, sources, ingestion.** Untouched.
- **Auth, RBAC, tenancy, metering.** Untouched — D4 keeps them as-is.
- **`TD-27`** (Docling vanishing on `--force-recreate`) — 🔴 and unrelated. Fix it in the
  same deploy window as `RM-13` since both touch compose, but it is not part of this plan.

---

## 7. Contingency — if `RM-1` finds no placeholders

If the BRI templates draw everything as static shapes with no placeholders, `python-pptx`
has little to fill and D2 cannot be reached by placeholder filling. Three options, in
preference order:

1. **Rebuild the templates properly.** A `.pptx` with real layouts is a one-off design
   task, produces a permanently better asset, and everything downstream works as written.
   Usually the right answer.
2. **Absolute positioning.** Render text boxes at coordinates copied from a reference
   slide. Visually close, brittle against template changes, and it forfeits the theme
   inheritance that makes fonts and colours free.
3. **Reconsider.** If neither is acceptable, the assessment's premise does not hold for
   your templates, and the Presenton decision should be revisited on the new evidence
   rather than argued from this document.

Choose in writing, in the `RM-0` baseline report. Do not discover it mid-`RM-8`.
