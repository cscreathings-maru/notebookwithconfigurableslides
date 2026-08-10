# Assessment — Template Management

Why every uploaded template shows **"⚠️ Tema bawaan"**, and what template management should
look like once that's fixed.

Written 2026-08-06, prompted by the Templat page showing both `Template Presentasi BRI` and
`Template Presentasi BRI v.2` with the fallback badge despite both having an uploaded `.pptx`.

**Evidence basis:** the deployed engine is `presenton/presenton` @ `v0.9.3-beta` plus two
config-only commits (confirmed on the VPS 2026-08-05: `82555808` basePath, `41119096`
assetPrefix, on top of tag `v0.9.3-beta`). Findings below were read from that tag's source on
GitHub, then **confirmed against the running engine on 2026-08-06** — every prediction held.
See [`PLAN-TEMPLATE-MANAGEMENT.md`](./PLAN-TEMPLATE-MANAGEMENT.md) §0 for the observed output;
the `UNVERIFIED` markers below are retained as a record of what was inference at the time of
writing, and each is resolved there.

> **Verdict: confirmed.** `404` on the plural path, `422` on the singular one. Both defects
> real. Decisions locked and the fix sequenced as `TM-0`–`TM-6` in the plan.

---

## 1. The immediate answer: two stacked defects, both fatal

`registration_status = fallback` means `register_template()` took a failure branch and
returned the stock theme ref. It does that for four different reasons that all look
identical in the UI. For your two templates, the cause is almost certainly the first below —
and the second would still bite immediately after it's fixed.

### Defect A — the URL is wrong. Every registration 404s.

| | Path |
|---|---|
| What `engines/presenton.py` calls | `/api/v1/ppt/**templates**/fonts-upload-and-slides-preview` |
| What the engine actually serves | `/api/v1/ppt/**template**/fonts-upload-and-slides-preview` |

Plural vs. singular. The engine's `TEMPLATE_ROUTER` declares `prefix="/template"`, mounted
under the main router's `prefix="/api/v1/ppt"`. Same mismatch on the second call
(`/templates/init` vs `/template/init`).

A 404 is `>= 400`, so both call sites take their `TemplateRegistration.fallen_back(...)`
branch and the row is written with the stock theme ref. `engines/presenton.py:150-158`
and `:178-184`.

**This is the same defect class T-1.3 already fixed once** — that time the request *body* was
wrong (422 → fallback), now the *URL* is wrong (404 → fallback). The fallback machinery
worked exactly as designed both times: it recorded the failure rather than hiding it. What it
could not do is make anyone read the recorded reason.

> **You can confirm this yourself in ten seconds:** hover the "⚠️ Tema bawaan" badge. It
> carries the stored `registration_error` as its `title` (`RegistrationBadge.tsx:29`). If it
> says `preview step returned 404`, Defect A is confirmed outright.

### Defect B — `/init` alone produces an unusable template

Fixing the URL is necessary but **not sufficient**. From the engine's own `template.py`:

- `POST /template/init` validates the PPTX, converts it to JSON layout data, stores metadata,
  fonts and slide images, and returns a template id — but the resulting template has
  **`layouts: null`**. It is a skeleton, not something that can render a deck.
- Making it renderable requires `POST /template/layouts/create` (generate `SlideLayout`
  objects from the raw PPTX slides) and typically `POST /template/generate-blocks` (merge
  similar components).
- **`POST /template/async` does all of it in one call** — prepares the source, generates every
  layout in parallel with progress tracking, merges components, persists. Returns an
  `AsyncTaskModel`, i.e. it is a job you poll, not a synchronous result.

So our current two-step (`preview` → `init`) is, even with correct URLs, the wrong shape: it
would create template rows the engine accepts but cannot render from. **UNVERIFIED:** whether
`presentation/generate` rejects a `layouts: null` template outright or silently renders stock.
Given the generate endpoint validates template existence and raises *"Template not found.
Please use a valid template"* on failure, the likely outcome is a hard 400 at generation time —
i.e. fixing only Defect A would move the failure from upload to generation, which is worse.

### The other two fallback causes, for completeness

`fallback` today also means "no PPTX was uploaded" (`without_source()`, a legitimate,
non-error case) and "engine unreachable / exception" (the `except` at `:194`). Four distinct
situations, one badge. That's a design problem in its own right — see §3.

---

## 2. What you're seeing in the picker is the filter working, not a second bug

DG-3.1 made the Studio/chat picker list only templates where
`status === "approved" && registration_status === "registered"`. Both your templates fail the
second condition, so **the picker currently offers only "Tema bawaan" and nothing else** —
which looks broken but is the filter doing its job: it refuses to offer a choice that would
silently change nothing about the output.

The alternative (listing them anyway) is what the code did *before* DG-3.1, and it's strictly
worse: you'd pick "Template Presentasi BRI", get a stock-themed deck, and have no idea why.

