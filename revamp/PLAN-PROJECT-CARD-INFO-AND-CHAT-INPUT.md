# Project card truncation + chat input auto-send — assessment & plan

Status: **assessed, decisions taken, NOT started.** Written 2026-08-04 from two reports
against the deployed stack.

**Decisions (product owner, 2026-08-04):**

| Question | Decision |
|---|---|
| Enter key | **Claude-style** — Enter sends, Shift+Enter inserts a newline (with an `isComposing` guard for IME) |
| Card info | **Full name + more detail** — last updated and source count, not just the name. Requires expanding `ProjectResponse` |
| Build now? | **No — plan only.** Nothing below is implemented |

§"Confirm before I build" is retained only as the reasoning that led here.

---

## 1. Project name is truncated with no way to read it in full

`projects/page.tsx:127`:

```tsx
<h2 className="... line-clamp-1">{p.name}</h2>
```

`line-clamp-1` hard-truncates to one line with no `title` attribute and no other
affordance — "Onboarding BRImerchant" becomes "Onboarding BRI…" with the rest gone,
exactly as reported. There's a second constraint worth knowing before scoping a fix:
`Project` genuinely carries almost nothing else. The API type is:

```ts
export interface Project {
  id: string;
  name: string;
  created_at: string;
}
```

`ProjectResponse` on the backend matches — `id`, `name`, `created_at`. So "details
information" can mean two different things, and they cost differently:

- **Just the full name**, untruncated — a frontend-only fix, done in one component.
- **Richer detail** (last updated, source count, who created it) — needs the backend
  response expanded first, since none of that is returned today.

### Recommendation

A small info affordance next to the name, not a native `title` tooltip. This session
already established why for citations: hover-only tooltips are invisible on touch and
unreachable by keyboard, and this codebase's own citation fix ([ChatPanel.tsx](../frontend/src/components/project/ChatPanel.tsx))
replaced exactly that pattern for that reason. The same logic applies here — smaller
stakes, same principle. A small "ⓘ" button opens an inline popover with the full name;
click/keyboard to open, click-outside or Escape to close, matching the disclosure
pattern already in the chat citations.

**Decided: full name + more detail.** Concretely, that means expanding
`ProjectResponse` ([schemas/ingestion.py:21](../backend/src/schemas/ingestion.py:21))
with two fields the model or an adjacent table already has:

- `updated_at` — trivial. `Project` already carries `UpdatedAtMixin`
  ([models/project.py:13](../backend/src/models/project.py:13)); `_to_response`
  ([api/projects.py:24](../backend/src/api/projects.py:24)) just isn't reading it yet.
- `source_count` — needs a query, not just a field read. `list_projects` returns
  `list[ProjectResponse]`, so a naive per-project `COUNT(*)` on `source` is an N+1 on
  that endpoint. Do it as one `GROUP BY project_id` query joined against the project
  list, the same shape as `count_in_session` in `chat/repository.py`, not a query
  inside a loop.

`created_by` (an author name) was considered and left out: it needs a join to
`user_account` for a value the report didn't ask for. Add it later if wanted — not
now, per YAGNI.

Frontend: the info affordance opens a popover showing name (untruncated), created
date (already fetched, just currently the only thing shown), updated date, and
source count.

---

## 2. Chat input sends on Enter, which breaks multi-line prompts

`ChatPanel.tsx` uses a single-line `<input type="text">` inside a `<form>`. Two things
compound:

1. **An `<input>` cannot hold a newline at all.** There's no "accidentally sending
   early" to prevent — the field is physically incapable of multi-line text, so any
   attempt to compose a longer, structured prompt (a list, a multi-part question) hits
   Enter and the browser's native single-input-form behavior submits immediately.
2. Even switching to a multi-line field, *something* has to decide what Enter does.

Reported: *"send when it's clicked only, make it same as Claude or some other
tools."* Those two clauses describe **different** behaviors, and the fix is
different depending on which one you actually want:

| | Enter key | Shift+Enter |
|---|---|---|
| **Claude's actual behavior** | Sends | Inserts a newline |
| **"Click only" as literally stated** | Always inserts a newline | Not applicable — nothing sends except the button |

**Decided: Claude-style.** Switch to an auto-growing `<textarea>`; Enter sends,
Shift+Enter inserts a newline, and an `isComposing` guard (relevant for IME input
methods, including mid-conversion Indonesian input) stops a composition keystroke
from being misread as either.

### What this touches, either way

- `ChatPanel.tsx`: `<input>` → auto-growing `<textarea>`, capped at a reasonable max
  height (~6 lines) so a long prompt scrolls inside the box rather than pushing the
  send button off-screen.
- The `/generate` command check still runs against the field's trimmed value on
  submit — unaffected by which key triggers submission.
- `onKeyDown` needs an `isComposing` guard regardless of which Enter behavior is
  chosen, so committing an IME candidate (relevant for Indonesian input methods) is
  never misread as a send/newline keystroke.

---

## Acceptance criteria

**AC-1** A project card's full name, last-updated date, and source count are all
reachable without leaving the projects page, via a control that works by mouse,
touch, and keyboard.

**AC-2** The affordance is dismissible by Escape and by clicking outside it, matching
the citation disclosure already in this app.

**AC-3** `source_count` is computed with one grouped query for the whole list
endpoint, not one query per project.

**AC-4** The chat field accepts multi-line input before sending.

**AC-5** Enter sends; Shift+Enter inserts a newline; a mid-composition Enter (IME) is
neither.

**AC-6** `/generate` and ordinary prose routing (Phase D's safety property) are
unaffected by the input change.

---

## Implementation notes for later

- Backend: `ProjectResponse` gains `updated_at: datetime` and `source_count: int`.
  `list_projects` groups a `source` count by `project_id` in one query and merges it
  into the response list; `get_project` (single) can do a plain `COUNT(*)`.
- Frontend: a small `ProjectInfoPopover` (or similar), reusing the citation
  disclosure's open/close/Escape/outside-click behavior rather than inventing a new
  pattern.
- Frontend: `ChatPanel`'s `<input>` becomes an auto-growing `<textarea>` (~6-line cap);
  `onKeyDown` handles Enter/Shift+Enter/`isComposing`; the existing `/generate`
  detection and `onSubmit` logic are reused, not rewritten.
- Both are additive and independent — either can be built and shipped without the
  other.
