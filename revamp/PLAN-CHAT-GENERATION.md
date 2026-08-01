# Chat-driven generation: outline-first, confirmed in the thread

Status: **proposal**. Written 2026-07-31, after Phase D shipped `/generate` as a
one-shot freeform card (`186e14c`). Scope: what `/generate` does between the command
and a finished deck.

---

## 0. First, the question asked

**Studio still works.** `/generate` and Studio both `POST /projects/{id}/generations`;
neither was removed, and nothing about one disables the other. Phase D deliberately
kept the form as the control surface and made chat the shortcut. If Studio ever
*should* go away, that is a separate decision about whether anyone still uses it —
not a consequence of shipping the chat trigger.

---

## 1. The finding that should shape this work

The requested flow — *"create outlines based on the template assessment, confirm, then
generate"* — **already exists in this codebase**. It is simply not reachable from chat.

`schemas/generation.py:24` names both paths outright:

| | Governed path | Freeform path |
|---|---|---|
| Entry | `outline_id` | `content_source` + ad-hoc config |
| Structure | `Outline` — validated `sections[]`, `talking_points[]`, `data_bindings[]` | none |
| Settings from | `StakeholderProfile` (approved, versioned) | whatever the form posted |
| Provenance | profile id **+ version**, template id **+ version** | config blob |
| Used by | nothing in the current UI | Studio, and Phase D's `/generate` |

And `StakeholderProfile` already carries **every variable the popup is meant to
collect** — `template_id` + `template_version`, `tone`, `verbosity`, `slide_min`,
`slide_max`, `language`, `section_structure`, `prompt_config`, `audience`.

`section_structure` **is** the "template assessment" being described. The outline
builder turns it into ordered sections and the LLM fills wording but never structure
(`outline/schema.py:5`: *"the LLM fills wording, never the structure"*).

**So this is mostly a routing and surfacing job, not a new pipeline.** That is good
news for the estimate and bad news for anyone who assumed it was greenfield.

### The catch

`seed_lite.py` seeds **no profile**, and `OutlineService.build` requires an
*approved* one (`outline/service.py:50`, raising `profile_not_approved`). So on your
lite stack today the governed path cannot run at all. Any plan has to answer "what
happens when there is no profile" before it answers anything else. See §5.

---

## 2. UX recommendation — inline card, not a modal

The ask was a "mini popup". I would push back, and Claude itself is the evidence:
**Claude does not use modals for this.** Confirmations render as cards *inside* the
conversation, because:

- **You need the conversation while you decide.** A modal hides the very answer you
  are turning into slides. Deciding "8 slides or 12" depends on what is on screen
  behind the modal.
- **The outline is an artifact, not a dialog.** It should stay in the thread, be
  scrollable back to, and survive a reload. A modal implies "transient" and teaches
  the user this thing disappears.
- **Modals are hostile on mobile.** Your workspace already collapses to a bottom tab
  bar below `lg`; a modal on top of that is a third layer.
- **You just spent Phase A fixing an overlay-and-clipping problem.** Adding a
  floating layer over a scroll container is the same class of bug.

Where a popover *is* right: the tiny "change one setting" affordance — clicking
"8 slides" on a summary line opens a 3-item popover anchored to it. Small, anchored,
dismissible. Not the primary flow.

**Recommendation: everything inline, progressive disclosure, two confirmations.**

---

## 3. The proposed flow

