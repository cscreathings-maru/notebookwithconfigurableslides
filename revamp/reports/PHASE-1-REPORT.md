# Phase 1 Test Report — Critical Fixes: Make the Core Loop Work

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `1 — Critical Fixes` |
| Date started | `2026-07-28` |
| Date completed | **not complete — see §2** |
| Executed by | Claude Opus 5 (local workstation session) |
| Commit range | `37c9e27..c4b9b5d` (3 commits) |
| Branch | `revamp/phase-1` |
| Environment | `local` — macOS workstation, Docker Desktop 27.3.1 |
| Presenton source revision | **UNKNOWN — source still not reachable from this environment** |

---

## 2. Gate summary

| # | Exit gate criterion | Verdict | Evidence |
|---|---|---|---|
| G1 | `/editor` serves Presenton at 200 with zero asset 404s | **BLOCKED** | §5 M1 |
| G2 | "🎨 Editor" opens the correct deck | **BLOCKED** | §5 M1 |
| G3 | **Brand colours visibly applied to a generated deck** | **BLOCKED** | §5 M1 |
| G4 | No Arq enqueue precedes its DB commit; missing job logs an error and retries | **PASS** | §4.1 |
| G5 | PPTX and PDF download successfully in a real browser | **PARTIAL** | §4.1, §5 M4 |
| G6 | Template registration failure visible in API and UI | **PASS** | §4.1, §5 M3 |
| G7 | Backend suite green, coverage ≥ 83%; frontend typecheck clean | **PASS** | §4.1, §4.2 |
| G8 | Full 9-step manual journey passes, with screenshots | **BLOCKED** | §5 M1 |

**Overall gate: `FAIL`** — 3 PASS, 1 PARTIAL, 4 BLOCKED.

> **G3 is the phase's stated reason for existing** (`PHASE-1-PROMPT.md`: *"If every other gate passes and G3 fails, the phase has not delivered its purpose."*). It is blocked. Phase 1 is **not** complete and Phase 2 is **not** authorised.

### Why blocked

The Phase 0 blocker is unchanged. **Phase 1 was started anyway, at the user's explicit direction**, after confirming that three of six tasks need no Presenton source. That deviation is recorded as D1.

| Precondition | State | Check |
|---|---|---|
| Presenton source vendored | **absent** | `git ls-files \| grep -c '^presenton/'` → `0` |
| `../presenton-custom` present | **absent** | `ls` → `No such file or directory` |
| Docker daemon | **up** | `docker info` → server 27.3.1 (fixed this session) |
| Host disk | **healthy** | 18Gi free (was 585Mi) |

T-1.1, T-1.2, T-1.3 each require reading or editing files that do not exist here:

| Task | Required artefact |
|---|---|
| T-1.1 | `presenton/servers/nextjs/next.config.mjs` — `basePath` must be baked at build time |
| T-1.2 | Presenton's editor route file — the prompt explicitly forbids guessing between `/presentation/{id}`, `/presentation?id={id}`, `/editor/{id}` |
| T-1.3 | Presenton's generate endpoint — the theming contract is undocumented and must be read from source |

**No attempt was made to guess any of the three.** Guessing T-1.2's route shape is precisely what produced the uncommitted change Phase 0 inherited (`1e99a1e`), which flipped between two forms without establishing which was real. Guessing T-1.3's contract would produce a mapper that passes its own contract test and changes nothing in the rendered deck — a false `PASS` on the one gate that matters.

---

## 3. Task results

| Task | Title | Severity | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `T-1.1` | Serve Presenton at `/editor` | 🔴 | **BLOCKED** | — | §5 M1 |
| `T-1.2` | Fix the editor deep-link identifier | 🔴 | **BLOCKED** | — | §5 M1 |
| `T-1.3` | Wire `brand_tokens` to the renderer | 🔴 | **BLOCKED** | — | §5 M1 |
| `T-1.4` | Eliminate the enqueue-before-commit race | 🟠 | **DONE** | `test_job_dispatch_ordering.py` (4) | `513ece6` |
| `T-1.5` | Make deck downloads reachable | 🟠 | **DONE (unwalked)** | `test_generation.py::test_full_pipeline_to_ready_and_download` | `39e0645` |
| `T-1.6` | Surface template registration failure | 🟠 | **DONE** | `test_template_registration_status.py` (5) | `c4b9b5d` |

