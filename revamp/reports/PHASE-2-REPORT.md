# Phase 2 Test Report — Architecture Stabilisation

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `2 — Architecture Stabilisation` |
| Date started | `2026-07-29` |
| Date completed | `2026-07-29`; **amended same day** after a local stack became runnable (§10) |
| Executed by | Claude Opus 5 (local workstation session) |
| Commit range | `bbfc6ce..4688cc0` (8 commits) |
| Branch | `revamp/phase-1` (continued; Phase 2 work is `36d229c..4688cc0`) |
| Environment | `local` — macOS workstation, Docker Desktop 27.3.1 |
| Open Notebook revision probed | `lfnovo/open_notebook:v1-latest` @ `sha256:e53f90d6153f…` |

---

## 2. Gate summary

| # | Exit gate criterion | Verdict | Evidence |
|---|---|---|---|
| G1 | RAG retrieval provably scoped; engine-isolation tests pass | **PASS** | §4.1, §5 M1 |
| G2 | Missing/unfilterable ref → empty grounding, never unscoped | **PASS** | §4.1 |
| G3 | Freeform generations in `/usage`; quota applies to both paths | **PASS** | §4.1 |
| G4 | `LlmClient` extends `EngineClient`; diagnosable; coverage ≥ 70% | **PASS** | §4.1 — 100% |
| G5 | `/api/readyz` reachable through Traefik, per-dependency; all healthchecks | **PASS** | §5 M8 |
| G6 | Frontend tier in CI; thresholds met; would have caught T-1.2 | **PARTIAL** | §4.2, §7 F4 |
| G7 | Regex script deleted; 5 Playwright journeys pass against a live stack | **PARTIAL** | §4.3, §5 M9 |
| G8 | No false documentation claim; `docs/ARCHITECTURE.md` exists | **PASS** | §5 M4 |
| G9 | Backend coverage ≥ 87%; no previously passing test regressed | **PASS** | §4.1 — 89% |

**Overall gate: `FAIL`** — **7 of 9 `PASS`**, 2 `PARTIAL`, 0 `FAIL`.

> **Amended 2026-07-29 (post-recovery).** G5 moved `PARTIAL` → `PASS` and G7 gained real
> evidence once a local stack became runnable. See §5 M8–M9; the addendum in §10 records
> what changed and why it became possible.

> **G1 and G2 — the phase's stated reason for existing — both PASS.** The cross-project
> retrieval hole is closed and covered by tests verified red against the old code.
> The two remaining PARTIALs no longer share a cause: G6 waits on T-1.2 landing, while
> G7 waits only on the two engines that still need to be running.

### Why the two are PARTIAL

| Gate | Done | Not done |
|---|---|---|
| G5 | ~~Never curled through Traefik~~ — **now verified end to end (§5 M8)** | *resolved* |
| G6 | 66 tests, thresholds enforced, CI workflow added | *"Would have caught T-1.2"* cannot be demonstrated — T-1.2 is still unfixed (TD-06), so there is no fix to revert |
| G7 | `01-shell` **passes 4/4 against a live stack**; `04`/`05` correctly **skip** | `02`/`03` still unexercised — need Open Notebook and Presenton running |

---

## 3. Task results

| Task | Title | Sev | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `T-2.1` | Scope RAG retrieval to the project | 🔴 | **DONE** | `test_engine_isolation.py` (8) | `36d229c` |
| `T-2.2` | Unify quota + metering across both paths | 🟠 | **DONE** | `test_generation_preflight.py` (5) | `9f79045` |
| `T-2.3` | `LlmClient` under the resilience layer | 🟠 | **DONE** | `test_llm_client.py` (21) | `436e5db` |
| `T-2.4` | Restore health monitoring | 🟠 | **DONE** | `test_health.py` (9) + §5 M8 | `2668bf4` |
| `T-2.5` | Frontend test tier | 🟡 | **DONE** | 66 Vitest tests | `b58c225` |
| `T-2.6` | Retire the fake verification suite | 🟡 | **PARTIAL** | 13 specs written, none run | `52272a2` |
| `T-2.7` | Reconcile documentation | 🟡 | **DONE** | §5 M4 | `4688cc0` |

