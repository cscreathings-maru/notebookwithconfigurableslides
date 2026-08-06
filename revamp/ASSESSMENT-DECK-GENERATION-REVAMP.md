# Technical Assessment — Deck Generation Workflow Revamp

Assessment of [`revamp - deck generations.md`](./revamp%20-%20deck%20generations.md) against the
code as it stands on `revamp/phase-1` (`5450df5`).

**Written:** 2026-08-05 · **Method:** static reading of every module on the generation path,
plus `git ls-tree` across all local and remote refs. No VPS access — every runtime claim is
marked **UNVERIFIED** and listed in §7.

---

## 1. Verdict

The proposed flow is **mostly buildable on what already exists**. The backend is closer to
the target than the brief assumes: generation is already an async job, template selection
already exists on one of the two entry points, and the editor deep link is already composed
server-side with the correct identifier.

Two things the brief does not mention decide whether it can ship at all:

1. **The slide engine is not in this repository, and `/editor` does not route.** "Open in
   Presenton Studio" — success criteria 3 and 4 — cannot be built, tested, or demoed until
   that is resolved. It is the only item here with no workaround.
2. **An edited deck cannot be downloaded from NoteAI.** The brief's export flow (Option 1
   *and* Option 2) makes two buttons return two different documents, silently. This is a
   correctness defect the design as written would ship.

Everything else — template picker, thumbnails, progress panel, download — is independent of
those two and can proceed.

---

## 2. Claim-by-claim review

Each row states what the brief asserts and what the code does.

