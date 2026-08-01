# Workspace UI — Assessment & Plan

Status: **plan approved, implementation not started.** Written 2026-07-31, after RAG
grounding was fixed (`ad22136`, `943aa7a`). Scope: the project workspace at
`frontend/src/app/(app)/projects/[id]/page.tsx` and the four panels under
`frontend/src/components/project/`.

**Decisions taken (product owner, 2026-07-31):**

| Question | Decision |
|---|---|
| Generation trigger | `/generate` slash command + editable confirmation card. **No free-text intent detection.** |
| Chat sessions | Session switcher, **one active thread at a time**. Not stacked accordions. |
| Next step | Plan only. No code until explicitly asked. |

Sections 2.2 and 2.3 record the reasoning behind the first two; they are settled, not
open for re-litigation during implementation.

---

## 1. What is actually broken today

Findings are anchored to code, not impressions.

### 1.1 The chat has no height ceiling — this is the "never-ending scroll"

The middle column is `flex flex-col gap-6 lg:col-span-5 min-h-[500px]`
(`page.tsx:65`) and holds `GuidePanel` (auto height) stacked above `ChatPanel`
(`h-full min-h-[400px]`, `ChatPanel.tsx:89`).

`ChatPanel`'s message list is `flex-1 overflow-y-auto` (`ChatPanel.tsx:97`) — correct
in isolation. But **no ancestor establishes a bounded height**. `min-h-*` sets a floor,
never a ceiling. So the column grows with its content and the *page* scrolls instead of
the message list. Every new turn pushes the composer further down the document.

This is structural, not cosmetic. Restyling the bubbles will not fix it. The workspace
has to become a fixed-height grid — an explicit viewport-derived height, plus `min-h-0`
on every flex ancestor — so that the message list is the only thing that scrolls.

### 1.2 One infinite thread per project

`ChatMessage` carries only `project_id` (`backend/src/models/chat.py:31`). There is no
session, no thread, no pagination. `api.listChat(projectId)` returns every message ever
sent in the project and the client renders all of them (`ChatPanel.tsx:109`).

Two consequences, and the user is feeling both:

- **Topics collide.** Onboarding questions and, later, pricing questions live in one
  undifferentiated stream.
- **The payload only grows.** Nothing truncates, windows, or paginates.

### 1.3 Citations work now, but are not usable

Grounding was just fixed, so citations finally arrive populated. They render as
`<span title={c.snippet}>Sumber N</span>` (`ChatPanel.tsx:126`).

`title` is hover-only: invisible on touch, unreachable by keyboard, ignored by most
screen readers. There is also no path from a citation back to the source that produced
it, even though `Citation.source_ref` carries the engine id.

Citations are the trust surface of a RAG product. This is the highest value-per-effort
item on the whole board.

### 1.4 Sources poll forever

`SourcesPanel.tsx:34` — `setInterval(load, 2500)` with **no terminal condition**. The
production logs show `GET /projects/{id}/sources` every ~2.5s for twenty minutes with
nothing processing. It should stop once no source is `queued` or `processing`.

### 1.5 Studio is a 411-line form competing with chat for permanent attention

`StudioPanel.tsx` is the largest component in the app: eight controls (template, tone,
density, slide count, output, language, model, web-search), all always visible, holding
1/3 of the workspace permanently. Generation is an occasional act; chat is continuous.
The layout currently gives them equal standing.

---

## 2. The proposal — agreements and pushback

### Agreed

- **Three columns is right — and you already have it.** The 12-col grid is
  Sources(3) · Guide+Chat(5) · Studio(4). The real change is *what goes where*, not the
  column count. Worth knowing, because it makes this a much smaller job than it sounds.
- **The guide belongs on the right.** It is reference material — glanceable, rarely
  interacted with. The centre column should belong to what users touch most.
- **Multi-session chat is correct and overdue.** See 1.2.

### Pushback 1 — do not let free-text chat trigger generation — **ACCEPTED**

Triggering generation by classifying intent from free text means a **probabilistic
classifier firing a billable, irreversible, artifact-producing action**. Both failure
directions are bad:

- *False positive*: "bisakah kamu ringkas ini seperti untuk presentasi?" → 8 slides
  generated, quota consumed, user surprised.
- *False negative*: user asks explicitly, nothing happens, feature looks broken.

**Recommendation — explicit trigger plus confirmation card:**

