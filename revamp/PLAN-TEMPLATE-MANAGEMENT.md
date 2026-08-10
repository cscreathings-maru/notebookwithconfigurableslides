# Plan — Template Management

Implements the fixes and redesign from
[`ASSESSMENT-TEMPLATE-MANAGEMENT.md`](./ASSESSMENT-TEMPLATE-MANAGEMENT.md).
Task ids `TM-N`, same conventions as `PLAN-DECK-GENERATION-REVAMP.md`
(Evidence / Acceptance / Out-of-scope, `🔴/🟠/🟡` severity, commit per task).

**Status: ready to implement.** Root cause confirmed against the live engine 2026-08-06,
decisions locked with the product owner the same day.

---

## 0. What the VPS confirmed

Every prediction in the assessment held. This section replaces the assessment's
**UNVERIFIED** markers with observed fact.

### 0.1 Defect A — proven outright

```
404 /api/v1/ppt/templates/init      ← what our code calls (plural)
422 /api/v1/ppt/template/init       ← the real route (singular)
```

A `422` on the singular path is the proof: the route **exists** and merely rejected an empty
body. The plural path does not exist at all.

### 0.2 The stored errors, and why the two templates differ

```
Template Presentasi BRI      | fallback | EngineError: Engine 'presenton' request failed.
Template Presentasi BRI v.2  | fallback | preview step returned 404: {"detail":"Not Found"}
```

`v.2` is Defect A verbatim. The first one is an **older, different** failure — the generic
`EngineError` from `EngineClient.request()` itself, i.e. the engine was unreachable at the
time, not that it answered 404. That is consistent with the historical
`PRESENTON_URL=deck.umarsyukri.com` (no scheme) misconfiguration recorded in
[`PLAN-OPEN-NOTEBOOK.md`](./PLAN-OPEN-NOTEBOOK.md) §F4. Both are fixed by `TM-1` + a
re-register; neither needs separate treatment.

Worth noting: **the error strings did their job.** T-1.6's insistence on recording the
engine's own reason is the only thing that made this a ten-minute diagnosis instead of a
guess.

### 0.3 The real API surface (from the deployed engine's `openapi.json`)

| Route | Methods | Use |
|---|---|---|
| `/api/v1/ppt/template/fonts-upload-and-slides-preview` | POST | Step 1 — multipart PPTX upload → `{pptx_url, slide_image_urls, fonts}` |
| `/api/v1/ppt/template/async` | POST | **Step 2 — the complete-template call (Q1).** Returns an async task |
| `/api/v1/async-tasks/status/{id}` | GET | **Poll here.** Note: *not* under `/ppt` |
| `/api/v1/async-tasks` | GET | List tasks |
| `/api/v1/ppt/template/{template_id}` | GET, PATCH, **DELETE** | Fetch / update / **delete (Q5 — confirmed available)** |
| `/api/v1/ppt/template/all` | GET | List engine templates (`default` filter) — for drift detection, not the picker |
| `/api/v1/ppt/template/init` | POST | The skeleton-only path. **Not used** — superseded by `/async` |
| `/api/v1/ppt/template/layouts/create`, `/layouts/generate`, `/generate-blocks` | POST | The manual three-step route `/async` replaces |
| `/api/v1/ppt/themes/create`, `/themes/all`, `/themes/default`, `/themes/update/{id}`, `/themes/delete/{id}`, `/theme/generate` | various | **The theme API exists.** See §5 — changes `TD-07`'s status |

**One thing to keep in mind:** `/api/v1/async-tasks/...` sits outside `/api/v1/ppt`, so it is
*not* in the Traefik allowlist for the `presenton` router. That is fine — the orchestrator
calls the engine directly on `http://presenton:80` and never through Traefik. It only matters
if a browser ever needs to poll a task directly, which this plan does not do (polling happens
in the worker).

---

## 1. Locked decisions