```
User: /generate
      │
      ▼
┌─ SETUP CARD (inline, in thread) ──────────────────────────┐
│  Buat slide                                               │
│  Profil ▾ [Board update ▾]      ← pinned settings preview │
│  ────────────────────────────────────────────────────     │
│  Tema bawaan · profesional · 8 slide · Bahasa Indonesia   │
│                              ↑ click any chip to change   │
│  ▸ Opsi lanjutan            ← collapsed: density, lang,   │
│                               web search, export format   │
│  [ Buat kerangka ]  [ Batal ]                             │
└───────────────────────────────────────────────────────────┘
      │  (LLM, ~3-8s — skeleton in place, card stays put)
      ▼
┌─ OUTLINE CARD (inline, editable) ─────────────────────────┐
│  Kerangka · 8 bagian            [ ↻ Buat ulang kerangka ] │
│  ⠿ 1  Ringkasan eksekutif              ✎  ⋯               │
│  ⠿ 2  Latar belakang merchant          ✎  ⋯               │
│  ⠿ 3  Alur pendaftaran                 ✎  ⋯               │
│      ▸ 3 poin pembicaraan   ← collapsed by default        │
│  …                                                        │
│  ────────────────────────────────────────────────────     │
│  [ Hasilkan dek ]  [ Ubah pengaturan ]  [ Buang ]         │
│                     ↑ back to setup, outline kept         │
└───────────────────────────────────────────────────────────┘
      │  (deck generation — the billable, irreversible step)
      ▼
┌─ RESULT CARD (replaces outline in place) ─────────────────┐
│  ✓ Dek siap · 8 slide · Tema bawaan                       │
│  [ Unduh PPTX ]  [ Unduh PDF ]  [ Buka editor ]           │
└───────────────────────────────────────────────────────────┘
```

**Why two confirmations and not one.** The outline is cheap and reversible; the deck
is neither. Splitting them means the expensive step is only ever taken against
something the user has already read. It also gives the outline a job: today nobody
sees `sections[]` before a deck exists, so a bad structure is discovered only after
paying for it.

**Why the settings are a chip row, not a form.** Four values matter (template, tone,
slides, language) and they are already decided by the profile. Showing them as
readable text with click-to-change is faster to scan than four labelled selects, and
it makes the profile the default rather than a thing to re-enter. Everything else
goes behind "Opsi lanjutan".

---

## 4. What has to be built

### 4.1 Backend

| # | Item | Why |
|---|---|---|
| B1 | `ChatMessage.kind` (`text` \| `outline` \| `generation`) + `payload` JSON; migration `0008` | The outline and result cards must survive a reload. Client-only state means a refresh loses the artifact — the opposite of "smooth". This was already logged as a gap in `PLAN-WORKSPACE-UI.md` §5 |
| B2 | `POST /projects/{id}/outline` accepts an optional `session_id`, and emits an `outline` chat message | Puts the artifact in the thread |
| B3 | Generation emits a `generation` chat message on completion | Result card, same reason |
| B4 | An **implicit profile** for projects with none — see §5 | Without it `/generate` is dead on the lite stack |
| B5 | `OutlineService.rebuild(outline_id)` | "Buat ulang kerangka" without re-entering settings |

Not needed: any new generation endpoint. `outline_id` already works.

### 4.2 Frontend

| # | Item |
|---|---|
| F1 | `GenerateSetupCard` — replaces the current `GenerateCard`; profile picker, chip row, advanced disclosure |
| F2 | `OutlineCard` — read/edit sections inline, reorder, collapse talking points |
| F3 | `GenerationResultCard` — status → download links |
| F4 | Chat renders `kind` — `text` as a bubble, `outline`/`generation` as cards |
| F5 | Settings popover anchored to a chip |
| F6 | i18n for all of it, both locales |

### 4.3 What this replaces

Phase D's one-shot `GenerateCard` becomes the *freeform fallback* (§5), not the main
path. The `/generate` command, the ＋ button and "generate from this answer" all keep
working — they just open the setup card instead of the config form.

---

## 5. The decision that blocks everything: no profile

`OutlineService.build` needs an approved `StakeholderProfile`. Lite stacks have none.
Three options:

**A — implicit default profile (recommended).** Seed one approved "Umum / General"
profile per tenant, with a sane `section_structure` (Ringkasan · Latar belakang ·
Temuan utama · Rincian · Langkah berikutnya · Penutup). `/generate` uses it unless
another is chosen. *Pro:* the governed path works on day one, everyone gets outlines,
provenance is real. *Con:* one more seeded row, and the default structure needs to be
good enough not to be fought.

**B — fall back to freeform when no profile exists.** `/generate` silently uses the
Phase D card. *Pro:* zero new data. *Con:* two different behaviours behind one
command, which is exactly the kind of inconsistency that makes a product feel
unfinished. Users cannot tell why they sometimes get an outline.

