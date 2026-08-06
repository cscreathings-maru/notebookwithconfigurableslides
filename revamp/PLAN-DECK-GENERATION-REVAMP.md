# Plan — Deck Generation Workflow Revamp

Status: **plan approved for implementation planning; no code written yet.** Supersedes
[`ASSESSMENT-DECK-GENERATION-REVAMP.md`](./ASSESSMENT-DECK-GENERATION-REVAMP.md), which stays
as the record of what was found and why each decision below was made — read it for evidence
and rejected alternatives; this file is the build order.

Source brief: [`revamp - deck generations.md`](./revamp%20-%20deck%20generations.md).
Decisions locked with the product owner 2026-08-05; VPS findings confirmed same day.

---

## 0. What changed since the assessment

The assessment's §4 ("Blocker A") is **substantially resolved**, not open. VPS evidence
(§14 of the assessment):

- The engine **is** version-controlled — a real fork, `cscreathings-maru/presenton`, with the
  `basePath: '/editor'` commit already on it. `TD-01` is functionally done.
- `/editor` **routes correctly** — `curl` returns `401`, not `404`. `TD-05` is done.
- A **new, narrower** blocker replaced it: the editor's own HTTP Basic Auth (documented,
  intentional, engine-side) now gates a request that successfully reaches it. This is a small
  fix (`DG-0`), not the open-ended "vendor the engine" problem the tech debt register
  describes.

This moves "Open in Studio" from *blocked indefinitely* to *one Traefik middleware away*. The
plan below reflects that — `DG-0` is now first, not a footnote.

---

## 1. Conventions

Same as every other file in this directory (`revamp/README.md`):

| | Meaning |
|---|---|
| `DG-N.x` | Task id, stable across this plan. |
| **Evidence** | `file:line` proving the current state. Re-verify before changing — code moves. |
| **Acceptance** | Binary and observable. Not "improved." |
| **Out of scope** | Explicitly deferred; do not opportunistically fix while here. |
| 🔴 / 🟠 / 🟡 | Blocks the brief's success criteria / should fix / nice to have. |

**Rules carried over from the programme** (`revamp/README.md`, unchanged, still binding):
every fix ships with a test that fails before and passes after; the backend suite stays
green; silent fallbacks are forbidden; commit per task referencing its id.

---

## 2. Locked decisions (recap)