1. A `/generate` slash command (and a `＋` button) in the composer opens a **compact
   inline form inside the chat**, prefilled from the last-used config.
2. The assistant *may* proactively **propose** generation, but renders it as a
   confirmation card with visible, editable params. It never auto-executes.
3. The irreversible step is always one deliberate click with the parameters on screen.

This keeps the conversational feel without betting money on an intent classifier. It is
also testable — intent detection largely is not.

### Pushback 2 — accordion-stacked sessions rebuild the bug you are fixing — **ACCEPTED**

If "accordion" means several sessions expanded in one column, you recreate the exact
unbounded-height problem from 1.1.

**Recommendation:** a session **switcher** at the top of the chat column (slim list or
dropdown), with **one active thread at a time** — the pattern users already know from
ChatGPT, Claude and NotebookLM. Keep "collapse the entire chat column" as a separate
focus-mode affordance if that is what you actually wanted.

### Pushback 3 — do not delete Studio — **open, decide before Phase B**

Configuring eight parameters through conversation is slower than a form for anyone
doing it more than once. Chat-triggered generation should be the **shortcut**; the form
stays the **control surface**.

**Recommendation:** the right column becomes a two-tab rail — **Ringkasan** (guide) and
**Studio** — sharing one column. Tabs rather than a fourth column: at 1440px a fourth
column starves the chat, which is the primary workspace.

---

## 3. Proposed layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  NoteAI   ·   Onboarding new                                    [Bahasa ▾] │
├──────────────┬───────────────────────────────────┬─────────────────────────┤
│ SUMBER       │ OBROLAN                           │ ⟨Ringkasan⟩ ⟨Studio⟩    │
│              │ ┌───────────────────────────────┐ │                         │
│ ⊕ Upload     │ │ ▾ Onboarding merchant    ⋯    │ │  Ringkasan notebook     │
│              │ └───────────────────────────────┘ │  ─────────────────      │
│ ▪ Panduan…   │      ↑ session switcher           │  Dokumen ini menjelas…  │
│   OFFICE ●   │                                   │                         │
│ ▪ 00-over…   │  ┌─────────────────────────────┐  │  Pertanyaan awal:       │
│   TEXT   ●   │  │ … only this area scrolls …  │  │  › Apa syarat daftar?   │
│ ▪ Template…  │  │                             │  │  › Berapa lama proses?  │
│   OFFICE ●   │  │  [assistant bubble]         │  │                         │
│              │  │  [1] [2]  ← real citations  │  │  ┌───────────────────┐  │
│              │  │                             │  │  │ Studio (tab 2)    │  │
│              │  └─────────────────────────────┘  │  │ template, nada,   │  │
│              │  ┌─────────────────────────────┐  │  │ slide, bahasa…    │  │
│              │  │ ＋ │ Tanyakan…        │ ▶ │  │  │ [Hasilkan]        │  │
│              │  └─────────────────────────────┘  │  └───────────────────┘  │
│   3 cols     │        5 cols                     │        4 cols           │
└──────────────┴───────────────────────────────────┴─────────────────────────┘
   ↑ unchanged      ↑ gains sessions + bounded height     ↑ guide moves here,
                      + /generate                            studio becomes tab 2