**C — require the user to create a profile first.** *Pro:* honest and explicit.
*Con:* a wall in front of the feature; nobody wants a registry form before their
first deck.

I recommend **A**, with the profile picker in the setup card so the governed path is
visible and switchable from the start.

---

## 6. Acceptance criteria

Written so each is falsifiable by a test or a click-through.

### AC-1 — `/generate` opens the setup card
- **Given** a project with at least one `ready` source
- **When** the user types `/generate` or clicks ＋
- **Then** a setup card renders **inside the thread**, showing template, tone, slide
  count and language from the active profile
- **And** no outline is built and nothing billable is called until "Buat kerangka" is
  pressed

### AC-2 — outline is built and shown before any deck exists
- **When** "Buat kerangka" is pressed
- **Then** a skeleton renders in place (the card does not jump or unmount)
- **And** on success the card becomes an outline card listing the sections in order
- **And** no `Generation` row exists yet

### AC-3 — the outline is editable and re-runnable
- **Then** a section title can be edited inline and reordered
- **And** "Buat ulang kerangka" produces a new outline without re-entering settings
- **And** edits persist through `PUT /outlines/{id}` and survive a page reload

### AC-4 — generation takes a second, deliberate confirmation
- **When** "Hasilkan dek" is pressed
- **Then** exactly one `POST /generations` fires, carrying `outline_id`
- **And** the result card replaces the outline card **in place**
- **And** pressing it twice does not produce two decks

### AC-5 — the artifacts survive a reload
- **Given** an outline card and a result card in a thread
- **When** the page is reloaded
- **Then** both re-render in their original position with their state
- *(This is what B1 buys; without it this criterion fails and the feature feels
  disposable.)*

### AC-6 — settings are changeable without losing work
- **When** a chip is clicked
- **Then** a popover anchored to it offers just that setting
- **And** changing it after an outline exists prompts a rebuild rather than silently
  invalidating the outline

### AC-7 — prose never triggers anything (regression from Phase D)
- **When** a message merely *mentions* slides or presentations
- **Then** it is sent as a question; no card opens and nothing billable fires

### AC-8 — failure is legible
- No `ready` source → the card says so and offers to open Sources
- Quota exceeded → the engine's own reason is shown, not a generic string
- Outline build fails → the setup card returns with its values intact, not cleared

### AC-9 — accessible and responsive
- Every card is reachable and operable by keyboard; Escape dismisses popovers
- Cards render correctly at 375px inside the mobile chat tab
- No card is absolutely positioned inside the message list (the Phase A clipping bug)

---

## 7. Phases

| | Scope | Depends on | Est. |
|---|---|---|---|
| **E1** | B1 + B4 — `ChatMessage.kind`/`payload`, migration, default profile | §5 decision | 1 day |
| **E2** | F1 + setup card, profile picker, chip row | E1 | 1 day |
| **E3** | B2 + B5 + F2 — outline in thread, editable, rebuildable | E1 | 1.5 days |
| **E4** | B3 + F3 — result card, downloads in thread | E3 | 0.5 day |
| **E5** | F5 chip popover, F6 i18n, AC-8/AC-9 polish | E2–E4 | 1 day |

~5 days. E1 is the gate: without persisted message kinds, AC-5 fails and the rest is
built on sand.

---

## 8. Risks

- **The default `section_structure` decides how every deck looks.** A mediocre one
  makes every generated deck mediocre, and users will blame the AI. Worth drafting it
  with a real example deck in hand.
- **Outline build latency is user-visible** (LLM call). If it exceeds ~8s the card
  needs streaming or a progress hint, or it will feel broken.
- **Two paths still exist.** Studio remains freeform; chat becomes governed. That is
  defensible (quick vs controlled) but should be a stated product position, not an
  accident — otherwise the same deck configured two ways produces different results
  and nobody knows which is canonical.
- **TD-27 is still open.** A `--force-recreate` of `open-notebook` breaks ingestion,
  which breaks sources, which breaks outlines. Fix before demoing this.
