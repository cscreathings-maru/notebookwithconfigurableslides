# Plan — LLM-planned, deterministically-rendered decks

Implements [`ASSESSMENT-LLM-DECK-PLANNING.md`](./ASSESSMENT-LLM-DECK-PLANNING.md).

**Written:** 2026-08-15 · **Branch base:** `revamp/phase-1`

> **Supersedes [`PLAN-SLIDE-CLONING.md`](./PLAN-SLIDE-CLONING.md)**, which was
> correct about *cloning designed slides* and wrong about *how to understand
> them*. Its `SC-2` (geometric capacity detection) is withdrawn — see the
> assessment §3.
>
> **Two of its tasks are already done and carry over unchanged:**
> `SC-0` (`deck/clone.py`, image-safe cloning — proven against the real
> template) and `SC-7` (the full 30-slide house template, restored).

---

## 1. Locked decisions

| # | Decision | Consequence |
|---|---|---|
| **L1** | Render by **cloning designed slides**, never by building from layouts | `deck/clone.py` is the rendering primitive |
| **L2** | An **LLM catalogues a template's designs once, at upload** | No geometric inference. `SC-2` withdrawn |
| **L3** | The catalog is **reviewed by an admin before use** | The review gate moves from per-deck to per-template |
| **L4** | **One LLM call plans the whole deck** — order, design per section, text per anchor | Replaces the separate planner + matcher |
| **L5** | **Rendering is deterministic, zero LLM** | Reproducible, testable, cannot produce an invalid file |
| **L6** | Content exceeding a design's capacity **splits across repeats**, continuation titles suffixed `(lanjutan)` | No content is ever dropped |
| **L7** | A design may be reused **any number of times** in one deck | Image-safe cloning is mandatory (done) |
| **L8** | The model is **configuration, verified at deploy** — Kimi K3 via OpenRouter | Never hard-coded; per-task routing already exists |

---

## 2. Target architecture

```
┌─ ONBOARDING (once per template, LLM, best model) ──────────────┐
│  upload .pptx                                                   │
│    → dump each slide's shapes as structured text                │
│    → LLM: shapes → DesignCatalog                                │
│         · role        (cover/divider/cards/timeline/…)          │
│         · capacity    (how many item groups it holds)           │
│         · anchors     (shape_id → what belongs there)           │
│    → ADMIN REVIEWS AND CORRECTS  ← L3                           │
│    → stored as Template.slide_catalog                           │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─ PLANNING (once per generation, LLM) ──────────────────────────┐
│  catalog (compact) + resolved content                           │
│    → LLM: one call → DeckPlan                                   │
│         ordered [ (design_id, {anchor_id: text}) ]              │
│    → validated against the catalog (real ids, capacity honoured)│
└─────────────────────────────────────────────────────────────────┘
                              │
┌─ RENDER (deterministic, no LLM) ───────────────────────────────┐
│  clone chosen slides in order → replace anchor text →           │
│  drop unused slides → bytes                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 Anchors — the key data structure

Cloning a designed slide means writing text into shapes that already exist.
Those shapes are not all placeholders: a designed slide mixes real placeholders
(addressable by `idx`) with plain text boxes (addressable by shape id).

So each catalogued design records its **anchors**:

```
anchor_id     the shape's id, stable within that slide
current_text  the placeholder text as designed ("Point 1", "Lorem ipsum…")
purpose       what belongs here, labelled by the LLM:
              title | subtitle | body | item_1_title | item_1_body | …