```

Column spans stay `3 / 5 / 4`. The whole grid gets a fixed height so only the message
list and each rail scroll internally — the page itself never scrolls.

**Responsive** (the current layout collapses to a single column below `lg`, which is
a stack of three tall panels — poor on tablet):

| Breakpoint | Behaviour |
|---|---|
| ≥1280 | three columns as above |
| 1024–1280 | right rail collapses to an icon-tab drawer over the chat |
| <1024 | bottom tab bar: Sumber · Obrolan · Ringkasan; chat is the default tab |

---

## 4. Interaction decisions

**Sessions.** Auto-title from the first user message (truncated), renameable inline via
double-click or the `⋯` menu. New session button. Delete with undo. Sessions are
per-project. A project always has at least one session; existing messages backfill into
"Obrolan 1".

**Message list.** Render the most recent N (~50) with "muat pesan sebelumnya" above.
Keeps first paint cheap on long threads.

**Citations.** Replace the `title` tooltip with a real control: a numbered chip that is
a `<button>`, opening a popover with the snippet, the source name, and a link that
highlights that source in the left rail. Keyboard reachable, screen-reader labelled.

**Generation from chat.** `/generate` renders an inline card in the thread. Its result
(a `generation` record) also renders in-thread as a status card → download links. The
Studio tab and the chat card write to the same config, so switching between them is
lossless.

**Empty and error states.** The current empty state is decent. Add: a session with no
messages should surface the guide's suggested questions as chips, so a new thread is
never a blank box.

---

## 5. What this costs on the backend

This is the part that is invisible in a UI mock, and it is most of the work.

| Item | Backend change |
|---|---|
| Multi-session chat | New `ChatSession` model (id, project_id, title, archived, timestamps); `ChatMessage.session_id` FK; Alembic migration backfilling existing rows into a default session per project; `GET/POST/PATCH/DELETE /projects/{id}/chat/sessions`; `listChat`/`sendChat` become session-scoped. Tenant scoping must go through `TenantScopedRepository` like every other model. |
| Message windowing | `limit`/`before` params on the chat list endpoint. |
| Generation from chat | A generation started from a session should be linked to it, so its status card can render in-thread. Either `Generation.chat_session_id`, or a `ChatMessage` of kind `generation_ref`. The latter is less invasive. |
| Citations → source | `Citation.source_ref` is the *engine* id. The left rail keys off the orchestrator's own `Source.id`. Needs a mapping in the chat response, or the API resolving `source_ref` → `source_id` before returning. **This is a genuine gap — the UI cannot link a citation to a source today even if it wanted to.** |
| Guide, Studio | No change. |

Frontend state also needs attention: the app uses plain `useState` + `fetch` with no
data layer (`package.json` has no TanStack Query / SWR / Zustand). Session switching,
in-thread generation status and cross-column highlighting all need shared state. Today
`pendingQuestion` is lifted to the page and drilled down (`page.tsx:21`); that pattern
will not survive this feature set. Recommend a single `WorkspaceProvider` context for
the workspace route before building sessions — not a global store, just this route.

---

## 6. Phases

Ordered so that each phase ships value alone and the cheap wins land first.

**Phase A — Fix what is broken (UI only, no backend, ~½ day)**
- Bounded workspace height; only lists scroll (fixes 1.1, the actual complaint)
- Citations become real buttons with a popover (fixes 1.3)
- Sources polling stops when nothing is in flight (fixes 1.4)
- No API change, no migration, independently shippable

**Phase B — Layout re-org (UI only, ~1 day)**
- Guide moves to the right column; Studio becomes its second tab
- Responsive rules above
- Still no backend change

**Phase C — Multi-session chat (backend + UI, ~2 days)**
- `ChatSession` model, migration, endpoints, tenant scoping, tests
- Session switcher, rename, delete-with-undo
- Message windowing
- `WorkspaceProvider` lands here

**Phase D — Generation from chat (~1–2 days)**
- `/generate` slash command → inline card
- In-thread generation status card
- Assistant-proposed generation with confirmation, if still wanted after D ships

Phases A and B are pure frontend and could go out this week. C is the real feature. D
should not start before C, because a generation card without sessions has nowhere
coherent to live.

---

## 6b. Delivered

| Phase | Status | Commit |
|---|---|---|
| **A** — bounded height, real citations, polling stop | shipped, verified in a browser (40 messages / 4620px scroll inside a 502px window, page does not scroll) | `843298b` |
| **B** — guide right, Studio as tab 2, responsive | shipped, verified at 1440 / 1100 / mobile | `843298b` |
| **C** — multi-session chat | backend `3890b0f` (migration verified against a seeded pre-0007 database, upgrade + downgrade); frontend `186e14c` | `3890b0f`, `186e14c` |
| **D** — `/generate` command + confirmation card | shipped; three tests pin that nothing billable fires without a deliberate confirmation | `186e14c` |

Not verified in a browser: Phase C/D, because the Docker daemon stopped after a host
resource exhaustion. Typecheck, lint and 80 frontend + 222 backend tests are green.

## 7. Open items carried in

- `POST /projects/{id}/guide` returned **422** in production logs on 2026-07-31. Not
  investigated yet. Independent of this plan but it lives in the panel being moved.
- The six dead sources in the old "Onboarding" project are still `failed` and
  unrecoverable; delete via UI.
- Docling tech debt: installed into `/app/.venv`, which is not on a volume, so any
  `--force-recreate` of `open-notebook` breaks ingestion again.