**So: don't loosen the filter. Fix registration.** Once §1 is fixed and the templates
re-register successfully, they appear in the picker automatically with no picker change.

---

## 3. The wider template-management assessment

Beyond the two bugs, here's the current design measured against what a template system needs.

| # | Capability | Current state | Verdict |
|---|---|---|---|
| 1 | Upload a branded `.pptx` | Works — stored in MinIO under a tenant key, `source_pptx_uri` | ✅ Sound |
| 2 | Register it with the engine | **Broken** (§1) | 🔴 Fatal |
| 3 | Know whether registration worked | Recorded and badged (`registration_status` + `registration_error`, T-1.6) | ✅ Good — this is why the failure is diagnosable at all |
| 4 | Distinguish *why* it didn't work | Four causes collapse into one `fallback` value | 🟠 Needs splitting |
| 5 | Registration progress | None. It's a synchronous call inside the upload request | 🟠 Wrong shape once `/async` is used |
| 6 | Retry a failed registration | `POST /templates/{id}/reregister` exists, re-reads the stored PPTX | ✅ Already the right repair path |
| 7 | Thumbnails for a picker | Persisted as of DG-3 — but always empty today, since registration never succeeds | ⚪ Blocked on #2 |
| 8 | Preview a template's layouts | `preview_url` → `/editor/template-preview?id=<engine ref>` | ⚠️ **UNVERIFIED** — the API router is `/template` singular; the frontend route may differ too |
| 9 | Delete a template | **None.** Engine has `DELETE /template/{id}`; NoteAI has no delete at all | 🟠 Gap |
| 10 | Detect engine-side drift | None. A template can vanish or be edited engine-side and NoteAI won't know (`TD-25`, `TD-26`) | 🟡 Gap |
| 11 | Immutable versioning + approve gate | Enforced, with `VersionInUseError` protecting in-use versions | ✅ Sound governance |
| 12 | Two orthogonal gates (`approved` **and** `registered`) | Both must hold for a template to be usable; nothing explains that to the user | 🟠 Confusing (your screenshot is exactly this: one Draf+fallback, one Disetujui+fallback, neither usable, for two different reasons) |
| 13 | `brand_tokens` (colours, fonts, logo, aspect ratio) reaching the renderer | Stored, never sent anywhere (`TD-07`) | 🔴 The configurator is decorative |

### On #13 — worth revisiting now, not later

`TD-07` has been open since the original assessment on the premise that "the uploaded PPTX
*is* the brand, so `brand_tokens` can't be wired". That premise deserves re-testing: the
engine exposes **both** a `THEME_ROUTER` and a `THEMES_ROUTER` alongside the template router,
and `TECH-DEBT.md` itself records a `POST /api/v1/ppt/themes` contract taking
`{name, description, company_name, logo, logo_url, data}`. That looks like a real path for
colour/logo branding that is independent of PPTX layout extraction. **UNVERIFIED** — worth one
investigation pass before deciding the configurator is permanently decorative.

---

## 4. What "good" looks like here

The shape I'd argue for, given what the engine actually supports:

```
Upload .pptx
    │
    ▼
Template row created immediately, registration_status = PENDING     ← returns fast
    │
    ▼
Arq job: POST /template/async  →  poll task  →  layouts generated
    │
    ├─ success → registration_status = REGISTERED, thumbnails stored
    ├─ engine rejected the deck → FAILED, with the engine's own reason
    └─ engine unreachable → FAILED, retryable via the existing reregister
    │
    ▼
Appears in the picker (approved + registered)
```

Three properties that matter, none of which hold today:

1. **Upload returns fast.** Layout generation is an LLM/parallel-processing job; holding an
   HTTP request open for it is the wrong shape, and it's why the current synchronous design
   has no progress reporting.
2. **The status distinguishes causes.** "Still working" ≠ "engine said no" ≠ "you didn't
   upload a deck". One badge for three states is how a 404 went unnoticed.
3. **Registration reuses the job infrastructure that already exists.** `JobService.commit_and_dispatch`,
   Arq, and the poll-to-terminal pattern are already proven here for ingestion and generation.
   Template registration is the third instance of the same problem and should not invent a
   fourth mechanism.

---

## 5. Decisions needed before implementation

**Q1 — `/template/async`, or `/init` + `/layouts/create` + `/generate-blocks`?**
`/async` is one call and the engine's own "do it properly" path, but it's a task to poll.
The three-step route is more calls and more failure points but each step is synchronous.
*My recommendation: `/async`*, because the polling machinery already exists here and the
three-step path would need the same job wrapper anyway once layout generation is slow.

**Q2 — Should template upload return immediately (`pending`) or keep blocking?**
Follows from Q1. If `/async`, blocking isn't really an option.
*My recommendation: return immediately, poll like sources already do.*