### T-2.1 — the finding that determined the design

The prompt asks which of three options is available. **Established from the pinned image,
not assumed** — by reading `/app/api/`, `/app/open_notebook/domain/notebook.py` and the
SurrealDB migrations inside `lfnovo/open_notebook:v1-latest`:

| Question | Answer | Source |
|---|---|---|
| Does `POST /api/search` accept a notebook filter? | **No** | `api/models.py` — `SearchRequest` is `{query, type, limit, search_sources, search_notes, minimum_score}` |
| Do the search functions scope at all? | **No** | `fn::vector_search`, `fn::text_search` scan every embedding in the instance (`migrations/9.surrealql`) |
| Do results carry a usable reference? | **Yes — `parent_id`** | `SELECT source.id as parent_id` for both `source_embedding` and `source_insight` rows |
| Does it survive the API? | **Yes** | `SearchResponse.results` is `List[Dict[str, Any]]` — passed through unmodified |

**Option A is unavailable. Option C is unnecessary. This is Option B** — but filtered
against the orchestrator's **own tenant-scoped `Source` rows** rather than an
engine-reported notebook reference. That is a stronger authority: the allow-set is built
through `_scoped()`, which cannot be issued without a tenant filter.

Two details that matter and were not obvious:

- **Match on `parent_id`, not `id`.** For `source_insight` rows the engine aliases `id`
  to the insight's own id. Matching `id` would fail to match a legitimate hit and drop
  it — failing closed, but silently losing recall on every insight.
- **Over-fetch 6×.** Post-filtering discards other projects' hits, so requesting the
  final 10 would starve recall on a busy shared instance.

**A fourth call site beyond the three in the prompt's evidence:** `outline/builder.py:105`,
the governed outline path. It leaked identically. `allowed_source_refs` is a **required**
keyword there, so a future caller cannot forget to scope.

### T-2.2 — deviation from the prompt's signature

The prompt proposes one `authorize_and_meter()`. That cannot hold its own stated ordering:
quota must run **before any row is written**, while the usage record needs the generation
id that exists only **after**. Split into `authorize_generation()` and `meter_generation()`
in `generation/preflight.py` — one home, both constraints satisfied.

Metering records **even in lite mode**. `QuotaService` short-circuits there by design;
skipping the usage record would leave the dashboard blind in the deployment most users run.

### T-2.6 — PARTIAL, and why the specs skip

`automation/verify_noteai_revamp.py` is deleted (366 lines). Five journeys, 13 tests,
replace it. `04-editor` and `05-branding` **skip with a stated reason** when `/editor` is
unreachable rather than passing. Reporting green on a missing feature is precisely what
the deleted script did; a skip is honest, a vacuous pass is not.

~~**None of the 13 has run.**~~ **Amended:** `01-shell` now passes **4/4** against a live
stack, and `04`/`05` **skip** rather than pass — the design claim, validated (§5 M9).
`02`/`03` remain unexercised: they need Open Notebook and Presenton running.

### Deviations

**D1 — Phase 2 started against a `FAIL` Phase 1 gate**, at the user's direction, with
the Presenton-dependent tasks left untouched. Same posture as Phase 1's D1.

**D2 — Two `verify_noteai_revamp` references deliberately survive.** The prompt's check
expects `grep` to return empty. Both remaining mentions *name the script to explain why
it is gone* (README's correction note, CHANGELOG's correcting entry). Erasing them would
re-hide the false confidence the correction exists to record.

**D3 — Scope addition: `.github/workflows/ci.yml`.** There was no CI whatsoever, so
G6's *"runs in CI"* was unsatisfiable as written. Four jobs; the migration job runs the
round-trip against real Postgres, closing TD-20.

**D4 — Frontend coverage thresholds are per-module, not per-tree.** `api.ts` is ~100
one-line endpoint wrappers funnelling through the single `request` helper the tests
cover; a 60% *function* threshold there means 100 tests asserting URL strings. The
untested page components remain visible in the report (~25% overall) rather than being
hidden behind a narrowed `include`.