| # | Question | Decision |
|---|---|---|
| Q1 | `/async` vs. the three-step route | **`/async`** — one call, the engine's own complete path |
| Q2 | Blocking upload vs. return-and-poll | **Return immediately**, poll like sources already do |
| Q3 | Manual approve gate | **Auto-approve** on successful registration. No approval step |
| Q4 | `brand_tokens` / the 4-section configurator | **Hide it for now.** Not deleted, not wired — see §5 |
| Q5 | Delete support | **Yes**, add it |

---

## 2. Target flow

```
POST /api/v1/templates  (multipart: name, file)
    │
    ├─ store PPTX in MinIO
    ├─ Template row: registration_status = PENDING, status = draft
    ├─ JobService.commit_and_dispatch(register_template job)
    └─ 202 immediately  ────────────────────────────────►  UI polls, shows "Mendaftarkan…"
                                                                    │
    Worker (register_template)                                      │
    ├─ POST /template/fonts-upload-and-slides-preview (multipart)   │
    │      → {pptx_url, slide_image_urls, fonts}                    │
    ├─ POST /template/async {pptx_url, slide_image_urls, fonts, name}
    │      → task id                                                │
    ├─ poll GET /async-tasks/status/{id} until terminal             │
    │                                                               │
    ├─ success → registration_status = REGISTERED                   │
    │            presenton_template_ref = <engine template id>      │
    │            slide_image_urls stored (thumbnails, DG-3)         │
    │            status = APPROVED  (Q3)                     ───────┘
    │                                                        appears in the picker
    ├─ engine rejected → FAILED + the engine's own reason
    └─ unreachable/timeout → raise, so Arq retries (same discipline as ingest_source)
```

---

## 3. Tasks

### TM-0 — Pin the `/async` + task-status contract before writing the client 🔴

**Why this is a task and not an assumption.** This entire defect exists because a client was
written against a guessed path. The `/async` request body and the task-status response shape
are the two things this plan still infers rather than knows.

Run on the VPS, paste the output back:

```bash
cd /var/www/notebookfinal
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T orchestrator python -c "
import base64, json, os, urllib.request
u = os.environ['PRESENTON_AUTH_USERNAME']; p = os.environ['PRESENTON_AUTH_PASSWORD']
req = urllib.request.Request('http://presenton:80/openapi.json')
req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{u}:{p}'.encode()).decode())
spec = json.load(urllib.request.urlopen(req))

def show(name):
    s = spec['components']['schemas'].get(name)
    print('===', name, '===')
    print(json.dumps(s, indent=2)[:1800] if s else '(absent)')

# request body of /template/async and the task-status response
for path, method in [('/api/v1/ppt/template/async','post'),
                     ('/api/v1/async-tasks/status/{id}','get')]:
    op = spec['paths'][path][method]
    print('###', method.upper(), path)
    print(json.dumps({'requestBody': op.get('requestBody'), 'responses': op.get('responses')}, indent=2)[:1500])
    print()

for n in ['CreateTemplateRequest','InitTemplateRequest','AsyncTaskModel',
          'AsyncTaskStatusResponse','FontsUploadAndSlidesPreviewResponse']:
    show(n)
"
```

**Acceptance:** the exact field names for (a) the `/async` request body, (b) the task id in
its response, (c) the task-status terminal values, and (d) where the resulting **template id**
appears on completion, are all written into `TM-1`'s implementation before code is merged.

**Mitigation if a field still surprises us:** the client keeps using the existing
`PresentonClient._first(body, *keys)` tolerance helper, which already exists precisely because
engine response shapes vary between self-hosted and cloud.

---

### TM-1 — Fix registration: correct paths, `/async`, contract tests 🔴

**Evidence.** `engines/presenton.py:144-154` (`/templates/fonts-upload-and-slides-preview`)
and `:168-177` (`/templates/init`). Both 404. Confirmed §0.1.