**Q3 — Keep the manual approve gate, or auto-approve on successful registration?**
Today a template needs `approved` **and** `registered`. Two gates, one of them (approve) a
governance decision, the other (register) a technical outcome. For a single-tenant lite
deployment the approve step may be pure friction.
*Options: keep both (governance), auto-approve on successful registration (fewer steps), or
keep both but make the UI state a single "usable / not usable yet / needs attention".*

**Q4 — Investigate `brand_tokens` → theme endpoints (`TD-07`), or park it?**
One investigation pass could determine whether the 4-section configurator can be made real.
If not, the honest move is to hide or relabel it rather than leave a form that does nothing.

**Q5 — Add delete?**
The engine supports it; NoteAI doesn't expose it. Needs a decision on what happens to
`Generation` rows that pinned that template version (the immutability rule suggests: refuse to
delete a version that's in use, same as `VersionInUseError` does for status transitions).

---

## 6. Proposed plan

Sequenced so the fatal path is fixed first and independently verifiable.

| Task | Scope | Sev | Depends on |
|---|---|---|---|
| **TM-0** | **Verify the contract against the running engine**, not against my reading of a GitHub tag. Dump the live OpenAPI paths (command in §7) and confirm: the `/template` prefix, the `/async` request shape, the task-status endpoint, and whether `/editor/template-preview` is a real frontend route | 🔴 | nothing — do this first |
| **TM-1** | Fix the registration URLs (`/templates/` → `/template/`) and switch to the complete-template call per Q1. Contract test that pins the exact paths, so a plural/singular slip fails a test instead of a deck | 🔴 | TM-0 |
| **TM-2** | Make registration an Arq job: `registration_status = pending` on upload, worker drives it to a terminal state, poll endpoint for the UI | 🟠 | TM-1 |
| **TM-3** | Split `fallback` into honest states — `pending` / `registered` / `failed` (engine rejected, with its reason) / `no_source` (no PPTX, not an error). Migration + badge copy in both locales | 🟠 | TM-2 |
| **TM-4** | Repair the existing rows: re-register the two BRI templates through the fixed path and confirm they reach `registered` with thumbnails. A bulk "re-register all failed" action if there turn out to be many | 🟠 | TM-1 |
| **TM-5** | Template deletion + engine-drift verification (`GET /template/{id}` to confirm it still exists), gated by the in-use rule per Q5 | 🟡 | Q5 |
| **TM-6** | Reconcile the two status axes into one user-facing "usable" state per Q3 | 🟡 | Q3 |
| **TM-7** | `brand_tokens` investigation pass per Q4 — is `POST /api/v1/ppt/themes` a real path to colour/logo branding? Decide, then either wire it or relabel the configurator honestly | 🟠 | Q4 |

TM-0 → TM-1 → TM-4 is the critical path to "my uploaded template actually works". Everything
else is improvement on top.

---

## 7. Verification commands (run on the VPS)

**7.1 — What does the badge actually say?** Fastest confirmation of Defect A. Hover the
"⚠️ Tema bawaan" badge in the UI, or read it from the API:

```bash
cd /var/www/notebookfinal
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name, version, registration_status, registration_error FROM template ORDER BY created_at;"'
```

**7.2 — TM-0: the authoritative contract, from your engine, not from GitHub.**

```bash
cd /var/www/notebookfinal
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T orchestrator python -c "
import base64, json, os, urllib.request
u = os.environ['PRESENTON_AUTH_USERNAME']; p = os.environ['PRESENTON_AUTH_PASSWORD']
req = urllib.request.Request('http://presenton:80/openapi.json')
req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{u}:{p}'.encode()).decode())
spec = json.load(urllib.request.urlopen(req))
for path in sorted(spec['paths']):
    if 'template' in path.lower() or 'theme' in path.lower() or 'task' in path.lower():
        print(sorted(spec['paths'][path].keys()), path)
"
```

That prints every template/theme/task route the *deployed* engine serves, with its methods —
which settles the `/template` vs `/templates` question, reveals the task-status endpoint for
`/async`, and shows whether the theme endpoints exist for `TD-07`.

**7.3 — Confirm the 404 directly**, if you want it unambiguous:

```bash
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T orchestrator python -c "
import base64, os, urllib.request, urllib.error
u = os.environ['PRESENTON_AUTH_USERNAME']; p = os.environ['PRESENTON_AUTH_PASSWORD']
auth = 'Basic ' + base64.b64encode(f'{u}:{p}'.encode()).decode()
for path in ['/api/v1/ppt/templates/init', '/api/v1/ppt/template/init']:
    req = urllib.request.Request('http://presenton:80' + path, data=b'{}', method='POST')
    req.add_header('Authorization', auth); req.add_header('Content-Type', 'application/json')
    try:
        r = urllib.request.urlopen(req); print(r.status, path)
    except urllib.error.HTTPError as e:
        print(e.code, path)
"
```

Expect `404` for the plural path and `422` for the singular one — a 422 there means the route
*exists* and merely rejected the empty body, which is exactly the proof that the path is right
and ours is wrong.