**D5 — TD-12 and TD-13 closed opportunistically.** Both were scheduled for Phase 2 and
sat in the module T-2.1 rewrites.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Phase 1 (`bbfc6ce`) | Phase 2 (`4688cc0`) | Delta |
|---|---|---|---|
| Passed | 70 | **120** | **+50** |
| Failed | 0 | 0 | 0 |
| Skipped | 1 | **0** | **−1** |
| Coverage (total) | 85% | **89%** | **+4** |
| `engines/llm.py` | 31% | **100%** | **+69** |
| `engines/open_notebook.py` | — | **89%** | — |
| `ruff` errors | 10 | **0** | **−10** |

```
TOTAL                                 3155    357    89%
120 passed, 103 warnings in 3.09s
```

**Verification block:**

| # | Check | Result |
|---|---|---|
| V1 | Backend suite | `120 passed, 0 skipped` |
| V2 | Coverage ≥ 87% (gate) | `89%` |
| V3 | `ruff check src tests` | **`All checks passed!`** (was 10 errors) |
| V4 | Isolation tests red against pre-T-2.1 client | `3 failed` — confirmed |
| V5 | Preflight tests red against pre-T-2.2 service | `5 failed` — confirmed |
| V6 | `docker compose config` after env cleanup | `OK` |
| V7 | `git status --short` | empty |

The skipped test is gone because `test_open_notebook_contract.py` no longer skips at
module level (TD-12) — it now pins the **verified real** `/api` surface, 7 tests.

### 4.2 Frontend

```bash
cd frontend && npm run typecheck && npm run lint && npm run test:coverage
```

| Check | Result |
|---|---|
| `tsc --noEmit` | **clean** |
| `next lint` | **No ESLint warnings or errors** |
| Vitest | **66 passed** across 9 files (was: no framework installed) |
| Coverage gate | **exit 0** — all per-module thresholds met |

| Module | Coverage |
|---|---|
| `lib/` (download, nav, structuralDiff, config) | **98%** |
| `SlideEditorModal.tsx` | **100%** |
| `SectionStructureBuilder.tsx` | **100%** |
| `StudioPanel.tsx` | **80%** |
| `services/api.ts` | **65%** |
| i18n `en`/`id` parity | **168/168 enforced** |

### 4.3 End-to-end

```bash
npx playwright test --list   # 13 tests in 5 files
```

| Journey | Tests | Runnable today |
|---|---|---|
| `01-shell` | 4 | needs a stack |
| `02-project-lifecycle` | 2 | needs a stack |
| `03-generation` | 2 | needs a stack |
| `04-editor` | 4 | **blocked — skips** (TD-05) |
| `05-branding` | 1 | **blocked — skips** (TD-07) |

**Nothing has executed.** The stack cannot start: `presenton`'s build context does not
exist. This is the honest state of G7.

### 4.4 Per-task test evidence

