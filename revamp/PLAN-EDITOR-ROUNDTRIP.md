# Plan — Editing in the Presenton studio, with edits that persist

**Goal, as stated:** *"edit using the Presenton editor studio, the files and the template
adjustable like SlideShare, and when it's saved, it's stored."*

This plan takes that apart into what it actually requires, separates what already works
from what nobody has built, and names the one gap that will otherwise bite quietly.

Written 2026-07-29. Anything marked **UNVERIFIED** has not been executed and should be
confirmed before being relied on.

---

## What the goal decomposes into

| # | Capability | Editing works? | Edits persist? | NoteAI sees them? |
|---|---|---|---|---|
| 1 | Adjust a **template's** layouts | Native to Presenton | Native | ⚠️ only the reference |
| 2 | Adjust a **generated deck's** slides | Native to Presenton | Native (autosave) | ❌ **no** |
| 3 | Download the deck **as edited** | — | — | ❌ **no — this is the gap** |

Items 1 and 2 are largely Presenton features that need correct wiring. **Item 3 does not
exist and is the real work.**

---

## The gap, stated plainly

Today the deck bytes are produced **once**, during generation, and stored in MinIO:

```
generate → engine renders → NoteAI downloads the file → MinIO
```

If a user then edits that deck in the Presenton studio, Presenton updates **its own**
copy. NoteAI's stored PPTX is untouched.

So:

- The **editor** shows the edited deck ✓
- **Download** from NoteAI returns the **pre-edit** file ✗

That is a silent wrong answer — the worst failure shape in this codebase, and the class
of defect this whole programme has been unwinding. A user edits, saves, downloads, and
gets their old slides with no error anywhere.

**"When it's saved, it's stored" is only true inside Presenton.** Making it true for
NoteAI is `E-2`.

---

## Where the state actually lives

From the container logs: `Context impl SQLiteImpl`. Presenton persists to **SQLite inside
the `presenton_data` volume** (`/app_data`) — 17MB in the last backup.

That means every template layout and every deck edit lives in one SQLite file in one
Docker volume. It is covered by `revamp/scripts/phase-0-vps-recover.sh`, which is why
that backup mattered. It has no migration path and no export.

---

## E-0 — Unblock registration *(prerequisite, in flight)*

Nothing below is reachable until an engine template exists.

| Task | State |
|---|---|
| Two-step registration sends what the engine declares required | **done** (T-1.3) |
| `basePath: '/editor'` so routing matches the mount | **done** on the fork |
| Repair path for templates registered through the broken request | **done** (`/reregister`) |
| **A template actually reaching `registration_status: registered` on the live stack** | **OPEN** |

**Gate E-0:** one template shows `registered`, a non-null `preview_url`, and its preview
renders the uploaded deck's layouts rather than stock.

---

## E-1 — Template editing round-trip

**What exists:** Presenton serves `/template-preview` and `/custom-template`, and exposes
`PATCH /api/v1/ppt/templates/{template_id}`. Layout edits save to its SQLite.

**What is missing:** NoteAI holds `presenton_template_ref` and nothing else. It cannot tell
whether the engine template has been edited since registration, so a NoteAI `Template`
row and the engine's layouts can silently diverge.

### Tasks

- **E-1.1** Confirm the editor writes through. Open `/editor/template-preview?id=<ref>`,
  change a layout, reload. **UNVERIFIED** — assumed from the presence of
  `useAutoSave.tsx` and `autoSaveDiff.ts` in the engine source, not observed.
- **E-1.2** Record engine-side revision on the NoteAI row — `engine_revised_at`, set when
  a preview is opened and refreshed on demand. Enough to show *"layouts edited in the
  studio"* in the UI so the divergence is visible rather than assumed away.
- **E-1.3** Decide the versioning rule and write it down. A NoteAI `Template` version is
  immutable once used by a `Generation`. An engine-side layout edit changes rendering
  **without** creating a NoteAI version — so a pinned "v1" can render differently over
  time. Either accept and document that, or bump the version on detected engine edits.
  **This is a governance decision, not a code one.**

**Gate E-1:** a layout edited in the studio survives reload, and the NoteAI templates page
shows that the template was edited engine-side.

---

## E-2 — Deck editing round-trip *(the real work)*

**What exists:** `editor_url` opens the correct deck (T-1.2). Presenton autosaves edits
to its own store.

**What is missing:** any path from an edited deck back to a downloadable artifact.

### Tasks

- **E-2.1 — Establish the re-export contract.** Determine how a *stored* presentation is
  exported to PPTX/PDF after editing. Candidates seen in the engine's router table:
  `POST /presentation/export`, `POST /presentation/edit`, the `/api/export-presentation`
  Next.js route, or re-invoking generate with the existing `presentation_id`.
  **Read the engine source before writing any of it** — the last three contracts in this
  programme were all different from what the prompts assumed.

- **E-2.2 — Add a refresh action.** `POST /generations/{id}/refresh`: re-export from the
  engine, overwrite the MinIO artifact, update `pptx_uri` / `pdf_uri`. The stored deck
  becomes the edited deck.

- **E-2.3 — Make staleness visible, do not hide it.** Add `artifact_stale: bool` to
  `GenerationResponse`, set when the engine reports a later modification than the stored
  artifact. The download button warns and offers refresh.
  > A silent stale download is exactly the failure this codebase keeps producing. If
  > staleness cannot be *detected*, say so and warn unconditionally after any editor
  > visit — never assume fresh.

- **E-2.4 — Decide refresh timing.** Options: on download (slow but always correct), on
  editor close (racy), or explicit button (predictable). **Recommend explicit**, with the
  stale warning making it obvious when to press.

**Gate E-2:** edit a deck in the studio → download from NoteAI → **the downloaded file
contains the edit.** That is the user-visible definition of *"when it's saved, it's stored."*

---

## E-3 — Durability of engine-side state

Every template layout and every deck edit lives in one SQLite file in one Docker volume.
Once users are editing there, that volume holds work product they cannot recreate.

- **E-3.1** Scheduled `presenton_data` backup, off-host, checksummed. The recovery script
  already does this once; it needs to be routine, not manual.
- **E-3.2** Verify a restore actually works. An unverified backup is not a backup.
- **E-3.3** Decide the system of record. NoteAI owns Postgres; Presenton owns its SQLite.
  Today the deck exists in both, and after E-2 they can disagree. Write down which wins.

**Gate E-3:** a restore from backup has been performed and the stack came back with
templates and decks intact.

---

## Order, and why

```
E-0  →  E-1.1  →  E-2.1  →  E-2.2/E-2.3  →  E-1.2/E-1.3  →  E-3
```

`E-2.1` gates everything valuable, and it is **research, not coding** — the same "read the
engine, don't assume" step that produced the last three fixes. Do it before estimating.

`E-3` looks like infrastructure and is easy to defer. It should not be: the moment users
edit decks in the studio, that volume holds work they cannot reproduce, and it currently
has one manual backup.

---

## What is honestly unknown

| Question | Status |
|---|---|
| Does the studio persist deck edits across reload? | **UNVERIFIED** — inferred from autosave modules |
| How is a stored presentation re-exported? | **UNKNOWN** — must be read from the engine |
| Can NoteAI detect that a deck was edited? | **UNKNOWN** — depends on whether the engine exposes a modified timestamp |
| Does editing a template retro-change decks already generated from it? | **UNKNOWN**, and important for E-1.3 |

The last one matters more than it looks: if layouts are read at render time, editing a
template silently changes the appearance of decks a user already approved.