| # | Decision |
|---|---|
| Outline | New, ungoverned outline step — LLM decides structure per-context, not a fixed profile `section_structure`. Built for token efficiency + a confirm-before-spend step. Governed path (`OutlineService.build`) is untouched, kept for if §5.4 ever resolves toward it. |
| Templates | Admin-uploaded only. No stock gallery, no exposing Presenton's built-ins. |
| Deck settings | Tone/density/slides/language/model/export/web-search live behind an "Advanced" disclosure on the new flow, not deleted, not moved onto the template. |
| Progress | Real statuses only (`queued`/`generating`/`ready`/`failed` + a genuine "building outline" step). No fabricated stage animation. |
| Download after edit | Once a generation's studio has been opened, NoteAI stops offering its own download for it; export moves into Presenton from that point. Tracked server-side (`studio_opened_at`), not client-only — durable across reload and across users. |
| Editor URL | Keep the existing capability-URL (`editor_url`) design. No engine id in a NoteAI route. |
| Scope boundary | §5.4 (governed-vs-freeform as the *whole* product's architecture) stays parked — this plan does not reopen it, only adds a second, independent outline builder. |

---

## 3. Dependency graph

```
DG-0 ──────────────────────────────────► (unblocks DG-4's user-visible effect)
DG-1 ──► DG-2
DG-3                                       (independent)
DG-4  (buildable any time; inert until DG-0 lands)
DG-5                                       (independent, trivial)
```

`DG-1`, `DG-3`, `DG-5` can start immediately and in parallel. `DG-0` should land early because
it is small and unblocks demoing anything editor-related. `DG-2` needs `DG-1`. `DG-4` can be
built early but has no visible effect for a user until `DG-0` ships.

---

## 4. DG-0 — Let real users into the editor 🔴

The one item without which "Open in Studio" cannot be demonstrated end to end.

**Evidence.** `curl -sD - -o /dev/null https://notellm.umarsyukri.com/editor` → `401
Unauthorized`, confirmed 2026-08-05. `engines/presenton.py:2-4` documents the Basic Auth as
intentional, applying to "the web UI" as well as the API.

**Task.**
- Precompute `PRESENTON_BASIC_AUTH_B64 = base64("$PRESENTON_AUTH_USERNAME:$PRESENTON_AUTH_PASSWORD")`
  and add it to `deploy/.env.lite` (and `.env.lite.example`, redacted).
- Add a Traefik middleware on the `presenton` router only:
  ```yaml
  - "traefik.http.routers.presenton.middlewares=presenton-auth@docker"
  - "traefik.http.middlewares.presenton-auth.headers.customrequestheaders.Authorization=Basic ${PRESENTON_BASIC_AUTH_B64}"
  ```
- Nothing else changes: the container's own port stays `127.0.0.1`-bound, the credential
  still gates any direct hit to it, and API calls from `PresentonClient` already send their
  own `auth=(...)` — this only covers the browser-facing routes Traefik forwards.

**Acceptance.** `curl -sD - -o /dev/null https://notellm.umarsyukri.com/editor` returns `200`
(or a normal Next.js response, not `401`), with no credentials supplied by the client. A
manual browser visit to `/editor` shows the app, not a Basic Auth prompt.

**Out of scope.** Removing the credential entirely, or making it per-tenant — it is
engine-internal defense-in-depth, not a tenant boundary, and stays that way.

**Verification commands (re-run after deploy):**
```bash
curl -sD - -o /dev/null https://notellm.umarsyukri.com/editor
curl -s https://notellm.umarsyukri.com/editor | grep -o '/_next/[^"]*' | head -5
```

---

## 5. DG-1 — Freeform outline: builder, schema, review UI 🔴

**Evidence.** `Outline.profile_id`/`profile_version` are `NOT NULL`
(`backend/src/models/outline.py:25-26`), which is the only structural blocker to reusing this
table for a profile-less draft. `OutlineContent`/`validate_outline`
(`backend/src/outline/schema.py`, `backend/src/outline/validator.py`) are already
profile-agnostic. `OutlineService.build` requires an *approved* profile
(`backend/src/outline/service.py:50-54`), which the lite stack's `seed_lite.py` never seeds —
this is exactly why a second builder is needed rather than reusing the existing one.

### DG-1.1 — Migration

Make `Outline.profile_id` and `Outline.profile_version` nullable. Additive, no data loss;
mirrors `Generation.profile_id` already being nullable for its freeform path
(`models/generation.py:44-47`).

**Acceptance.** Migration round-trips against Postgres (per `docs/ARCHITECTURE.md` §8's
standing convention — SQLite alone is not sufficient evidence). Existing governed-path rows
are unaffected.

### DG-1.2 — `build_freeform_outline()`

New function beside `build_outline()` in `backend/src/outline/builder.py` (not a replacement —
the governed path is untouched). One LLM call proposes **both** structure and wording, unlike
the governed path's two-phase split, because there is no fixed `section_structure` to shortcut
against — this is also what keeps token spend to one call, per the stated goal.

Inputs: the same four content sources the freeform generation mapper already recognizes
(`summary`/`notebook`/`chat`/`custom`, `generation/freeform_mapper.py:_content_brief`-adjacent
pattern), grounding via the existing `on_client.search()` call, and the Advanced-disclosure
knobs (tone, density, an optional slide-count *hint*, not a contract). Output: `OutlineContent`
with `sections[]`/`talking_points[]`, count decided by the model within a soft range (e.g.
4–12), validated with the existing `validate_outline()` — no `repair_outline()` call, since
there is no fixed title list to repair onto; a draft that fails validation is regenerated.

**Acceptance.** Given source content, `build_freeform_outline()` returns a validating
`OutlineContent` with ≥1 section for at least 3 distinct real inputs of different length/topic
(a test fixture, not a demo). A test asserting the LLM call count is 1, not 2, for this path.

### DG-1.3 — API + UI

- `POST /projects/{id}/outline` accepts the request with no `profile_id` and routes to
  `build_freeform_outline()` instead of `OutlineService.build`.
- Outline review card: list sections/bullets, inline edit, "Regenerate" (calls the builder
  again), "Confirm" (proceeds to `DG-2`). Reuses `PUT /outlines/{id}` unchanged.

**Acceptance.** A user can build a draft, edit a section title, reload the page, and still see
the edit (persisted via the existing update path). No `Generation` row exists until "Confirm."

**Out of scope.** Repairing a freeform draft onto a required structure — there isn't one.
Multi-turn outline refinement via chat — this is the picker/card flow, not
`PLAN-CHAT-GENERATION.md`'s parked proposal.

---

## 6. DG-2 — Generate from a confirmed freeform outline 🔴

**Depends on DG-1.**

**Evidence.** `FreeformGenerationService.create` resolves content from exactly four
`content_source` values today (`generation/freeform_service.py:160-210`); none of them is "a
confirmed outline." The governed mapper's `_slides_markdown()` (`generation/mapper.py:23-39`)
already does the exact transform needed — one markdown block per section, bullets from
talking points — it is just currently only reachable from the profile-gated path.

**Task.** Add a fifth path to `FreeformGenerationService`: when `outline_id` is supplied and
the referenced `Outline.profile_id is None`, build `slides_markdown` from `outline.content`
using the same per-section-block logic `mapper.py:_slides_markdown` already implements
(extract or share the function — do not duplicate it), then pass through the existing
`build_freeform_request()`. `POST /projects/{id}/generations` branches on whether the
outline it's given has a profile (existing `GenerationService`) or not (this new branch) —
one more case on an endpoint `docs/ARCHITECTURE.md` §3 already flags as this codebase's
recurring failure point for exactly this kind of divergence, so the branch condition and
both destinations belong in one place, commented as such.

**Acceptance.** Confirming an outline produces a `Generation` with `outline_id` set,
`profile_id` null, and `params["slides_markdown"]` matching the confirmed sections in order.
Consistency check is skipped (`generation/worker.py:77`, unchanged — already correct for any
`profile_id is None` generation). A test that edits a section title in the outline and asserts
the edit appears in the generated `slides_markdown`, not the original LLM draft.

**Out of scope.** A third `GenerationService` class — rejected in the assessment (§12.1(b)) as
repeating the exact divergence this endpoint already has a documented failure history for.

---

## 7. DG-3 — Template picker, registered templates only 🟠

**Independent of DG-1/DG-2.**

**Evidence.** Studio's existing selector filters on `status === "approved"` only
(`frontend/src/components/project/StudioPanel.tsx:72`) — a template can be `approved` *and*
`registration_status: "fallback"` simultaneously, meaning today's list can offer a choice that
silently renders the stock theme. Thumbnails already come back from the engine
(`slide_image_urls` in `engines/presenton.py:157`) and are discarded —
`TemplateRegistration` only carries `ref`/`status`/`error` (`engines/presenton.py:36-50`).

### DG-3.1 — Filter correctly

Picker (and Studio, while touching this) lists templates where `status == approved` **and**
`registration_status == registered` — i.e., a template that will actually change the render,
not just one an admin approved.

**Acceptance.** A template with `registration_status: fallback` does not appear in the picker
even if `status: approved`. Existing `RegistrationBadge` semantics unchanged.

### DG-3.2 — Persist and serve thumbnails

Migration: add `Template.slide_image_urls: list[str]` (or store as MinIO keys if the engine's
own URLs are not durable — verify: are `slide_image_urls` engine-hosted and stable, or
presigned/expiring? **Unverified — check before choosing storage.**). Store what
`fonts-upload-and-slides-preview` returns at registration time
(`engines/presenton.py:139-157`); serve to the picker.

**Acceptance.** A newly-registered template's picker card shows a real thumbnail, not a
placeholder. Existing templates without stored thumbnails degrade to a placeholder, not an
error.

**Out of scope.** Backfilling thumbnails for templates registered before this ships — a
`reregister` (already exists, `api/templates.py:114-129`) naturally populates them; no
separate backfill job needed unless requested.

### DG-3.3 — Wire into the flow, keep the Advanced knobs

The picker sits in front of the outline card (§ assessment 12.2's revised flow). Tone,
density, slide count, language, model, export format, web search move behind "Advanced" —
same options, same defaults, collapsed by default. **Not** deleted, **not** moved onto the
template (per the locked Q4 decision).

**Acceptance.** Every control currently in `StudioPanel.tsx:163-294` is reachable from the new
flow, just not all visible by default.

---

## 8. DG-4 — Download cutover after studio is opened 🟡

**Buildable any time; user-visible only after DG-0.**

**Evidence.** Deck bytes are written once, at generation, to MinIO
(`generation/worker.py:57-73`); editing in Presenton updates only the engine's own copy.
Today `TD-24` is latent because the editor isn't reachable — this plan's whole point is to
make it the default next step, which turns the silent-stale-download defect into the common
case.

### DG-4.1 — Track "opened"

Add `Generation.studio_opened_at: datetime | None` (migration). A rejected client-only flag
would reset on reload and not hold for a second viewer on the same tenant — this needs to be
durable and shared.

Small endpoint (or a mutation on the existing generation-fetch path) the "Open in Studio"
click fires, idempotently, before navigating.

**Acceptance.** Two different sessions viewing the same `Generation` after one of them opened
the studio both see the download option gone.

### DG-4.2 — Response + UI

`_to_response` (`api/generations.py:87-105`) stops reporting `artifacts.pptx`/`artifacts.pdf`
as available once `studio_opened_at is not None`. Frontend hides the download buttons for that
generation the same way it already hides them when `editor_url` is `None`
(`StudioPanel.tsx:352`, `:365`, `:380`).

**Acceptance.** Before opening the studio: both "Open in Studio" and "Download PPTX/PDF" are
available (this preserves the brief's own stated success criterion — download either
immediately after generation *or* from the editor). After opening: only the studio's own
export remains offered from NoteAI's UI for that generation.

**Out of scope.** Re-fetching the edited file from the engine on download (rejected option (a)
in the assessment §6/Q6 — the locked decision was Option C, the simpler cutover, not
reconciliation).

---

## 9. DG-5 — Remove the two dead statuses 🟢

**Independent, trivial, do whenever convenient.**

**Evidence.** `GenerationStatus.analyzing` and `.building_outline`
(`models/generation.py:23-24`) are never assigned anywhere in `src/` — confirmed by grep, only
match is the enum declaration. Given `DG-1`/`DG-2`, outline building now genuinely happens
*before* a `Generation` row exists (its own request/response with its own spinner), so these
were never going to become real generation-internal states.

**Task.** Delete both values, backend (`models/generation.py`) and frontend
(`services/api.ts:204-211`). Migration for the Postgres enum type.

**Acceptance.** `grep -rn "analyzing\|building_outline" backend/src frontend/src` returns
nothing. No behavior change — nothing ever set these.

---

## 10. Build order

| Order | Task | Why here |
|---|---|---|
| 1 | `DG-0` | Small, deploy-only, unblocks demoing the rest of the editor-facing work |
| 2 | `DG-1` | Gates `DG-2`; no dependency on anything else |
| 2 | `DG-3` | Fully independent; run in parallel with `DG-1` |
| 2 | `DG-5` | Fully independent, trivial; fold into whichever PR is convenient |
| 3 | `DG-2` | Needs `DG-1` |
| 3 | `DG-4` | Independent, but pointless to demo before `DG-0` |

`DG-1`+`DG-3`+`DG-5` can be three parallel workstreams. `DG-2` and `DG-4` follow.

---

## 11. What this plan deliberately does not touch

- The governed path (`OutlineService.build`, `StakeholderProfile`) — untouched, available if
  §5.4 ever resolves toward it. **§5.4 remains parked; you asked to be reminded — this is that
  reminder surfacing again, not a request to decide it now.**
- `check_consistency` / the consistency gate — freeform-outline generations have no
  `profile_id`, so the existing skip (`generation/worker.py:77`) already applies with no new
  code.
- Studio's existing form — not deleted, its controls relocate behind Advanced (`DG-3.3`).
- `brand_tokens` reaching the renderer (`TD-07`) — separate, larger piece of tech debt, not
  in scope of this brief and not blocking it (template *selection* works without it; template
  *fidelity beyond the uploaded PPTX* is a different, already-tracked problem).
- Multi-tenant scoping of Open Notebook's shared search index (`TD-23`) — orthogonal.

---

## 12. Residual open items (non-blocking, track separately)

From the VPS check (assessment §14.4) — none of these block `DG-0`–`DG-5`, but should not be
forgotten:

- Confirm `presenton-custom:noteai/deployed` is actually pushed to
  `github.com/cscreathings-maru/presenton` (formally closes `TD-01`'s bookkeeping, not its
  substance).
- Clarify what `/var/www/notebookfinal/presenton` (no `-custom`) is for; if it's the `TD-02`
  staging tree, document it as such.
- Add `presenton/` and `presenton-custom/` as top-level `.gitignore` entries in this repo —
  they show as untracked, not ignored, which is the exact accidental-vendor hazard `TD-04`
  already found once (`a535bc0`).
- `TD-03` (off-host backup) is still not off-host. Unrelated to this plan; flagging because it
  sits under everything this plan builds on top of.
