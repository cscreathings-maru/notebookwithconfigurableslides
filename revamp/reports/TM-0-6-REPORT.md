# TM-0 – TM-6 Report — Template Management

Implements [`PLAN-TEMPLATE-MANAGEMENT.md`](../PLAN-TEMPLATE-MANAGEMENT.md) in full. Follows
the shape of [`TEST-REPORT-TEMPLATE.md`](../TEST-REPORT-TEMPLATE.md).

---

## 1. Metadata

| Field | Value |
|---|---|
| Scope | TM-0 through TM-6, all seven tasks in the plan |
| Date | 2026-08-06 |
| Executed by | Claude (agentic session) |
| Branch | `revamp/phase-1` |
| Commit range | Uncommitted at time of writing; see §9 |
| Environment | Local (backend: SQLite-backed test harness; frontend: Vitest + jsdom). TM-0's contract dump was run by the user against the live VPS engine |

---

## 2. Gate summary

| # | Exit gate criterion | Verdict | Evidence |
|---|---|---|---|
| G1 | TM-0: `/async` request/response and task-status shapes confirmed against the running engine, not guessed | `PASS` | §3 — user ran the dump, output quoted verbatim in the plan §0 |
| G2 | TM-1: registration paths corrected, `/async` + poll replaces `/init`, contract test pins the literal URLs | `PASS` | §4.5 |
| G3 | TM-2: `POST /templates` returns sub-second with `pending`; registration is an Arq job | `PASS` | §4.5 |
| G4 | TM-3: `pending`/`registered`/`failed`/`no_source` are distinct, badged differently | `PASS` | §4.5 |
| G5 | TM-4: no manual approve step anywhere; success auto-approves | `PASS` | §4.5 |
| G6 | TM-5: delete removes both sides; refuses (409) when in use | `PASS` | §4.5 |
| G7 | TM-6: no brand-token configurator; nothing claims an effect it doesn't have | `PASS` | §4.5 |
| G8 | Backend suite stays green | `PASS` | §4.1 |
| G9 | Frontend suite stays green, typecheck clean | `PASS` | §4.2 |

**Overall gate:** `PASS`. One item explicitly carried forward, not silently dropped — see §9: the two live BRI templates on the VPS have not yet been re-registered through the fixed path (needs a deploy first).

---

## 3. Task results

| Task | Title | Severity | Status | Evidence |
|---|---|---|---|---|
| TM-0 | Pin the `/async`/task-status contract against the running engine | 🔴 | `DONE` | User-run dump, quoted in the plan §0 — confirmed `404` plural / `422` singular, `CreateTemplateRequest`/`AsyncTaskModel` shapes, and that the poll endpoint sits outside `/ppt` |
| TM-1 | Fix paths, switch to `/async` + poll, contract test | 🔴 | `DONE` | `engines/presenton.py`, `tests/contract/test_presenton_template_registration.py` (12 tests, rewritten) |
| TM-2 | Registration as an Arq job | 🟠 | `DONE` | `registry/registration.py` (new), `workers/tasks.py::run_register_template`, `registry/service.py::create`/`reregister` |
| TM-3 | Split `fallback` into 4 states | 🟠 | `DONE` | `models/registry.py`, migration `0013_template_reg_states.py` |
| TM-4 | Auto-approve, repair the two live templates | 🟠 | `DONE` (code) / **carried forward** (the two live rows) | `registry/registration.py` sets `status = approved` on success; VPS re-registration still owed, §9 |
| TM-5 | Delete | 🟡 | `DONE` | `DELETE /api/v1/templates/{id}`, `registry/service.py::delete`, `RegistryUsage.template_logical_id_in_use` |
| TM-6 | Hide the brand-token configurator | 🟠 | `DONE` | `frontend/.../templates/page.tsx` rewritten |

### Deviations

**A real bug was found and fixed while testing TM-5/TM-6, not just a test artifact.** The
page-level error alert (used by delete and reregister failures) was nested inside the
`{showCreate && (...)}` block — i.e., only rendered while the create form was open. A
delete failing with a 409 while the form was closed had nowhere to show its message,
silently. Moved to page level. Caught by
`page.test.tsx::"surfaces the 409 in-use message instead of failing silently"`, which
failed against the original placement and passes now — exactly the before/after evidence
this report format asks for.

**`TemplateRegistration.fallen_back()` renamed to `.rejected()`.** Its old name implied the
`fallback` status it constructed, which no longer exists post-TM-3; kept the method, renamed
it rather than leaving a name that lies about what it returns.