char_budget   derived from the shape's geometry (existing logic reused)
```

**Capacity falls out of this for free**: it is the number of distinct
`item_N_*` groups. No geometric grouping needed — which is exactly the
withdrawn `SC-2`.

### 2.2 Module disposition

| Module | Fate |
|---|---|
| `deck/clone.py` | **keep** — shipped, proven |
| `deck/charts.py` | **keep** |
| `deck/inspect.py` | **replace** → `deck/dump.py` (serialise slides for the LLM) |
| `deck/roles.py` | **shrink** — the role vocabulary survives as the LLM's label set; `classify_layout` goes |
| `deck/spec.py` | **rewrite** — content is per-anchor, not role + bullets |
| `deck/planner.py` | **merge** into the single planning call |
| `deck/matcher.py` | **delete** — the LLM does the matching (L4) |
| `deck/renderer.py` | **rewrite** — clone/replace, not `add_slide` |
| `deck/preview.py` | **adapt** — wireframe a slide, not a layout |
| `deck/from_outline.py` | **keep the idea** — an outline still bypasses content invention; its output shape changes |

---

## 3. Tasks

Severity: 🔴 blocks everything · 🟠 blocks the phase · 🟡 improvement

### Phase A — template understanding

| # | Task | Sev |
|---|---|---|
| **LD-1** | `deck/dump.py` — serialise one slide's shapes into compact structured text for the LLM: shape id, type, position, size, current text, group nesting. Compact matters: ~15k tokens for 30 slides is the whole budget | 🔴 |
| **LD-2** | `LlmClient.catalog_template` — dump → `DesignCatalog` (role, capacity, anchors). Strict JSON. **Per-slide chunking** if the model's context cannot take the whole deck (assessment §7) | 🔴 |
| **LD-3** | Persist `Template.slide_catalog` + migration; `TemplateService.create` runs cataloguing. **No longer synchronous** — an LLM call belongs in a job, so template creation returns `cataloguing` and an Arq job drives it terminal | 🔴 |
| **LD-4** | Catalog review UI — admin sees each design's wireframe, the LLM's label, capacity and anchors, and can correct them before the template is usable (L3) | 🟠 |

> **LD-3 reverses RM-3's synchronous inspection.** That was right when
> inspection was a local file parse; it is wrong now that it is a network LLM
> call. The `pending` state removed in RM-3 returns — earned this time.

### Phase B — deck planning

| # | Task | Sev |
|---|---|---|
| **LD-5** | `deck/plan.py` — the `DeckPlan` contract: ordered `[(design_id, {anchor_id: text})]`, plus `notes`. Pydantic, strict | 🔴 |
| **LD-6** | `LlmClient.plan_deck` — catalog + content → `DeckPlan`, one call. Prompt carries each design's capacity and each anchor's budget, and the `(lanjutan)` rule (L6) | 🔴 |
| **LD-7** | Plan validation — every `design_id` exists, every `anchor_id` belongs to that design, capacity respected, budgets enforced with the existing truncation backstop. A plan that fails validation is **regenerated once**, then surfaced | 🔴 |

### Phase C — rendering and wiring

| # | Task | Sev |
|---|---|---|
| **LD-8** | `deck/renderer.py` — clone designs in plan order (`deck/clone.py`), write anchor text, drop unused slides. Pure function, no LLM, no network | 🔴 |
| **LD-9** | Wire into `generation/service.py` + worker; delete `matcher.py`; adapt the existing review gate to plan-level review | 🟠 |
| **LD-10** | Model config: `DECK_CATALOG_MODEL` / `DECK_PLAN_MODEL`, defaulting to the tenant model. **Verify Kimi K3 exists and does strict JSON before rollout** (assessment §7) | 🟠 |
| **LD-11** | Delete the superseded modules and their tests; reconcile `TECH-DEBT.md` and `ARCHITECTURE.md` | 🟢 |

---

## 4. Order

```
LD-1 ──► LD-2 ──► LD-3 ──┬──► LD-4
                          │
                          └──► LD-5 ──► LD-6 ──► LD-7 ──► LD-8 ──► LD-9 ──► LD-11
                                                                      │
                                                                   LD-10
```

Critical path: `LD-1 → LD-2 → LD-3 → LD-5 → LD-6 → LD-7 → LD-8 → LD-9`.

**LD-2 is the spike.** Before building anything downstream, run the real BRI
dump through the real model once and read the catalog it produces. If it cannot
tell a 3-card design from a timeline, this plan changes shape — and that is
cheap to discover ($0.02) and expensive to assume.

**Estimate: 2–3 sessions**, down from 3–4, because the withdrawn `SC-2` was the
largest and least certain piece.

---

## 5. Exit gate

| # | Criterion |
|---|---|
| G1 | A rendered deck **keeps the BRI logo and design furniture** — the failure that triggered this |
| G2 | **A human opens the deck and confirms it looks like the template** |
| G3 | Cloning a slide with images yields readable images (`pic.image.blob`) — *already met by `deck/clone.py`* |
| G4 | 5 items into a 3-capacity design → two slides, second titled `… (lanjutan)`, **no content dropped** |
| G5 | One design used 4× renders 4 intact copies — *already met* |
| G6 | An admin can correct a mis-catalogued design before the template is usable |
| G7 | A malformed LLM plan is rejected and retried, never rendered into a broken deck |
| G8 | Determinism holds: same plan + template → byte-comparable output |
| G9 | Suites green; ruff/eslint/typecheck clean |

**G1, G2 and G6 cannot be closed by automated tests.** The suite was fully
green while producing a logo-less deck — that is the specific reason these
gates name a human.

---

## 6. Risks, and what is done about each

| Risk | Mitigation |
|---|---|
| **The model mis-reads the template** (a timeline labelled as cards) | LD-4's admin review, before the template can be used. Errors are corrected once, not per deck |
| **Kimi K3 unverified** — existence, pricing, JSON reliability | LD-10 verifies at deploy; per-task routing lets these two calls fall back to a JSON-reliable model without touching chat |
| **Text inside grouped shapes** — anchors may nest several levels down | LD-1 records group nesting explicitly; LD-8 resolves anchors by shape id regardless of depth. Flagged as the most likely source of "text went to the wrong box" |
| **Deck length becomes unpredictable** (L6 splitting) | Accepted and documented: `n_slides` shifts from a contract to a hint. Named here so it is not discovered later |
| **A design has no anchors the LLM can identify** | It is catalogued `unusable` with a reason, exactly as a bad template is today — visible, not silent |

---

## 7. What this plan does not touch

- **Open Notebook / SurrealDB** — same class of problem, still deliberately
  unbundled (`ASSESSMENT-ARCHITECTURE-2026-08-15.md` §7).
- **Chat, guide, sources, ingestion** — untouched.
- **Auth, RBAC, tenancy, metering** — untouched.
- **`TD-27`** (Docling vanishing on `--force-recreate`) — 🔴 and unrelated.