### T-1.4 — DONE (detail)

`JobService.commit_and_dispatch()` commits the transaction, then enqueues. Applied at all three call sites: `generation/service.py`, `generation/freeform_service.py`, `ingestion/service.py`.

The worker's silent miss is now loud: `_require_job()` logs at `error` and raises `JobRowMissing`, so Arq retries. `_load_job()` is retained for `_finish_job`, where an absent row is not itself the failure.

Two tests form a matched pair — one asserts `commit_and_dispatch` makes the row visible at enqueue time, the other asserts bare `dispatch()` still does not. The second is the regression guard: if it ever starts passing, the race is no longer reproducible and the first test has stopped proving anything.

### T-1.5 — DONE, but not walked in a browser

Option B, as recommended. `GET /generations/{id}/download` streams bytes with `Content-Disposition: attachment`. Ingestion presigns are untouched.

**A second defect surfaced during implementation and is not in the phase prompt.** The endpoint is bearer-authenticated, and the token lives in JS (`services/session.ts`), so `window.open(url)` sends no `Authorization` header — Option B would have 401'd on every download had only the backend been changed. The client now fetches a `Blob` and saves it via an object URL.

`tsc` then found **two further call sites** the prompt's evidence did not list: `GeneratePanel.tsx:64` and `VersionHistoryPanel.tsx:67`. The prompt cited only `StudioPanel.tsx:141`. `VersionHistoryPanel` previews rather than downloads, so its object URL is revoked on replace and on unmount.

Marked **unwalked** rather than PASS: no browser has clicked the button. The bytes, headers, and status are asserted by test; end-to-end browser behaviour is not.

### T-1.6 — DONE (detail)

`RegistrationStatus` (`registered | fallback | failed`) + `registration_error` on `Template`, surfaced in `TemplateResponse` and rendered as a warning badge. `register_template` returns a `TemplateRegistration` carrying the reason; the redundant outer `try/except` in `registry/service.py` is deleted. One fallback, one place.

Migration `0006` verified `upgrade → downgrade → upgrade` against **Postgres 16**, with the resulting column and enum inspected directly (§5 M3).

### Deviations

**D1 — Phase 1 started against a `FAIL` Phase 0 gate.**
`PHASE-1-PROMPT.md` requires *"Phase 0 gate `PASS`"*. It is `FAIL`. The user directed execution after being shown the blocker; the three tasks with no Presenton dependency were executed and the three with one were left untouched. **This does not make Phase 1 complete** — it front-loads the reachable work so that only Presenton-dependent tasks remain when the source lands.

**D2 — `DownloadResponse` schema deleted.**
Nothing constructs it once `/download` streams. Leaving a response model that no endpoint returns would misdescribe the API. Removal is within T-1.5's blast radius, not scope creep.

**D3 — Migration revision id shortened after a real failure.**
`0006_template_registration_status` is 33 characters; `alembic_version.version_num` is `varchar(32)`. The first `upgrade head` failed with `StringDataRightTruncation`. Renamed to `0006_template_registration` (26). **This would have passed a SQLite-only check and failed on the production VPS** — see F1.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Baseline (`37c9e27`) | This phase (`c4b9b5d`) | Delta |
|---|---|---|---|
| Passed | 61 | **70** | **+9** |
| Failed | 0 | 0 | 0 |
| Skipped | 1 | 1 | 0 |
| Coverage (total) | 83% | **85%** | **+2** |
| Duration | 2.24s | 2.23s | −0.01s |

```
--------------------------------------------------------
TOTAL                                 3067    475    85%
70 passed, 1 skipped, 89 warnings in 2.23s
```

**Verification block:**

| # | Check | Result |
|---|---|---|
| V1 | Backend suite | `70 passed, 1 skipped` |
| V2 | Coverage ≥ 83% | `85%` |
| V3 | `ruff check src tests` | `10 errors` — **identical count at `HEAD`**, all pre-existing (§7 F3) |
| V4 | `git ls-files \| grep -c '^presenton/'` | `0` — G1/G2/G3 still correctly blocked |
| V5 | Migration `upgrade → downgrade → upgrade` on Postgres 16 | `PASS` |
| V6 | `git status --short` | empty |

### 4.2 Frontend

```bash
cd frontend && npm run typecheck && npm run lint
```