| Task | Test | Before | After |
|---|---|---|---|
| `T-2.1` | search never crosses notebooks | `FAIL` — returned both projects | `PASS` |
| `T-2.1` | empty scope issues no request | `FAIL` — searched unscoped | `PASS` |
| `T-2.1` | unresolvable hit dropped | `FAIL` — included | `PASS` |
| `T-2.1` | `parent_id` preferred over `id` | — | `PASS` |
| `T-2.1` | allow-set is tenant-scoped | — | `PASS` |
| `T-2.1` | guide grounded only in own sources | `FAIL` | `PASS` |
| `T-2.1` | chat citations own sources only | `FAIL` | `PASS` |
| `T-2.2` | freeform counted in `/usage` | `FAIL` — no record | `PASS` |
| `T-2.2` | freeform blocked at quota | `FAIL` — 202, unlimited | `PASS` |
| `T-2.2` | blocked attempt writes no row | `FAIL` | `PASS` |
| `T-2.2` | quota breach alerts on freeform | `FAIL` | `PASS` |
| `T-2.3` | 429 retried, 401 not | `FAIL` — no retry at all | `PASS` |
| `T-2.3` | each status → actionable log | `FAIL` — one opaque string | `PASS` |
| `T-2.3` | provider key never in client message | `PASS` | `PASS` |
| `T-2.4` | `/api/healthz` reachable | `FAIL` — 404 (root only) | `PASS` |
| `T-2.4` | per-dependency reporting | `FAIL` — db only | `PASS` |
| `T-2.4` | engine outage degrades, not unready | `FAIL` | `PASS` |
| `T-2.5` | download carries the bearer token | — | `PASS` |
| `T-2.5` | en/id parity | — | `PASS` |
| `T-2.6` | 5 journeys against a live stack | — | **not run** |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | Probe Open Notebook's real API | determine which scoping option exists | Pulled `v1-latest`, read `api/routers/search.py`, `api/models.py`, `domain/notebook.py`, `migrations/9.surrealql`. **No notebook filter; `parent_id` present.** | **PASS** |
| M2 | Isolation tests fail against old client | red | `3 failed, 5 passed` — the 5 are wiring/repository tests that scope independently | **PASS** |
| M3 | `/api/readyz` through Traefik | per-dependency JSON | **not attempted** — no stack | **BLOCKED** |
| M4 | Docs contain no false claim | — | README testing section rewritten; CHANGELOG corrected; `docs/ARCHITECTURE.md` created; dead env vars removed | **PASS** |
| M5 | Compose parses after env cleanup | valid | `docker compose config` → OK | **PASS** |
| M6 | CI workflow is valid YAML | parses | 4 jobs: backend, migrations, frontend, build | **PASS** |
| M7 | Two projects, disjoint sources, no cross-contamination | — | asserted **by test** (`test_guide_is_grounded_only_in_own_project_sources`), **not by hand** — needs a stack | **PARTIAL** |
| M8 | **Health through Traefik (G5)** | per-dependency JSON at `/api/readyz` | `GET /api/healthz` → **200**; `GET /api/readyz` → **200** `{"status":"degraded", ...}` with `postgres/redis/minio: ok`, `open_notebook/presenton: down`. `/` → **307** (frontend). `GET /readyz` at root → **404**, proving the pre-T-2.4 mount was unreachable behind the proxy. Compose reports `healthy` for frontend, orchestrator, postgres, redis, minio. | **PASS** |
| M9 | **Smoke journeys against a live stack (G7)** | real execution, no vacuous passes | `01-shell` **4/4 passed** (5.4s). `04-editor` + `05-branding` → **5 skipped**, with the stated reason, because `/editor` is unreachable. `02`/`03` not attempted — engines not running. | **PARTIAL** |

**No screenshots.** The prompt's manual steps 1–4 need journeys `02`/`03`, which need the
two engines running. Steps that only needed the orchestrator tier are now covered by M8.

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | **PASS** | 70 → 120, none lost |
| Coverage did not decrease | **PASS** | 85% → 89% |
| No new `ruff` / `tsc` / `eslint` errors | **PASS** | ruff 10 → **0**; tsc and eslint clean |
| Previous phases' gate criteria still hold | **PASS** | Phase 1 G4/G6/G7 re-verified |
| No previously working user journey broke | **NOT PROVABLE** | see below |

**On the last row.** T-2.1 changed the signature of `search()` and every caller; T-2.3
changed the LLM transport; T-2.4 changed compose `depends_on` semantics. All are covered
by tests and typecheck clean, but none has been exercised against a live stack.

The specific risk worth naming: **`depends_on: service_healthy` will hold startup until
healthchecks pass.** If a healthcheck is wrong, the stack hangs instead of racing. That
is the better failure mode, but it is a behaviour change on first deploy.

---

## 7. Findings discovered during this phase

| # | Finding | Sev | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | **A fourth unscoped search call site** — `outline/builder.py:105`, the governed outline path — absent from the prompt's evidence, leaking identically | 🔴 | `TypeError` on the changed signature surfaced it | **fixed in-phase** |
| F2 | Search results were mapped via `item.get("source_id") or item.get("id")`. For `source_insight` rows the engine aliases `id` to the *insight*, so the pre-existing mapping already attributed snippets to the wrong entity | 🟠 | `migrations/9.surrealql` | **fixed in-phase** (`parent_id`) |
| F3 | **No CI existed at all.** Every gate in this programme depended on someone running commands by hand | 🟠 | no `.github/` | **fixed in-phase** (D3) |
| F4 | G6's *"demonstrate by reverting the T-1.2 fix"* is unsatisfiable — T-1.2 was never fixed. The gate assumes a Phase 1 that passed | 🟡 | `PHASE-2-PROMPT.md` G6 | **prompt defect** — carried as TD-21 |
| F5 | `LlmClient` retries were previously absent *and* the base client logged nothing per attempt, so a retried 429 was invisible until exhaustion | 🟡 | `engines/base.py` | **fixed in-phase** — benefits all three engines |
| F6 | The engine-tier isolation gap existed because `test_tenant_isolation.py` covers only Postgres. **The pattern generalises**: every boundary the orchestrator delegates across is untested | 🟠 | §2 of the prompt | **Phase 4** — engine contract tests against real containers |
| F7 | `SlideEditorModal.tsx:23` still reads `NEXT_PUBLIC_PRESENTON_UI_URL`, which is permanently `undefined`. Its rewriting logic is dead code | ⚪ | `frontend/Dockerfile` declares no such build arg | **T-1.2** (blocked, TD-06) |