**Scope**
- Correct both paths to `/api/v1/ppt/template/…`.
- Replace the `init` call with `POST /api/v1/ppt/template/async` + polling
  `GET /api/v1/async-tasks/status/{id}` to a terminal state, per the shapes TM-0 pins.
- Poll bounds and interval as settings (mirror `ingest_poll_max_attempts` /
  `ingest_poll_interval_seconds`), not hard-coded.
- **A contract test that asserts the literal request paths.** This defect would have been
  caught at write time by one assertion on the URL string; the existing
  `tests/contract/test_open_notebook_contract.py` is the precedent to follow.

**Acceptance**
- A test fails if either path loses its singular `/template` form.
- Uploading a branded `.pptx` yields `registration_status = registered`, a non-`"default"`
  `presenton_template_ref`, and a non-empty `slide_image_urls`.
- A deck generated with that template renders with its branding (the real end-to-end proof —
  requires a live engine, so it is a manual step in the report, not an automated test).

**Out of scope:** `/init`, `/layouts/create`, `/generate-blocks` — `/async` supersedes all
three (Q1). Do not keep the old two-step as a fallback path; a silent second path is how
divergence starts.

---

### TM-2 — Registration becomes a job 🟠 *(depends: TM-1)*

**Evidence.** `registry/service.py:96-100` awaits `register_template` inline inside the
`POST /templates` request. With `/async` + polling that can take minutes — untenable in a
request, and the reason there is no progress state today.

**Scope**
- New `JobType.register_template`; worker task alongside `ingest_source` / `generate_presentation`.
- `TemplateService.create` stores the PPTX, writes the row as `pending`, and calls
  `JobService.commit_and_dispatch` — the commit-before-enqueue discipline from `T-1.4`, not a
  bare enqueue.
- `reregister` re-enqueues the same job rather than re-running inline (keeps one code path).
- Transient engine failures **raise** so Arq retries; only a definitive engine rejection
  writes `failed`. Same rule as `ingest_source`.

**Acceptance**
- `POST /templates` returns in well under a second with `registration_status = pending`.
- Killing the engine mid-registration leaves the row `pending` and the job retrying — never a
  silent `registered`.

---

### TM-3 — Split `fallback` into honest states 🟠 *(depends: TM-2)*

**Evidence.** `RegistrationStatus` has `registered | fallback | failed`, and `fallback`
currently means four different things: no PPTX uploaded, 404, engine rejected the deck, engine
unreachable. §0.2 shows two of those four sharing one badge right now.

**Scope**
- `pending` — queued or in flight (new, needed by TM-2).
- `registered` — usable.
- `failed` — the engine definitively rejected it. `registration_error` carries the engine's
  own words.
- `no_source` — no PPTX was uploaded. **Not an error**; the template simply carries no
  branding. Replaces today's `TemplateRegistration.without_source()` misuse of `fallback`.
- Retire `fallback` in the migration (map existing rows: those with a `source_pptx_uri` →
  `failed`, those without → `no_source`).
- Badge copy + colours per state, both locales. `pending` gets a spinner affordance, not a
  warning triangle.

**Acceptance:** a template that was never given a PPTX and one the engine rejected are
visually and semantically distinct.

---

### TM-4 — Auto-approve, and repair the two existing rows 🟠 *(depends: TM-1)*

**Scope**
- On successful registration the worker sets `status = approved` (Q3). The manual Approve
  button and its endpoint go away; `VersionInUseError` protection on other transitions stays.
- Re-register the two BRI templates through the fixed path and confirm both reach
  `registered` + `approved` with thumbnails.

**Acceptance:** both templates appear in the Studio/chat picker with a real thumbnail, with
no manual approve step anywhere in the flow.

**Note on the `approved` gate disappearing:** `list_templates` currently returns
`approved_only` for non-admins (`api/templates.py:101`). That stays meaningful — it now just
means "successfully registered" in practice. `isSelectableTemplate` on the frontend keeps both
conditions and needs no change.

---