| Check | Result |
|---|---|
| `tsc --noEmit` | **clean** |
| `next lint` | **No ESLint warnings or errors** |
| Unit tests | **N/A — no frontend test tier exists (T-2.5)** |

The T-1.2 unit test the prompt authorises as an exception is **not written** — it tests `editor_url`, which T-1.2 would introduce, and T-1.2 is blocked.

`tsc` did real work here: it caught the two unlisted download call sites (§3 T-1.5).

### 4.3 End-to-end

`N/A — introduced in Phase 2 (T-2.6).`

### 4.4 Per-task test evidence

| Task | Test | Before | After |
|---|---|---|---|
| `T-1.4` | `commit_and_dispatch` → row visible at enqueue | `FAIL` (method absent) | `PASS` |
| `T-1.4` | bare `dispatch()` → row **not** visible | — | `PASS` (guard holds) |
| `T-1.4` | missing row raises `JobRowMissing` | `FAIL` — returned `None` silently | `PASS` |
| `T-1.4` | cross-tenant row raises | `FAIL` — returned `None` silently | `PASS` |
| `T-1.5` | `/download` returns 200 + pptx media type | `FAIL` — returned JSON `{url}` | `PASS` |
| `T-1.5` | `Content-Disposition` names the deck | `FAIL` — no such header | `PASS` |
| `T-1.6` | healthy registration → `registered`, error `null` | `FAIL` (field absent) | `PASS` |
| `T-1.6` | engine down → template still created | `PASS` (fallback pre-existed) | `PASS` |
| `T-1.6` | engine down → `fallback` + reason in API | `FAIL` — indistinguishable from healthy | `PASS` |
| `T-1.6` | status survives a list read | `FAIL` (field absent) | `PASS` |
| `T-1.6` | engine ref still absent from response | `PASS` | `PASS` |
| `T-1.1/2/3` | — | — | **not run — BLOCKED** |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | Locate Presenton source | present | `ls ../presenton-custom` → absent; `git ls-files '^presenton/'` → `0` | **FAIL — blocked** |
| M2 | Clean-tree image build (Phase 0 T-0.5 retest) | all services build | `init`, `orchestrator`, `worker`, `frontend` → **build OK**; `presenton` → `unable to prepare context: path .../presenton-custom not found` | **4/5 PASS** |
| M3 | Migration against Postgres | column + enum created, reversible | `registration_status template_registration_status not null default 'registered'`; `registration_error varchar(1024)`; enum `registered, fallback, failed`; down/up clean | **PASS** |
| M4 | Deck download in a real browser | file opens | **not attempted** — needs a running stack, which needs Presenton | **BLOCKED** |
| M5 | 9-step journey | all steps | **not attempted** — steps 7–9 need Presenton | **BLOCKED** |

**No screenshots are attached.** §5 carries the phase's real weight and it is largely unwalked; that is the honest state, not an omission.

**Artefacts:** commits `513ece6`, `39e0645`, `c4b9b5d`; `backend/alembic/versions/0006_template_registration.py`; `frontend/src/lib/download.ts`; `frontend/src/components/registry/RegistrationBadge.tsx`.

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | **PASS** | 61 → 70, none lost |
| Coverage did not decrease | **PASS** | 83% → 85% |
| No new `ruff` / `tsc` / `eslint` errors | **PASS** | ruff `10` at HEAD and after; tsc and eslint clean |
| Previous phases' gate criteria still hold | **PASS** | Phase 0's G4/G6/G7 re-verified: no secrets, tree clean, suite green |
| No previously working user journey broke | **NOT PROVABLE** | see below |

**On the last row.** The download path changed shape — response body, client call, and three components. Its tests pass and types check, but the deployed journey has not been walked in a browser. The old presigned URL was unreachable from a browser by construction, so there is no working journey to regress; the change cannot be worse than a URL that never resolved. That is an argument, not a verification.

---

## 7. Findings discovered during this phase

