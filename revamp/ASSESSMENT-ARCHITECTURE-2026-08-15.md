# Technical Assessment — Architecture, and the case for removing Presenton

Why template management and deck generation keep failing, whether the cause is fixable
in place, and what the system looks like if the slide engine is brought in-process.

**Written:** 2026-08-15 · **Branch:** `revamp/phase-1` (`9814ee9`) · **Method:** static
read of every module on the template and generation paths, the compose topology, and the
three prior assessment documents. No VPS access this session — every runtime claim is
marked **UNVERIFIED** and listed in §10.

**Supersedes nothing.** [`ASSESSMENT-TEMPLATE-MANAGEMENT.md`](./ASSESSMENT-TEMPLATE-MANAGEMENT.md)
and [`ASSESSMENT-DECK-GENERATION-REVAMP.md`](./ASSESSMENT-DECK-GENERATION-REVAMP.md) were
both correct within their frame. This one changes the frame.

---

## 1. Verdict

**The bugs you have been fixing are not independent. They are one architectural cost being
paid in instalments.**

Every defect in the last three work sessions sits on the same seam: the boundary between
the orchestrator and Presenton. Not near it — *on* it. And the fixes have all been correct
fixes that could not have prevented the next one, because the next one came from a
different part of the same undocumented contract.

Given your four answers — **no browser editor, exact `.pptx` fidelity, charts instead of
photos, single tenant on one VPS** — Presenton is providing approximately nothing you need
and charging you for a distributed system you did not want.

> **Recommendation: remove Presenton. Render decks in-process with `python-pptx`.**
>
> It is already a dependency (`backend/pyproject.toml:22`) and already used to read decks
> back (`generation/artifact.py`). The migration cost is unusually low because — per
> `TD-32` — **template registration has never once succeeded in this codebase's history**,
> so there is no engine-side state worth preserving.

Confidence: high on the diagnosis, high on the direction, moderate on the effort estimate
in §9 (it depends on how many layouts your real BRI templates expose — see §5.4).

---

## 2. The failure ledger — one seam, nine instalments

Read this column-wise. The pattern is the point, not any individual row.

| # | Defect | Where it lived | Class |
|---|---|---|---|
| 1 | Registration sent a body the engine rejected (422 → fallback) | `engines/presenton.py` | Undocumented contract |
| 2 | Registration called `/templates/` (plural); engine serves `/template/` | `engines/presenton.py:163` | Undocumented contract |
| 3 | `/template/init` returns `layouts: null` — a skeleton that cannot render | engine semantics | Undocumented contract |
| 4 | Task-status endpoint sits outside `/api/v1/ppt`, unlike every other route | `engines/presenton.py:39` | Undocumented contract |
| 5 | `/editor` 404s — `assetPrefix` prefixes assets but not routing | Presenton build config | Two Next.js apps, one origin |
| 6 | `/_next` collides between the two apps; Traefik cannot disambiguate | `docker-compose.lite.yml:250` | Two Next.js apps, one origin |
| 7 | 17-way `PathPrefix` allowlist steals paths from the orchestrator at priority 20 | `docker-compose.lite.yml:250` | Two Next.js apps, one origin |
| 8 | Edited deck is not downloadable — engine's copy and MinIO's copy diverge (`TD-24`) | `generation/worker.py:57-73` | Two systems of record |
| 9 | A pinned template version can silently re-render differently (`TD-26`); engine state is one unbacked SQLite file (`TD-25`) | `presenton_data` volume | Two systems of record |

Three classes, one root: **you integrated a product, not a library.** A library's contract
is its function signatures, checked by your type checker and your tests at build time. A
product's contract is its HTTP surface, checked by nothing, discovered by 404.

`docs/ARCHITECTURE.md` §8 states this codebase's best convention — *"make failure
visible"* — and the registration code follows it faithfully: every failure path records
its reason. That discipline is why `TD-32` took ten seconds to confirm once someone looked.
**It is also why the seam is still expensive.** Excellent diagnostics on a boundary that
should not exist is a well-instrumented tax.

### 2.1 Seven of nine blocked items are this seam