### TM-5 — Delete 🟡 *(Q5)*

**Scope**
- `DELETE /api/v1/templates/{logical_id}` (admin) → deletes engine-side via
  `DELETE /api/v1/ppt/template/{ref}`, then the NoteAI rows.
- **Refuses with 409 if any `Generation` pinned that template version** — the same rule
  `VersionInUseError` already enforces for status transitions, and the reason
  `template_version` exists on `Generation` at all. Deleting it would strand provenance.
- Engine-side delete failure must not orphan the NoteAI row silently: either both go or the
  error surfaces.

**Acceptance:** deleting an unused template removes it from both sides; deleting one used by a
generation returns 409 with a message naming that constraint.

---

### TM-6 — Hide the brand-token configurator 🟠 *(Q4)*

**Evidence.** `frontend/src/app/(app)/templates/page.tsx` collects primary/secondary/accent
colours, font, logo URL, aspect ratio, header/footer text. None of it reaches the renderer
(`TD-07`) — neither mapper sends `brand_tokens`.

**Scope**
- Hide the four-section configurator. Upload becomes: name + `.pptx`, which is what actually
  determines branding.
- **Keep the `brand_tokens` column and the API field.** Not a deletion — §5 shows the theme
  API exists, so this may become real later; removing the data would make that harder.
- Keep `extract-tokens` working if it costs nothing to leave, but stop presenting extracted
  values as if they will be applied.

**Acceptance:** nothing in the templates UI claims a visual effect it does not have.

**Out of scope:** wiring `brand_tokens` to `/themes/create` — that is §5, deliberately parked.

---

## 4. Order

```
TM-0 ──► TM-1 ──┬──► TM-2 ──► TM-3
                └──► TM-4
TM-5   (independent)
TM-6   (independent, frontend-only)
```

`TM-0 → TM-1 → TM-4` is the critical path to "my uploaded template works". TM-5 and TM-6 can
run in parallel with anything.

---

## 5. `TD-07` — status change, deferred by choice not by impossibility

`TD-07` has stood since the original assessment on the reasoning that *"the uploaded PPTX **is**
the brand — `POST /templates/init` takes no colour or font parameters, so `brand_tokens` cannot
be wired"*. That reasoning was about the **template** API, and it was correct about it.

§0.3 shows a **separate theme API** exists on the deployed engine:

```
POST   /api/v1/ppt/themes/create
GET    /api/v1/ppt/themes/all
GET    /api/v1/ppt/themes/default
PATCH  /api/v1/ppt/themes/update/{theme_id}
DELETE /api/v1/ppt/themes/delete/{theme_id}
POST   /api/v1/ppt/theme/generate
```

which matches the `{name, description, company_name, logo, logo_url, data}` contract
`TECH-DEBT.md` already recorded but never acted on.

**So `TD-07` should be re-classified from "believed impossible" to "confirmed plausible,
deferred by choice" (Q4: hide for now).** Two things remain unknown and would need one
investigation pass before committing to it:

1. Whether a *theme* and a *template* compose — can a deck use an uploaded template's layouts
   **and** a theme's palette, or are they alternatives?
2. Whether `presentation/generate` accepts a theme reference at all (its `template` field is
   documented; a theme field is not).

Recorded here so the next person does not re-derive it. **Not in this plan's scope.**

---

## 6. What this plan does not touch

- The deck-generation flow (`DG-0`–`DG-5`) — unchanged. Once templates register successfully
  they flow into the existing picker with no change to it.
- `isSelectableTemplate`'s filter — correct as written, and the reason the broken templates
  were correctly withheld from the picker rather than silently rendering stock.
- `TD-24` (edited decks / download cutover), `TD-25` (engine backups), `TD-26` (engine-side
  layout edits changing a pinned version's rendering) — related to templates but separate.
  TM-5's drift concern touches `TD-26`; detection is not built here.
- §5.4 governed-vs-freeform — still parked.