F1 is the one to dwell on. The prompt listed three call sites from a careful reading of
the codebase, and there were four. It surfaced only because `allowed_source_refs` was
made a **required** keyword — a signature that fails loudly rather than defaulting to
"unscoped" turned a silent leak into a `TypeError` at import time.

---

## 8. Facts vs. assumptions

**The prompt flags §8 as critical for T-2.1. Precisely:**

| Claim | Basis |
|---|---|
| Open Notebook's `/api/search` accepts no notebook filter | **verified** — read `SearchRequest` in the pinned image |
| Its search functions scan the whole instance | **verified** — read `fn::vector_search` / `fn::text_search` |
| Results carry `parent_id` = the source id | **verified** — read the SurrealQL `SELECT` |
| Option A is unavailable; **Option B is what shipped** | **verified by the above** |
| Retrieval is now scoped to the project | **verified by test**, including red-against-old |
| Missing/unfilterable ref yields empty grounding | **verified by test** — no HTTP request is issued at all |
| The allow-set cannot contain a foreign tenant's id | **verified by test** + structurally, via `_scoped()` |
| `LITE_MODE=false` is now safe for multi-tenant data | **INFERRED, NOT VERIFIED.** See the residual risk below |
| Freeform generations are metered and quota-gated | **verified by test**, red against old |
| `LlmClient` retries and is diagnosable | **verified by test** — 100% coverage |
| `/api/readyz` reports per dependency | **verified by test**, **not through Traefik** |
| Frontend behaviours listed in §4.2 | **verified by test** |
| The 5 smoke journeys pass | **FALSE — none has been run** |

### Residual risk on T-2.1 — written down, as the prompt requires

Option B is **post-filtering**. Its guarantees:

- **Holds:** no snippet whose source is outside the caller's project reaches an LLM
  prompt, a guide, a chat answer, or a deck. Enforced on our side of the boundary,
  against our own tenant-scoped rows.
- **Does not hold:** the *query* still reaches the shared index, and the engine still
  computes similarity against **every tenant's embeddings** before we discard them.
  Nothing leaves the engine boundary, but the query text is processed against foreign
  data. Under a strict interpretation this remains a shared-index deployment.
- **Depends on:** `on_source_id` matching `parent_id` exactly. If the formats ever
  diverge, the filter drops everything and grounding silently becomes empty — visible
  as a degraded product, **not** as a leak. The failure direction is correct.
- **Not covered:** notes. `search_notes` is `false` because note rows carry no source
  parent and therefore cannot be project-scoped at all.

**Recommendation, unchanged by this phase:** enabling `LITE_MODE=false` for more than
one tenant's data warrants Option C (a namespace or instance per tenant) as a
follow-up. Option B closes the observed leak; it does not make the index unshared.

**Not verifiable in this environment:** every runtime property of the deployed stack —
readiness through Traefik, healthcheck behaviour on real containers, the five smoke
journeys, and the manual isolation walkthrough.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | **FAIL** (6 PASS / 3 PARTIAL / 0 FAIL) |
| Next phase authorised | **NO** — but for a different reason than Phase 1 |
| Blockers carried forward | Live-stack verification (G5, G7) and T-1.1/T-1.2/T-1.3, all rooted in TD-01 |
| Signed | Claude Opus 5 · 2026-07-29 |