| # | Brief's claim | Finding | Evidence |
|---|---|---|---|
| 1 | "No template selection … users cannot browse, select, or preview" | **Partly inaccurate.** Studio has a template `<select>` populated from `GET /templates`, filtered to `approved`. The chat `/generate` card has **none** — those decks always render on the engine's stock theme. Browsing and preview are genuinely absent. | `StudioPanel.tsx:72`, `:190-204`; `GenerateCard.tsx:55-64` |
| 2 | "Deck generation uses a predefined template" | **True for the chat path**, and true for any project whose tenant has no approved template. **False for Studio.** | as above |
| 3 | "Generation should become an asynchronous job" | **Already is.** `POST /projects/{id}/generations` returns `202` with a `Generation` row at `queued`; `commit_and_dispatch` commits the row *before* enqueuing to Arq; `run_generate` → `generate_presentation` does the work. | `api/generations.py:108-134`, `jobs/service.py`, `workers/tasks.py:125-159` |
| 4 | "Missing generation feedback … black box" | **True in effect**, but for three specific reasons, all fixable. See §3. | §3 |
| 5 | "Disconnected editing experience … editor exists as a separate experience" | **True, and understated.** The button exists (`🎨 Editor` in Studio) and the URL is correct by construction. It is the *route* that does not resolve. See §4. | `StudioPanel.tsx:352-364`, `api/generations.py:70-84` |
| 6 | `POST /decks/generate {notebookId, templateId, outlineId}` → `jobId` | **Duplicates an existing endpoint.** `POST /projects/{id}/generations` is already polymorphic on `content_source` (freeform) vs `outline_id` (governed). Adding a third create path repeats the exact divergence this programme has spent two phases unwinding — the freeform path shipped without quota or metering because it was a parallel implementation. Recommend **extending the existing endpoint**, not adding one. | `api/generations.py:113-134`, `docs/ARCHITECTURE.md` §3 |
| 7 | `/studio/:presentationId` | **Not the engine's route.** The verified shape is `/editor/presentation?id=<engine id>` — Presenton's `app-path-routes-manifest.json` maps `/(presentation-generator)/presentation/page` to a **static** `/presentation` with no dynamic segment. A path-segment form does not exist. | `api/generations.py:70-84` and its docstring |
| 8 | (implied by #7) client holds `presentationId` | **Breaks a load-bearing invariant.** Engine ids deliberately never reach the client: `_PUBLIC_PARAM_KEYS` strips the template ref from `params`, and the response carries a *URL* (a capability) rather than the id. Putting the engine id in a NoteAI route reverses that decision. It is reversible — but it should be a decision, not a side effect. | `api/generations.py:42-53`, `schemas/generation.py:66-70` |
| 9 | Template gallery: "Modern / Corporate / Minimal / Academic" | **No such data exists.** A `Template` row is created only when an admin uploads a `.pptx` on `/templates`. There is no seeded catalog, and NoteAI has no knowledge of Presenton's own built-in templates. See §5 and Q3. | `registry/service.py:57-120`, `api/templates.py:76-93` |
| 10 | "Store the selected template identifier with each generation request" | **Already stored**, on both paths: `Generation.template_id` + `template_version`, plus the engine ref inside `params`. | `models/generation.py:48-51`, `generation/freeform_service.py:86-97` |

---

## 3. Progress feedback — the three actual causes

The brief asks for an 8-stage progress panel. The gap is not "no async job"; it is that
**nothing on the generation path emits stage information, and the client has no handle to
read it even if it did.**

**3.1 Two status values are dead code.** `GenerationStatus` declares `analyzing` and
`building_outline`. Nothing in `src/` ever assigns them — the only writers set `generating`,
`validating`, `ready`, `failed`. The frontend type mirrors the enum, so the UI already
believes in stages the backend never reports.
`models/generation.py:23-24`; `grep -rn "building_outline\|analyzing" src/` returns only the
enum declaration.

**3.2 `Job.progress` is written exactly twice, with a constant.** `{"step": "generating",
"percent": 10}` on pickup, `{"step": <terminal>, "percent": 100}` at the end. There is no
intermediate write anywhere, because the work between them is a single `await
presenton.generate(...)` — **the engine does not stream progress back**, so stages 3–7 of the
brief ("Creating slide structure", "Generating slide content", "Applying template",
"Rendering") have no observable events on our side today.
`workers/tasks.py:67`, `:120`, `:137`; `generation/worker.py:58`

**3.3 The client cannot reach the job at all.** `GET /jobs/{id}` exists and returns
`progress`. `GenerationResponse` carries **no `job_id`**, and nothing else maps a generation
to its job. `StudioPanel` therefore polls `getGeneration` every 2.5s and renders a single
status word.
`schemas/generation.py:51-73`, `StudioPanel.tsx:92-106`

**What this means for the design.** Stages 1–2 and 5–8 are honestly reportable (they are our
own steps); stages 3–4 and 6 happen inside one opaque engine call. A panel that animates
through them on a timer would be a fabricated progress bar — the exact "degradation that
looks like success" failure class this codebase has a standing rule against
(`revamp/README.md`, rule 5). **Decision needed (Q5):** either report the stages we can
actually observe, or first establish whether Presenton exposes per-step status for an
in-flight generation (**UNVERIFIED**).

---

## 4. Blocker A — the editor is not reachable, and the engine is not in version control

This gates success criteria 3 and 4 and is not mentioned in the brief.

**4.1 The build context does not exist in this repository.**
`deploy/docker-compose.lite.yml:219-220` builds `presenton` from `../presenton-custom`. That
path is tracked on **no ref** — verified against `main`, `origin/main`, `revamp/phase-0`,
`revamp/phase-1`, `origin/revamp/phase-1`. `.gitignore:23-30` anticipates a vendored tree at
`presenton/source/`, which also does not exist. `git log --all -- '*presenton*'` is empty.
This is `TD-01`, still open.

> **This contradicts what I was told** — that the engine is committed to
> `cscreathings-maru/notebookwithconfigurableslides`. That is this repo's `origin`, and
> `git ls-remote` shows only `main` and `revamp/phase-1`, neither containing it. See **Q1**.

**4.2 `/editor` requires a change that has not been made.** Same-origin routing works only
with build-time `basePath: '/editor'` in Presenton's `next.config.mjs` — baked at build time,
because standalone Next.js does not read the config at runtime. The one known delta on the
VPS is `assetPrefix: '/editor'`, which prefixes **assets but not routing**, so `/editor`
returns Next's 404 layout while its assets resolve. `TD-05`.
`docs/ARCHITECTURE.md` §2; `docker-compose.lite.yml` presenton labels (the comment states this
explicitly).

**4.3 Consequence.** `editor_url` is correct and already on the wire; `SlideEditorModal`
already loads it. The link points at a route that does not answer. Making "Open in Presenton
Studio" the default post-generation destination — the centrepiece of this revamp — is
therefore blocked on `TD-01` → `TD-05`, in that order. Nothing else in the brief is.

---

## 5. Blocker B — what "the desired template" can actually control

Stated goal: *"using the desired template that has been configured, following the font, tone,
locations and components and everything from the template."* Two structural facts constrain
that.

**5.1 The uploaded PPTX *is* the brand. The colour pickers are not.** Presenton's
`POST /templates/init` accepts no colour or font parameters — it derives layouts, fonts and
palette from the deck itself. So fidelity to "font, locations, components" arrives **only**
through template registration, and only for templates whose registration actually succeeded.
`engines/presenton.py:104-137`

**5.2 `brand_tokens` reach Postgres and nothing else.** Every value the 4-section Template
Configurator collects is stored and never sent anywhere — neither mapper carries it. `TD-07`.
A user who configures brand colours and no PPTX gets a stock-theme deck; the UI now says so
(`RegistrationStatus.fallback` + `RegistrationBadge`) rather than pretending, but the feature
does not function.
`registry/service.py:101-112`, `generation/mapper.py:56-68`, `generation/freeform_mapper.py:58-77`

**5.3 Implication for the template picker.** "Select a template" should mean *select a
registered engine template* — i.e. one where `registration_status == registered` and
`presenton_template_ref != "default"`. Anything else is a picker that offers choices which do
not change the output. The registry already models this precisely; the picker should surface
it rather than filtering only on `status == approved` as Studio does today.
`StudioPanel.tsx:72` filters on `approved` only — a template can be *approved* and *fallback*
simultaneously, and today it would appear in the list and silently render stock.

**5.4 A governance hole to decide on.** The freeform path resolves a template as
`latest_approved(id) or latest(id)` — falling back to an **unapproved** version rather than
refusing. If the picker becomes the primary control surface, this becomes user-visible.
`generation/freeform_service.py:90-92`

---

## 6. Blocker C — the export flow as designed returns two different documents

The brief offers export in two places: immediately after generation (NoteAI) and inside the
studio (Presenton). Today those are **not the same file**.

Deck bytes are produced once, during generation, and written to MinIO. Editing in the studio
updates Presenton's own copy in its SQLite/`app_data` volume. NoteAI's download endpoint
streams the stored object — the **pre-edit** file — with no error and no indication.
`generation/worker.py:57-73`, `api/generations.py:155-184`, `TD-24`,
[`PLAN-EDITOR-ROUNDTRIP.md`](./PLAN-EDITOR-ROUNDTRIP.md)

The current UI mostly hides this because editing is not reachable (§4). **This revamp's whole
premise is to make editing the default next step**, which converts a latent defect into the
common case: edit → download → old slides. Option 1 and Option 2 in the brief must either be
reconciled (re-fetch from the engine on download, invalidating the stored artifact) or Option
1 must be removed once a deck has been opened for editing. **Q6.**

---

## 7. Smaller findings, ranked

| Sev | Finding | Evidence |
|---|---|---|
| 🟠 | **Replacing the Studio panel deletes the only control surface** for tone, density, slide count, language, model, export format and web search. The brief's picker has none of them. Chat's card has three. Where do the rest go? **Q4** | `StudioPanel.tsx:163-294` vs brief §"Proposed Right Panel" |
| 🟠 | **Thumbnails already exist and are thrown away.** `fonts-upload-and-slides-preview` returns `slide_image_urls`; they are forwarded to `init` and then discarded — `TemplateRegistration` carries only `ref`/`status`/`error`. Persisting them is the cheapest path to a visual picker. Needs a migration and a decision on serving (Presenton's `/app_data` is already allowlisted in Traefik, or copy to MinIO). | `engines/presenton.py:157`, `:191-193`; `models/registry.py:86-99` |
| 🟡 | A per-template preview link **already exists** and is correct — `/editor/template-preview?id=<engine ref>`, `None` when registration fell back. It shares `/editor`'s fate (§4), but the picker should reuse it rather than invent a preview. | `api/templates.py:34-48`, `tests/unit/test_template_preview_url.py` |
| 🟡 | The brief's flow assumes **"Generate Deck Outline"** precedes the picker. Outlines exist and are validated, but no UI reaches them, and `OutlineService.build` requires an *approved* `StakeholderProfile` that `seed_lite.py` never seeds — so on the live lite stack the governed path **cannot run at all**. This is the parked §5.4 scope decision resurfacing inside this brief. **Q2** | `outline/service.py:50-54`, [`PLAN-CHAT-GENERATION.md`](./PLAN-CHAT-GENERATION.md) §5 |
| 🟡 | `Generation.project_id` is nullable and `list_generations` is per-project — a "presentations belong to a project" association the brief asks for already holds. No work needed. | `models/generation.py:37-39` |
| 🟢 | Frontend `GenerationStatus` already lists the two dead statuses, so removing them is a two-file change, not a contract break with anything real. | `services/api.ts:204-211` |

---

## 8. What is already done vs. what is new work

| Brief requirement | State |
|---|---|
| Async generation job | **Done** |
| Persist generation status | **Done** |
| Associate presentations with projects | **Done** |
| Store selected template id per generation | **Done** |
| Endpoints for status / retrieval / download | **Done** |
| Template selection (Studio) | **Done**, wrong filter (§5.3) |
| Template selection (chat `/generate`) | **Missing** |
| Template thumbnails | **New** — data exists, not persisted |
| Template metadata / browse UI | **New** |
| Stage-level progress | **New**, and partly unobservable (§3) |
| `job_id` on the generation response | **New** — one field |
| Open in studio | **Blocked** (§4) |
| Edit → export the edited file | **Blocked / defective** (§6) |
| Download PPTX after generation | **Done** |

Roughly: five of thirteen items are already shipped, four are ordinary new work, two are
blocked on the engine not being in version control, and two need a product decision before
anyone writes code.

---

## 9. Confirmations needed

Answering **Q1** and **Q6** changes what is buildable. The rest change scope.

**Q1 — Where is the Presenton source?** I could not find it on any branch of
`cscreathings-maru/notebookwithconfigurableslides`, and `../presenton-custom` does not exist
locally. Is it (a) committed to a branch not yet pushed, (b) in a different repo, or (c)
still only untracked on the VPS at `/var/www/notebookfinal/presenton-custom`? If (c), TD-01
is open and §4 stands as written.

**Q2 — Does this revamp assume an outline step?** The brief's flow has "Generate Deck
Outline" before the picker, which is the governed path — the one that cannot run on the lite
stack without a seeded profile. Should I assess this as *freeform + template picker* (no
outline), or does this brief supersede the parked §5.4 decision?
*(Parked per your instruction — flagging it because this brief walks into it.)*

**Q3 — What populates the gallery?** "Modern / Corporate / Minimal / Academic" implies a
stock catalog. Options: (a) admin-uploaded PPTX only — what exists today; (b) seed 3–5
house templates as real `.pptx` files and register them at deploy; (c) expose Presenton's
own built-in templates, which would need a new engine capability I have **not verified**
exists. Which?

**Q4 — Where do the other deck settings live** once the picker replaces the Studio form —
tone, density, slide count, language, model, export format, web search? Options: behind an
"advanced" disclosure on the picker; moved onto the template (so a template pins its tone);
or dropped.

**Q5 — Honest progress or fabricated progress?** Stages 3, 4 and 6 happen inside one opaque
engine call. Do you want (a) only the stages we can actually observe, (b) me to first verify
whether Presenton exposes in-flight generation status, or (c) a time-based animation
(explicitly a fabricated signal)?

**Q6 — Which file does "Download PPTX" return after an edit?** Today, the pre-edit one,
silently. Choose: (a) NoteAI re-fetches from the engine on download; (b) editing invalidates
the stored artifact and download is disabled until re-export; (c) after opening the editor,
export is only offered inside the studio.

**Q7 — Is the engine id allowed to appear in a NoteAI URL?** The brief's `/studio/:id`
requires it. Keeping the current `editor_url` capability preserves the invariant with no loss
of function; I'd keep it unless you want the deep-linkable route.

---

## 10. Parked decisions referenced by this brief

- **§5.4 governed-vs-freeform scope** — deferred by you on 2026-08-05, to revisit. Q2 above
  is where it touches this work.
- **TD-27** (Docling does not survive `--force-recreate`) — unrelated to this brief but sits
  upstream of every deck: broken ingestion → no grounding → empty decks. Worth confirming the
  live stack is still healthy before demoing any of this.

---

## 11. Decisions locked (2026-08-05)

| # | Decision |
|---|---|
| Q1 | **Open — verify on the VPS.** See §14. Nothing in §4 is assumed fixed until checked. |
| Q2 | An outline step **is** in scope — for token efficiency and a confirm-before-spend step, not for governance. Structure is **not** a fixed profile `section_structure`; the LLM decides shape/length from content, steered by a written prompt. This is a **new, ungoverned outline**, decoupled from `StakeholderProfile`. Does not reopen §5.4 — it only means the *existing* governed outline path (profile-gated) is not what gets built. See §12. |
| Q3 | Gallery = admin-uploaded templates only (what `/templates` already produces). No stock catalog, no exposing Presenton's built-ins. |
| Q4 | Tone / density / slides / language / model / export / web search move behind an "Advanced" disclosure on the new picker+outline card. Not removed, not on the template. |
| Q5 | Status only — `queued` / `generating` / `ready` / `failed` (+ a distinct "building outline" step, which is real and observable, unlike the engine-internal stages). No fabricated stage animation. |
| Q6 | **Option C.** Once a generation's presentation has been opened in the studio, NoteAI stops offering its own download for that generation; export happens inside Presenton from then on. See §12.4 for how "opened" is tracked. |
| Q7 | Keep the current `editor_url` capability. No engine id in a NoteAI route. |

---

## 12. Revised design

### 12.1 Outline: a second, unguarded builder

`OutlineService.build` and its `build_outline()` stay exactly as they are — the governed
path remains available if §5.4 is ever resolved toward it. This adds a **second** builder
next to it, not a replacement:

```
build_outline()          existing — profile.section_structure is authoritative, LLM fills wording only
build_freeform_outline()  new — LLM proposes both structure AND wording in one pass
```

**Why one pass, not two.** The governed path calls the LLM once for talking points because
structure is already fixed. A freeform outline doesn't have that shortcut — structure has to
come from *somewhere* — but the token-efficiency goal (Q2) argues against a
structure-then-content two-call sequence when one well-specified call can return both. The
prompt asks for a JSON array of `{title, bullets: string[]}`, with the section *count*
constrained to a soft range (e.g. 4–12) rather than fixed, and steered by:

- the retrieved grounding snippets (same `on_client.search()` call the governed path uses),
- the four content-source choices already in the freeform mapper (`summary` / `notebook` /
  `chat` / `custom`),
- the Q4 "advanced" knobs (tone, density, an optional target slide count as a *hint*, not a
  contract).

**Persistence — reuse `Outline`, don't fork a new table.** `Outline.profile_id` and
`profile_version` are `NOT NULL` today (`models/outline.py:25-26`), which is the only thing
stopping reuse. Making both nullable is a small, additive migration — the same shape as
`Generation.profile_id` already being nullable for its freeform path. Everything else on the
row (`content`, `valid`, `schema_version`) is already profile-agnostic; `OutlineContent`,
`validate_outline`, and the edit/reload/re-validate flow (`PUT /outlines/{id}`) all work
unchanged for a profile-less row. `repair_outline` (which repairs onto a *fixed* title list)
simply isn't called on this path — a freeform draft that fails validation is regenerated, not
repaired, because there is no fixed structure to repair onto.

**Generation from a confirmed freeform outline.** The existing governed `GenerationService`
cannot be reused as-is — it looks up `profile.template_id`/`template_version` from the
outline's pinned profile, which won't exist here. Two ways to close that, in order of
preference:

- **(a) Teach `FreeformGenerationService` a fifth content path: `outline_id`.** When a
  freeform-built `Outline.id` is passed instead of `content_source`, derive
  `slides_markdown` from `outline.content` the same way the governed mapper already does
  (`mapper.py:_slides_markdown`) — one block per section, bullets as talking points — then
  feed it into `build_freeform_request`. This keeps one generation code path (freeform) and
  reuses a function that already exists; the deck's structure is still fixed by the confirmed
  outline, Presenton just renders it.
- **(b)** A third service. Rejected: repeats the divergence documented in
  `docs/ARCHITECTURE.md` §3 ("divergence between the two is this codebase's recurring
  failure mode") for no functional gain over (a).

`POST /projects/{id}/generations` needs one addition: accept `outline_id` **without**
requiring it to resolve through `OutlineRepository` + a profile — i.e., branch on whether the
referenced outline has a `profile_id` (governed → existing `GenerationService`) or not
(freeform-with-structure → path (a) above). This is the one place `docs/ARCHITECTURE.md`'s
warning about the endpoint being "polymorphic" gets a third branch; worth a short comment
there when built, given the file already flags this exact endpoint as the programme's
recurring failure mode.

### 12.2 Revised flow

```
Notebook (sources ready)
    │
    ▼
Template picker  ── admin-uploaded, registered templates only (Q3) ── optional, may be skipped
    │
    ▼
Outline card  ── content source + advanced knobs (Q4) ── "Build outline"
    │            (token spend: one LLM call, cheap, reversible)
    ▼
Outline review  ── edit sections/bullets, "Regenerate", "Confirm"
    │
    ▼
POST /generations {outline_id}   ── the billable, irreversible step
    │
    ▼
Status: queued → generating → ready | failed   (Q5 — no fake stages)
    │
    ▼
Ready
 ├─ Download PPTX/PDF   (available until studio is opened — Q6)
 └─ Open in Studio  ──►  marks studio_opened  ──►  NoteAI download hidden from here on
```

### 12.3 `GenerationStatus` cleanup

`analyzing` and `building_outline` are dead on `Generation` (§7, 🟢 finding) and, given §12.1,
they were never going to be generation-internal states anyway — outline building now
genuinely happens *before* a `Generation` row exists, as its own request/response with its
own spinner. Recommend deleting both enum values (backend `models/generation.py:23-24`,
frontend `services/api.ts:204-211`) rather than repurposing them.

### 12.4 Q6, concretely — tracking "opened"

A client-side-only flag (session state) would reset on reload and wouldn't hold if a second
person on the tenant opens the same generation, so it's not the right minimal fix. Smallest
durable option:

- One column: `Generation.studio_opened_at: datetime | None`.
- One tiny endpoint (or a query param on the existing `GET /generations/{id}` that the
  "Open in Studio" click fires before navigating): sets it once, idempotently.
- `_to_response` in `api/generations.py` stops reporting `artifacts.pptx`/`artifacts.pdf` as
  available once `studio_opened_at is not None` — the frontend hides the NoteAI download
  buttons for that generation, same as it already hides `editor_url` when `None`
  (`StudioPanel.tsx:352`).

This keeps the "download immediately after generation" half of the brief's own success
criteria intact (§ "Success Criteria": *download either directly after generation or from
within the editor*) while making Option C's cutover real and not just a UI convention that a
reload would undo.

### 12.5 Revised phased build order

Supersedes the "what is already done vs. new work" table in §8 for planning purposes; §8
itself stays accurate as a status snapshot.

| Phase | Scope | Blocked on |
|---|---|---|
| **R1** | `Outline.profile_id`/`profile_version` nullable (migration); `build_freeform_outline()` + prompt; `POST /projects/{id}/outline` accepts no `profile_id` and routes to the new builder; outline review UI (list/edit/regenerate/confirm) | nothing — buildable now |
| **R2** | `outline_id`-without-profile branch on generation create; `_slides_markdown`-style mapping reused for freeform-from-outline; wire "Confirm" → `POST /generations` | R1 |
| **R3** | Template picker (registered templates only, Q3); thumbnails persisted from `slide_image_urls` (§7, 🟠 finding) + migration; picker wired into the outline card, not replacing Studio's other knobs (Q4) | independent of R1/R2, can run in parallel |
| **R4** | `studio_opened_at` column + endpoint + response/UI change (§12.4) | independent — but pointless to ship before the editor is reachable (Blocker A) |
| **R5** | Delete `analyzing`/`building_outline` (§12.3) | independent, do whenever convenient |
| — | "Open in Studio" actually working | **Blocked on TD-01 → TD-05 (§4).** R4 has no user-visible effect until this lands. |

R1–R3 and R5 do not touch Presenton at all and can proceed regardless of what §14 finds.

---

## 13. What §12 deliberately leaves alone

- The existing governed path (`OutlineService.build`, profile-gated) is untouched — kept for
  if/when §5.4 resolves toward it.
- Studio's existing form is not deleted; the brief's picker is additive UI sitting in front
  of a `/generate`-style confirm step, per Q4.
- No change to `check_consistency` / the consistency gate — outlines built by
  `build_freeform_outline()` have no `profile_id`, so `generation/worker.py:77` already skips
  it (`mode: freeform`) with no new code.

---

## 14. Q1 — VPS investigation (resolved 2026-08-05)

**§4 is substantially wrong. Revised below; superseded in full by
[`PLAN-DECK-GENERATION-REVAMP.md`](./PLAN-DECK-GENERATION-REVAMP.md) §1.**

### 14.1 The engine source exists, with real history, on a real fork

`presenton-custom/` on the VPS is a clean git checkout, branch `noteai/deployed`, working
tree clean, two remotes:

```
origin  https://github.com/presenton/presenton            (upstream)
fork    git@github.com:cscreathings-maru/presenton.git    (their own fork — NOT the monorepo)
```

```
82555808 (HEAD -> noteai/deployed) fix: basePath /editor so routing matches the same-origin mount (T-1.1)
41119096 config: assetPrefix /editor for same-origin serving under NoteAI
1f871549 (tag: v0.9.3-beta) fix: update version to 0.9.3-beta in package.json
```

**This resolves my §4 confusion.** I checked `cscreathings-maru/notebookwithconfigurableslides`
(this repo's own `origin`) and correctly found nothing — the engine was never there. It lives
in a **sibling repo under the same org**, `cscreathings-maru/presenton`, which nothing in this
codebase's docs points to. `TD-01`'s "commit the delta with provenance" is **functionally
done**: real fork, real upstream remote, the exact `basePath` commit `TECH-DEBT.md` describes
as the one thing that was missing. One bookkeeping gap remains — see §14.4.

### 14.2 `/editor` routing already works — the 404 is gone

```
curl -sD - -o /dev/null https://notellm.umarsyukri.com/editor
→ HTTP/1.1 401 Unauthorized
```

A 401 is not a routing failure. Traefik matched the path and forwarded to the container; the
container's own app answered — with an auth challenge, not a 404. **`TD-05` is done.** My
`next.config`/`BUILD_ID` grep came back empty, but that check was mistargeted (standalone
Next.js doesn't ship `next.config.mjs` into the runtime image, and `BUILD_ID` is a bare hash,
not JSON) — it proves nothing either way. The status code is the real signal, and it's
conclusive: routing resolved, something else now gates access.

### 14.3 New finding: the editor is behind HTTP Basic Auth real users don't have

The 401 is `PresentonClient`'s own documented behavior, applied to the browser now that
routing reaches the app: *"HTTP Basic auth (admin user/pass, **same as the web UI**) is
engine-internal defense-in-depth"* (`engines/presenton.py:2-4`). `PRESENTON_AUTH_USERNAME`/
`PASSWORD` gate the UI exactly as they gate the API. `DISABLE_AUTH=true` in the compose
environment does not turn this off — it evidently controls a different, Presenton-internal
login screen, not this transport-level challenge.

**This is a new, distinct blocker**, not the one `TECH-DEBT.md` described. "Open in Studio"
now needs one more fix: the *user's browser* has no way to satisfy a Basic Auth prompt it was
never given credentials for, and putting `user:pass@` in a URL is not viable (Chrome strips
userinfo from URLs; it's bad practice regardless). The credential does not need to be secret
from the end user in the way it needs to be secret from the open internet — Presenton's
port is already `127.0.0.1:8100`-bound and reachable only through Traefik — so the fix is to
have **Traefik supply the credential itself**:

```yaml
# on the presenton router
- "traefik.http.routers.presenton.middlewares=presenton-auth@docker"
- "traefik.http.middlewares.presenton-auth.headers.customrequestheaders.Authorization=Basic ${PRESENTON_BASIC_AUTH_B64}"
```

with `PRESENTON_BASIC_AUTH_B64` precomputed (`base64("$PRESENTON_AUTH_USERNAME:$PRESENTON_AUTH_PASSWORD")`)
and added to `.env.lite`. This changes nothing about what the credential protects — a direct
hit to the container's own port still requires it, and nothing outside Traefik is granted new
access — it just means Traefik, not the browser, presents it. Small, scoped, no engine change.
See the final plan, `DG-0`.

### 14.4 What's still open

- **Push status unconfirmed.** `git status` on `presenton-custom` didn't report tracking
  info against `fork/noteai/deployed`, so whether these commits reached
  `github.com/cscreathings-maru/presenton` is unverified. Formally closing `TD-01`'s
  "committed... with history" needs one more check: `git -C presenton-custom log
  fork/noteai/deployed..HEAD` (empty output = pushed) or `git -C presenton-custom push fork
  noteai/deployed --dry-run`.
- **`/var/www/notebookfinal/presenton` (no `-custom`) is a second, unexplained directory.**
  Likely the redacted staging tree the recovery script produces for `TD-02` (a safe copy
  intended for eventual commit into *this* repo, distinct from the live mutable
  `presenton-custom`) — consistent with `TECH-DEBT.md`'s `presenton/config/userConfig.example.json`
  reference — but unconfirmed. Both `presenton/` and `presenton-custom/` show as **untracked**
  (not ignored) in this repo's `git status`, which is the exact hazard `TD-04`'s note about a
  205MB accidental vendor describes; worth a `.gitignore` entry for both directory names, not
  just the `**/app_data/` etc. globs already there.
- **Off-host backup still not off-host.** `/root/noteai-backups/*.tar.gz` — two archives, on
  the same host they exist to survive. `TD-03` stays `PARTIAL`, unchanged from before this
  check.
- **`Server: nginx/1.24.0`** answered the `curl`, where the architecture doc states only
  Traefik publishes a port. Almost certainly a host-level TLS-terminating reverse proxy in
  front of Traefik (a common, unremarkable setup) rather than a contradiction — not chased
  further; flag if it becomes relevant.