| # | Finding | Severity | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | Alembic revision ids > 32 chars fail at `UPDATE alembic_version` on Postgres. A SQLite-only check would not catch it; the failure lands on first VPS deploy | 🟠 | `StringDataRightTruncation` on `0006_template_registration_status` | **fixed in-phase** (D3). Worth a naming convention note in `T-2.7` |
| F2 | `window.open()` cannot fetch a bearer-authenticated endpoint. Option B as written in the prompt would have 401'd on every download | 🟠 | `services/api.ts:40-48`, `services/session.ts` | **fixed in-phase** — the prompt's T-1.5 change list is incomplete |
| F3 | 10 pre-existing `ruff` errors on `main`, incl. 4 × `F821 Undefined name OPEN_NOTEBOOK_API_VERSION` in `test_open_notebook_contract.py` — an undefined name in a *contract test* | 🟠 | `ruff check src tests` at `37c9e27` | **Phase 2** — F821 in a contract test means those assertions cannot be evaluating what they claim |
| F4 | Two download call sites absent from the prompt's evidence (`GeneratePanel.tsx:64`, `VersionHistoryPanel.tsx:67`) | 🟡 | `tsc --noEmit` | **fixed in-phase** |
| F5 | `VersionHistoryPanel` previews decks via an object URL with no revocation — a leak per preview | ⚪ | `VersionHistoryPanel.tsx` | **fixed in-phase** |
| F6 | `workers/tasks.py` sits at **29% coverage** — the lowest module in the tree, and the one where the T-1.4 race lived | 🟠 | coverage report | **Phase 2 (T-2.5)** — the silent-return bug survived because nothing executed that path |
| F7 | Migration `0006` backfills existing rows to `registered`, which is optimistic. Templates that really fell back keep rendering stock and now *claim* to be healthy | 🟡 | `0006_template_registration.py` | documented in the migration; re-upload re-registers. Consider a one-off re-registration pass in **Phase 4** |

F6 is the one worth dwelling on. The enqueue-before-commit race is exactly the class of defect that unit tests do not find and coverage gaps predict. It lived in the least-covered module in the codebase.

---

## 8. Facts vs. assumptions

| Claim | Basis |
|---|---|
| Backend suite is 70/1 at 85% | **verified by execution** |
| Migration 0006 is reversible on Postgres 16 | **verified by execution** — up, down, up, then `\d template` inspected |
| The enqueue race is fixed | **verified** — by a test that fails against the old ordering |
| The worker no longer returns silently on a missing row | **verified by test** |
| Registration fallback reaches the API and the UI type layer | **verified by test** (API) and **`tsc`** (UI). **The badge has not been rendered in a browser** |
| Downloads work | **partially verified.** Bytes, media type, and headers asserted by test. **No browser has clicked the button** |
| Frontend has no new type or lint errors | **verified by execution** |
| Presenton source is still absent | **verified** — `ls`, `git ls-files` |
| Brand tokens reach the renderer | **FALSE — untouched.** T-1.3 not started |
| `/editor` serves Presenton | **FALSE — untouched.** T-1.1 not started |

**Not verifiable in this environment:** everything requiring a running stack — the 9-step journey, browser 404 counts, the rendered-deck palette, and the editor deep-link. All need Presenton.

**The single largest open risk is unchanged from Phase 0:** the slide engine exists only as mutable state on one host, with no backup and no copy in version control.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | **FAIL** (3 PASS / 1 PARTIAL / 4 BLOCKED) |
| Next phase authorised | **NO** |
| Blockers carried forward | T-1.1, T-1.2, T-1.3 — all require the Presenton source; and T-0.1, T-0.2, T-0.3, T-0.5 from Phase 0 |
| Signed | Claude Opus 5 · 2026-07-28 |

**Rationale.** Three of six tasks are complete, tested, and committed: the enqueue race that stranded generations at `queued` forever, the download path that handed browsers an unresolvable internal hostname, and the registration fallback that let a user's branding silently never apply. Nine new tests, coverage 83% → 85%, no regressions, no new lint. Two defects in the phase prompt's own change lists were found and fixed (F1, F2), and `tsc` surfaced two call sites its evidence had missed.

**The phase's stated purpose is unmet.** G3 — brand colours visibly applied to a deck — is the criterion the prompt singles out as the reason Phase 1 exists, and it is untouched, along with `/editor` routing and the editor deep-link. All three need the Presenton source that Phase 0 exists to recover.

What changed for a user today: jobs no longer vanish, downloads have a path that can work, and a failed template registration is no longer invisible. What did not change: the headline feature still does not function, and the editor still does not open.

**Phase 2 must not start.** Its tasks assume a working core loop.