**Rationale.** Phase 2's stated purpose is met. **G1 and G2 — the criteria the prompt
names as the phase's reason for existing — both pass**, with tests verified red against
the previous implementation and the design chosen from the engine's actual source rather
than assumed. The retrieval hole that let one project's documents ground another's output
is closed, and closed on the side of the boundary the orchestrator controls.

Alongside it: quota and metering now cover the path users actually use, the LLM is as
resilient as the other two engines and its failures name themselves, health monitoring
exists and is reachable, the frontend has a test tier where it had none, and the script
that manufactured false confidence is gone. Backend 70 → 120 tests, coverage 85% → 89%,
ruff 10 errors → 0, and the repository has CI for the first time.

**What is not done is verification against something running.** Three gates are PARTIAL
for one reason: the stack cannot start, because the slide engine is not in the
repository. Thirteen smoke tests exist and none has executed; `/api/readyz` has never
been curled through Traefik; the isolation walkthrough is proven by test and not by hand.

That distinction is the whole point of this programme. **Phase 3 should not start**, and
not because Phase 2 under-delivered — because the next phase deletes the governed
pipeline, and deleting code that has never been exercised end-to-end in this environment
is how the original defects got here.

**The recommended next action is not Phase 3. It is `TD-01`** — one command on the VPS,
which unblocks nine tracked items including the product's headline feature.

---

## 10. Addendum — 2026-07-29, post-recovery

This report was signed with three gates `PARTIAL`, all attributed to one cause:
*"the stack cannot start, because the slide engine is not in the repository."*

**That premise turned out to be wrong**, and the correction is worth recording because it
was the programme's central assumption for three phases.

### What the Phase 0 recovery actually found

| Assumed since the assessment | Reality |
|---|---|
| `presenton-custom` is absent from the VPS | **Present**, untracked, inside the repo at `presenton-custom/` |
| An unversioned fork, hand-mutated, provenance unrecoverable | A **clean git checkout** of `github.com/presenton/presenton` at `0.9.3-beta` |
| Undocumented divergence of unknown extent | **Zero commits** ahead of upstream (`git log origin/main..HEAD` → empty) |
| Mutations spread through the source | **One uncommitted line**: `assetPrefix: '/editor'` in `servers/nextjs/next.config.mjs` |

The recovery script itself reported the source missing — it resolved the compose build
context `../presenton-custom` from the repo root rather than from `deploy/`, where the
compose file lives. Fixed in `e6e3adf`.

### What that made possible

With divergence reduced to one config line, the published upstream image reproduces the
engine faithfully enough to run everything except `/editor` itself.
`deploy/docker-compose.local.yml` swaps the absent build context for
`ghcr.io/presenton/presenton:latest`, and the stack starts.

### What was then verified, not inferred

- **G5 → PASS.** `/api/readyz` answers through Traefik with per-dependency status; `/` still
  reaches the frontend; **`/readyz` at the root returns 404**, which is the executed proof
  that the pre-T-2.4 mount was unreachable behind the proxy. Five services report `healthy`
  under the compose healthchecks added by T-2.4.
- **G7 → real evidence.** `01-shell` passes 4/4 against the live stack. `04-editor` and
  `05-branding` **skip** with their stated reason rather than passing — the T-2.6 design
  claim, validated. The deleted regex script would have reported green on both.
- **Migrations** `0001`–`0006` applied against real Postgres via `init`, which exited `0`.

### What is still open, and why

`02-project-lifecycle` and `03-generation` need Open Notebook and Presenton running.
G6 needs T-1.2 to land before *"would have caught it"* can be demonstrated at all.

`/editor` remains broken, and the reason is now precise rather than suspected:
`assetPrefix` prefixes **assets** but does not change **routing**. Only `basePath` does,
and it must be baked at build time — so it cannot be patched into a prebuilt image. The
VPS's removal of Traefik's `stripprefix` was half of T-1.1, applied by hand and never
committed.

### Correction to the sign-off

The original §9 recommended `TD-01` over Phase 3. That still holds, but the reasoning has
changed: the risk was never that the engine was lost. It was that a one-line change and a
runtime config file lived in exactly one place, with no history and no backup — which is
the same shape of problem, and was worth the same urgency.