**`tenant_namespace()` made public** (`registry/service.py`, was `_tenant_namespace`). TM-2
moved the actual engine call from the request-handling service into the worker
(`registry/registration.py`), which still needs to compute the same tenant-namespaced name —
exporting it was the alternative to duplicating the one-line function.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term-missing
```

| Metric | Baseline (before TM-0..TM-6) | After | Delta |
|---|---|---|---|
| Passed | 260 | **264** | +4 net (many tests rewritten in place, not just added — see §4.4) |
| Failed | 0 | 0 | — |
| Coverage (total) | 90% | **89%** | −1pp — `workers/tasks.py`'s new `run_register_template` isn't directly unit-tested, same pre-existing gap `TECH-DEBT.md` TD-14 already named for its siblings (`run_ingest`/`run_generate`); the function it calls (`run_template_registration`) is well covered |
| `ruff check src tests` | clean | `All checks passed!` | — |

**Raw tail of output:**

```
264 passed, 203 warnings in 4.89s
```

New/rewritten test files: `tests/contract/test_presenton_template_registration.py` (12,
rewritten against the real contract), `tests/integration/test_template_registration_status.py`
(6, rewritten for async), `tests/integration/test_template_reregister.py` (7, rewritten),
`tests/integration/test_template_thumbnails.py` (5, rewritten), `tests/integration/test_registry.py`
(7, rewritten), `tests/contract/test_registry_versioning.py` (5, rewritten — gained a test),
plus one-line fixes in `tests/integration/test_generation.py`, `test_refine_history.py`,
`test_usage_audit.py` (their template-setup helpers now register+drive-to-completion instead
of calling the removed manual approve endpoint).

### 4.2 Frontend

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

| Metric | Baseline | After | Delta |
|---|---|---|---|
| Passed | 97 | **104** | +7 (new `templates/page.test.tsx`, the page's first-ever test file) |
| Failed | 0 | 0 | — |
| Type errors | 0 | 0 | — |

```
Test Files  14 passed (14)
     Tests  104 passed (104)