From [`TECH-DEBT.md`](./TECH-DEBT.md) §1: `TD-01` (engine not in version control), `TD-04`
(4-of-5 services build), `TD-05` (`/editor`), `TD-06` (deep link), `TD-07` (`brand_tokens`
never reach the renderer — *the product's headline feature*), `TD-08`, `TD-09`. Plus
`TD-24`, `TD-25`, `TD-26`, `TD-32` from §3.

That is **eleven open items**, including the one your register itself calls *"the
programme's highest-value item"*, all downstream of one integration choice.

---

## 3. What Presenton buys you, priced against your four answers

| Capability | Your answer | Value now |
|---|---|---|
| Browser WYSIWYG slide editor | Drop it | **Zero.** And it has never worked — `TD-05`/`TD-06` blocked, `TD-24` defective |
| LLM designs attractive free-form layouts | Exact `.pptx` fidelity required | **Negative.** LLM-reconstructed layouts are *the opposite* of using the real master |
| AI / stock imagery in slides | Charts and diagrams instead | **Zero.** Charts are `python-pptx` native; Presenton is not needed for them |
| Multi-tenant slide service | Single tenant, one VPS | **Zero.** Presenton has no tenant concept anyway — you namespace names by hand (`registry/registration.py:72`) |
| LLM turns content into slide text | — | **Duplicated.** You already run OpenRouter through `engines/llm.py`, with structured JSON output (`response_format={"type":"json_object"}`, `llm.py:136`) and a tenant-resolved provider config Presenton knows nothing about |

The last row is worth dwelling on. Today **two separate LLM configurations** produce one
deck: yours for the outline, and Presenton's `CUSTOM_MODEL` for slide content
(`docker-compose.lite.yml:232`). The compose file's own comment records that these silently
shared a model until someone noticed. You are paying for a second, unobservable LLM
integration whose prompts you cannot read, cannot version, and cannot test.

**Total value retained, given your four answers: none.**

---

## 4. The migration cost is close to zero, and that is a fact not an argument

The usual reason to keep a bad integration is the data inside it. Here there is none.

| Engine-side state | Migrate? |
|---|---|
| Registered templates | **Nothing to migrate.** `TD-32`: every registration since the project began returned 404 → `fallback`. Zero templates have ever existed engine-side |
| Generated decks | **Already yours.** Bytes are written to MinIO at generation time (`generation/worker.py:64-70`); the engine copy is a duplicate |
| Deck edits made in the studio | **None exist.** `/editor` has never routed (`TD-05`) |
| Uploaded source `.pptx` files | **Already yours.** MinIO, under a tenant key (`registry/service.py:83-95`) |

The one genuinely irreplaceable asset — the uploaded BRI `.pptx` files — is in your object
store and is precisely what the replacement consumes directly.

**Corollary:** the two BRI templates that `TD-32` still owes a live re-registration for do
not need one. Under the replacement they are inspected locally, in-process, in under a
second, with a readable report. The carried-forward blocker in `TM-0-6-REPORT.md` §9
dissolves rather than being closed.

---

## 5. The replacement: a deterministic renderer

### 5.1 The shape

```
sources / chat / custom markdown
        │
        ▼
  outline (already exists — outline/schema.py, LLM-filled, validated)
        │
        ▼
  DeckSpec           ← LLM produces STRUCTURE-FREE CONTENT ONLY, as validated JSON
   slides[]:           (title, bullets, chart data, notes) — never layout, never style
     role, title, bullets[], chart?, table?
        │
        ▼
  renderer.py        ← pure function: (DeckSpec, template.pptx bytes) → deck.pptx bytes
        │              python-pptx. No network. No LLM. Fully unit-testable.
        ▼
     MinIO → download
```

The load-bearing property: **the LLM never decides layout or style, only words and
numbers.** Layout comes from the user's own template. That is what "exact fidelity" means
mechanically, and it is why the pipeline becomes deterministic — the same `DeckSpec` and
the same template produce byte-comparable output, so golden-file tests are possible.

Contrast with today, where fidelity depends on an LLM on the far side of an HTTP boundary
reverse-engineering HTML layouts from your `.pptx` (`/template/layouts/create`,
`/template/generate-blocks` — semantics per `ASSESSMENT-TEMPLATE-MANAGEMENT.md` §1). That
approach cannot be exact by construction, and no amount of debugging makes it exact.

### 5.2 What `python-pptx` genuinely gives you

Opening the uploaded template and adding slides from its own layouts inherits, for free:

- The **theme** — colour palette and font scheme, so text picks up brand fonts without any
  font handling on your side, *provided you never set fonts explicitly*
- **Slide masters and layouts** — placeholder positions, sizes, alignment
- **Static master artwork** — logos, footers, page furniture, divider rules
- Slide size and aspect ratio

Then: fill title/body placeholders with text and bullet levels; add native PowerPoint
charts (`add_chart`, real editable charts, not images); add tables; place pictures.

This is exactly your answer to Q2 and Q3, and it needs no LLM and no network.

### 5.3 What it cannot do — stated before you commit, not after

| Limitation | Severity | Mitigation |
|---|---|---|
| **No text autofit.** `python-pptx` cannot measure rendered text, so a long bullet overflows its placeholder silently | 🟠 **The main real risk** | Derive a character budget per placeholder from its geometry and the layout's font size; enforce it on the LLM output *and* truncate deterministically as a backstop. Report overflow in the generation record rather than shipping a broken slide |
| **Cannot render to image or PDF** | 🟠 | LibreOffice headless in the worker image (`soffice --headless --convert-to pdf`). One package, well-trodden. Gated as its own task — skip it entirely if PPTX-only is acceptable |
| **Cannot invent layouts.** If the template has no two-column layout, there is no two-column layout | 🟡 | Detect at upload and *say so* ("this template offers 4 usable layouts; charts have no home"). Falling back to manually positioned shapes is possible but goes off-master |
| `prs.slide_layouts` exposes only the **first** master's layouts | 🟢 | Iterate `prs.slide_masters[*].slide_layouts`. Corporate templates frequently ship several masters |
| Uploaded templates usually contain **example slides** that must be stripped | 🟢 | Remove entries from `sldIdLst` and drop their relationships. Standard recipe |

The first row is the one to take seriously. It is a genuine regression versus an HTML
renderer, which reflows text natively. The mitigation is sound and testable, but it is
work, and it will need one tuning pass against real BRI content.

### 5.4 The estimate's main uncertainty

**UNVERIFIED — and it is the single input that most moves the effort estimate:** how many
usable layouts do your actual BRI templates expose, and do they use real placeholders or
static text boxes? A corporate template built by a design agency often draws everything as
fixed shapes with no placeholders, which leaves `python-pptx` little to fill.

`RM-1` in the plan exists specifically to answer this **before** anything is built, with a
throwaway script against the two real files. If the answer is bad, the plan changes shape
(see the plan's §7 contingency) — it does not proceed on hope.

---

## 6. What you give up, plainly

1. **Browser editing.** You chose to drop it. Worth naming that this is not really a loss
   today — it is `TD-05`/`TD-06` blocked and `TD-24` defective. You are deleting a feature
   that has never once worked, not removing a working one.
2. **Design variety.** Presenton produces varied, attractive slides for arbitrary content.
   The replacement produces slides that look like your template — every time. That is what
   you asked for, and it is the right call for a bank deck, but decks *will* look more
   uniform. Mitigation: ship a house template with 8–10 layouts (`RM-10`) so a fresh
   install is not limited to whatever one file happens to contain.
3. **Somebody else's problem becomes yours.** Slide rendering moves into code you maintain.
   Offset: it becomes code you can *test*, which the current boundary is not — and
   `TD-22` already records that every engine-tier boundary here is untested.

---

## 7. The same shape of problem, one service over: Open Notebook

Not in scope for your question, and **I am not recommending action yet** — but the
assessment would be incomplete without naming it, because it is the identical pattern.

| Symptom | Item |
|---|---|
| Search index is **global across all tenants**; scoping is enforced on your side, in `OpenNotebookClient.search()` | `ARCHITECTURE.md` §4, `TD-23` |
| Docling silently vanishes on `--force-recreate`, breaking every upload | `TD-27` 🔴 |
| Citations cannot link back to sources — engine ids vs your UUIDs, nothing maps them | `TD-28` |
| Costs two services (`open-notebook` + `surrealdb`) and a third datastore | `docker-compose.lite.yml:172-217` |

For a **single-tenant deployment**, the in-house equivalent is chunking + embeddings in
Postgres with `pgvector`, which would close `TD-23`, `TD-27` and `TD-28` outright and drop
the service count from 11 to 8. The genuine risk is different from Presenton's: Docling
does real document extraction (`.docx`/`.pptx`/`.pdf`) that you would have to keep, and
that is the part that is actually hard.

**Do not bundle this with the Presenton work.** One boundary at a time, each independently
verifiable. Flagged as a decision for after the renderer ships — see the plan's §8.

---

## 8. Complexity that is *not* Presenton's fault

Removing the engine will not fix these, and the plan should not pretend otherwise.

| Finding | Sev | Evidence |
|---|---|---|
| **Two generation services** — `GenerationService` (governed) and `FreeformGenerationService` (freeform), with a third entry `create_from_outline` bolted onto the second. `ARCHITECTURE.md` §3 names divergence between them as "this codebase's recurring failure mode" and it already cost you quota and metering once | 🟠 | `generation/service.py`, `generation/freeform_service.py:190` |
| **The governed path cannot run at all** on the lite stack — `OutlineService.build` needs an approved `StakeholderProfile` that `seed_lite.py` never seeds. So you maintain, test and carry two paths while one is dead weight in the only environment that exists | 🟠 | `outline/service.py:50-54`, per `ASSESSMENT-DECK-GENERATION-REVAMP.md` §7 |
| **Dead statuses.** `GenerationStatus.analyzing` and `.building_outline` are declared, mirrored in the frontend type, and never assigned anywhere in `src/` | 🟢 | `models/generation.py:23-24` |
| **`latest_approved(id) or latest(id)`** silently falls back to an *unapproved* template version rather than refusing | 🟡 | `freeform_service.py:183-185` |
| **Governance ceremony vs. deployment reality.** Immutable versioning, `VersionInUseError`, approve gates, RBAC, quotas and metering — sound, well-built, and sized for a multi-tenant SaaS you told me you are not running. Not a defect; worth deciding consciously whether to keep carrying | 🟡 | `registry/service.py`, `tenancy/`, `metering/` |

The renderer work is the natural moment to collapse the first two: one generation service,
one entry point, one `DeckSpec`. Sequenced as `RM-7` rather than assumed.

---

## 9. Effort, honestly

| Phase | Content | Estimate |
|---|---|---|
| Spike | `RM-1` — inspect the two real BRI templates, answer §5.4 | ½ session |
| Core | `RM-2`…`RM-6` — inspection, model migration, previews, `DeckSpec`, renderer, charts | 3–4 sessions |
| Cutover | `RM-7`, `RM-8` — wire the worker, collapse the paths, delete Presenton | 1–2 sessions |
| Optional | `RM-9` (PDF), `RM-10` (house template), `RM-11` (docs) | 1–2 sessions |

Net code: roughly **+1,400 lines added, −1,300 deleted** (22 backend source files, 21 test
files and 7 frontend files reference Presenton today). The system gets *smaller*.

Compare against continuing to debug the seam: `TD-01`, `TD-05`, `TD-06`, `TD-07`, `TD-24`,
`TD-25`, `TD-26` remain open, each needing engine work, and `TD-07` — the headline feature —
needs the theme-API investigation that is still unstarted. The estimates are not far apart.
The difference is that one of them ends.

---

## 10. Open questions and unverified claims

| # | Item | Why it matters | How to settle |
|---|---|---|---|
| **U1** | Do the BRI `.pptx` templates use real placeholders, and how many usable layouts? | Moves the estimate more than anything else (§5.4) | `RM-1` — a throwaway `python-pptx` script over the two files |
| **U2** | Is PDF export actually required, or is PPTX enough? | Decides whether LibreOffice enters the image (`RM-9`) | Product call — asked in the plan |
| **U3** | The current runtime errors | I assessed the architecture, not your latest failures. If they are *not* on this seam, that is important new information | Paste them (§11) |
| **U4** | Is `revamp/phase-1` deployed to the VPS, or is the box still on `main`? | `TECH-DEBT.md` §1 warns a plain `git pull` reports "Already up to date". Some "same issue after the fix" reports are explained by this alone | `git -C /var/www/notebookfinal branch --show-current` |
| **U5** | Presenton's internal rendering pipeline | I inferred HTML/React layout generation from the endpoint semantics recorded in `ASSESSMENT-TEMPLATE-MANAGEMENT.md` §1. I have not read the engine source — it is not in this repository (`TD-01`) | Only matters if you keep it; the recommendation does not rest on it |

## 11. What would sharpen this

Two commands, and the assessment stops relying on inference:

```bash
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite logs --tail 200 orchestrator worker
```

```bash
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name, version, status, registration_status, left(coalesce(registration_error,%s),160) AS err FROM template ORDER BY created_at;"' 2>/dev/null
```

The second one is the tell. If `registration_error` still reads `preview step returned
404`, the fix in `ab58c24`/`3d9a21b` is not running on that box (U4) and you have been
debugging code that was never deployed.

---

**Plan:** [`PLAN-MONOLITH-RENDERER.md`](./PLAN-MONOLITH-RENDERER.md)