```

### 4.3 End-to-end

`N/A — not run.` Same reason as the prior report: no running Docker stack this session.

### 4.4 Per-task test evidence

| Task | Test | Before fix | After fix |
|---|---|---|---|
| TM-1 | `test_registration_calls_the_singular_template_prefix_the_engine_serves` | The *old* version of this test asserted the **plural** path as correct — it tested the client against itself and passed while every real registration 404'd | Rewritten to assert the singular path; fails if the regression recurs |
| TM-2 | `test_creation_starts_pending_not_a_guess_at_the_outcome` | `FAIL` — old code returned `registered`/`fallback` synchronously from the create response | `PASS` |
| TM-3 | `test_no_pptx_is_no_source_not_failed` | `FAIL` — no `no_source` value existed; a no-PPTX template reported `fallback`, indistinguishable from an engine rejection | `PASS` |
| TM-4 | `test_used_template_cannot_be_deleted` (registry_versioning) | `FAIL` — no delete endpoint existed to test against | `PASS` |
| TM-5 | `test_repair_cannot_reach_another_tenants_template` | Unaffected by TM-5 directly, but exercises the same tenant-scoping the new delete endpoint needed to get right — `PASS` throughout |
| TM-6 | `page.test.tsx::"the create form asks only for a name and a .pptx file"` | `FAIL` — the old form had colour pickers, font select, logo/aspect-ratio fields | `PASS` |
| — | `page.test.tsx::"surfaces the 409 in-use message instead of failing silently"` | `FAIL` — real bug, error alert had nowhere to render outside the create form | `PASS` after moving the alert to page level |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | `curl` the deployed engine's `/openapi.json`, filter for template/theme/task routes | Confirms `/template` (singular), `/template/async`, `/async-tasks/status/{id}`, `DELETE /template/{id}` | User ran it; output matches exactly (plan §0.3) | `PASS` |
| M2 | `curl -X POST` both `/templates/init` and `/template/init` with an empty body | `404` plural, `422` singular | User ran it; got exactly that | `PASS` |
| M3 | Re-register the two existing BRI templates through the fixed path on the live VPS | Both reach `registered` + `approved`, with thumbnails | **Not yet performed** — needs a deploy first | `BLOCKED`, carried forward (§9) |
| M4 | Click through create → pending badge → registered badge → delete in a real browser | Matches the automated test assertions | Not run — no browser/live engine this session | `N/A`, inferred from tests |

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | `PASS` | Several were rewritten (their setup depended on the removed approve endpoint), none weakened — each rewrite still proves the same invariant, now through the current API |
| Coverage did not meaningfully decrease | `PASS` (89% vs 90%, explained in §4.1) | |
| No new `ruff` errors | `PASS` | |
| No new `tsc` errors | `PASS` | |
| DG-0–DG-5's gate criteria still hold | `PASS` | Nothing here touches the outline/generation flow; `isSelectableTemplate`'s filter (DG-3.1) needed no change — its two conditions (`approved` and `registered`) still mean exactly what they meant before |
| No previously working user journey broke | `PASS` (test-level) | Template creation, reregistration, and the picker's filtering behavior are all still covered, just async-aware now |

---

## 7. Findings discovered during this phase

| # | Finding | Severity | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | The error alert placement bug (§3 Deviations) — found and fixed in this session, not deferred | 🟠 | `templates/page.tsx`, now fixed | Closed |
| F2 | `workers/tasks.py` coverage remains low (24%, was 24% for `run_ingest`/`run_generate` before this session per `TECH-DEBT.md` TD-14); `run_register_template` follows the same pattern and inherits the same gap | 🟡 | `TECH-DEBT.md` TD-14, unchanged scope | Already tracked, Phase 3 per TD-14 |
| F3 | `POST /template/async`'s `pptx_url` vs `modified_pptx_url` ambiguity (assessment §1, Defect B note) — the client sends `pptx_url` (matching the request schema's field name), matching what the *old* `/init` flow also sent. **Unverified against a real successful registration** — TM-0's dump confirmed the schema accepts `pptx_url`, not which of the preview step's two URLs the engine expects semantically | 🟡 | `engines/presenton.py::register_template` | Resolved implicitly by M3 (§9) — if registration succeeds with `pptx_url`, this is closed; if not, the fix is a one-line swap to `modified_pptx_url`, and the contract test already pins the field name so a swap is a one-line test update too |

---

## 8. Facts vs. assumptions

| Claim in this report | Basis |
|---|---|
| Backend: 264 passed, 89% coverage, ruff clean | verified by test |
| Frontend: 104 passed, clean `tsc` | verified by test |
| The `/template` singular path, `/async`, `/async-tasks/status/{id}`, and `DELETE /template/{id}` all exist on the live engine | verified by the user's own `curl`/openapi dump, not inferred |
| `404` plural / `422` singular | verified by the user's own `curl`, not inferred |
| Registering a real template end-to-end (preview → async → poll → success) works against the live engine | **not verified this session** — every test uses `FakePresenton`. This is the one real-engine gap; §9's M3 closes it |
| `pptx_url` (not `modified_pptx_url`) is the correct field for `/template/async` | **inferred** from the request schema's field name matching, not confirmed by a successful real call — F3 |
| The error-alert placement bug was real, not a test artifact | verified by test — reproduced with `screen.queryByRole("alert")` returning `null` after a confirmed `deleteTemplate` call, fixed by moving the JSX, test passes after |

**Anything not verifiable this session:** everything requiring a live Presenton engine —
specifically, whether a real `.pptx` actually reaches `registered` end-to-end through the new
`/async` path, and which of `pptx_url`/`modified_pptx_url` the engine actually wants (F3).

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | `PASS` (code-level) |
| Next phase authorised | `YES`, conditional on M3 |
| Blockers carried forward | (1) Deploy this batch, then re-register the two live BRI templates (`Template Presentasi BRI`, `Template Presentasi BRI v.2`) through the fixed path — this is also the first real-engine proof that TM-1's fix works end-to-end, not just against `FakePresenton`. (2) F3 — confirm `pptx_url` vs `modified_pptx_url` once M3 runs. |
| Nothing committed yet | See the commit/push step that follows this report |
| Signed | Claude (agentic session) · 2026-08-06 |

**Rationale:** Once deployed, uploading a `.pptx` template will actually register with the
engine for the first time in this codebase's history — every prior attempt 404'd on a URL
that never existed. A user can now watch a template go from "Mendaftarkan…" to a usable,
auto-approved template with real thumbnails, with no separate approve click; delete a
template they no longer want, blocked only when a real generation still depends on it; and
the template creation form no longer offers four sections of colour/font/logo controls that
never did anything. The one thing this session could not prove is the one thing it couldn't
reach: a real engine actually finishing a real registration. That's the very next step.
