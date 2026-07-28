# Tech Debt Register

Carried-forward work from the revamp programme: gates that did not pass, tests that could
not run, and findings deferred to a later phase. One row per item, each with the evidence
that proves it is still open and the check that will prove it closed.

**Status legend:** `BLOCKED` — cannot proceed in any environment reachable today ·
`OPEN` — actionable now · `DEFERRED` — actionable, scheduled for a named later phase.

Last reconciled: **2026-07-29** (end of Phase 1).

---

## 1. Blocked on the Presenton source

Every item here has one root cause: **the slide engine exists only as mutable container
state on the production VPS.** It has never been in version control, there is no backup,
and it is not reachable from the development workstation.

Closing `TD-01` closes or unblocks all nine.

| ID | Item | From | Status | Closed when |
|---|---|---|---|---|
| **TD-01** | Vendor the Presenton source into the repo | Phase 0 T-0.1 | `BLOCKED` | `git ls-files \| grep -c '^presenton/'` > 0 |
| **TD-02** | Capture mutated runtime state as committed config | Phase 0 T-0.2 | `BLOCKED` | `/app_data/userConfig.json` equivalent lives in the repo, not the container |
| **TD-03** | Off-host backup of `presenton_data` + Postgres, checksums recorded | Phase 0 T-0.3 | `BLOCKED` | Archives exist off-host with recorded checksums |
| **TD-04** | Prove reproducibility from a clean clone | Phase 0 T-0.5 | `PARTIAL` | `docker compose build` succeeds for **all 5** services (currently 4/5 — `presenton` context absent) |
| **TD-05** | Serve Presenton at `/editor` via build-time `basePath` | Phase 1 T-1.1 | `BLOCKED` | `/editor` returns 200, zero asset 404s in devtools |
| **TD-06** | Fix the editor deep-link identifier (`editor_url` on `GenerationResponse`) | Phase 1 T-1.2 | `BLOCKED` | "🎨 Editor" opens the correct deck |
| **TD-07** | **Wire `brand_tokens` through to the renderer** | Phase 1 T-1.3 | `BLOCKED` | A `#FF00FF` template produces a visibly magenta deck |
| **TD-08** | Walk the 9-step manual journey with screenshots | Phase 1 G8 | `BLOCKED` | All 9 steps recorded in a report |
| **TD-09** | Smoke journeys `04-editor` and `05-branding` | Phase 2 T-2.6 | `BLOCKED` | Both specs pass against a live stack |

> **TD-07 is the programme's highest-value blocked item.** It is the product's headline
> feature — the repository is named *notebookwithconfigurableslides* and the slides are not
> configurable. The data is modelled and stored correctly; only the wiring is missing.
> It is cheap to fix and cannot be started without the source.

### Recovery path

```bash
cd /var/www/notebookfinal && git pull && bash revamp/scripts/phase-0-vps-recover.sh
```

Backs up before touching anything, stages but never commits, and hard-stops if it finds a
secret in the vendored tree. **Never executed** — syntax-checked only (`bash -n`).

---

## 2. Verified-by-test but not walked in a browser

Shipped and covered by automated tests, but no human or headless browser has exercised the
real path. Distinct from `BLOCKED`: nothing prevents this except a running stack.

| ID | Item | From | Status | Closed when |
|---|---|---|---|---|
| **TD-10** | Deck PPTX/PDF download in a real browser | Phase 1 T-1.5 | `OPEN` | A browser click saves an openable file |
| **TD-11** | Registration-fallback badge renders in the templates UI | Phase 1 T-1.6 | `OPEN` | Badge observed on a `fallback` template |

Both depend on a stack that currently cannot start, because `presenton` has no build
context — so in practice they unblock with `TD-01`.

---

## 3. Findings deferred to a named phase

| ID | Finding | Sev | From | Target | Closed when |
|---|---|---|---|---|---|
| **TD-12** | 4 × `F821 Undefined name OPEN_NOTEBOOK_API_VERSION` in `tests/contract/test_open_notebook_contract.py` — an undefined name inside a **contract test**, so those assertions cannot be evaluating what they claim | 🟠 | Phase 1 F3 | **Phase 2** | `ruff check` clean; the contract test asserts a defined constant |
| **TD-13** | 6 × `F401` unused imports across `src/` and `tests/` | ⚪ | Phase 1 F3 | **Phase 2** | `ruff check src tests` reports 0 |
| **TD-14** | `workers/tasks.py` at **29% coverage** — lowest module in the tree, and where the T-1.4 enqueue race lived | 🟠 | Phase 1 F6 | **Phase 2 (T-2.5 adjacent)** | Coverage ≥ 60% on `workers/` |
| **TD-15** | Migration `0006` backfills existing templates to `registered`. Templates that really fell back now *claim* to be healthy | 🟡 | Phase 1 F7 | **Phase 4** | A one-off re-registration pass, or an operator note |
| **TD-16** | `.env.lite.example` still configures `PRESENTON_DOMAIN` / `NEXT_PUBLIC_PRESENTON_UI_URL` for the retired subdomain model, contradicting the locked same-origin `/editor` decision | 🟡 | Phase 0 F4 | **Phase 2 (T-2.7)** | Dead variables removed |
| **TD-17** | `README.md:79` cites the archived `NOTEAI_TEST_REPORT.md` for "26 criteria, 100% pass" — a claim the archive itself now carries a banner disowning | 🟡 | Phase 0 F3 | **Phase 2 (T-2.7)** | No doc cites the archived report as evidence |
| **TD-18** | Alembic revision ids must stay ≤ 32 chars (`alembic_version.version_num` is `varchar(32)`). Caught only by running against Postgres; SQLite would have passed it | ⚪ | Phase 1 F1 | **Phase 2 (T-2.7)** | Convention documented in `docs/ARCHITECTURE.md` |

---

## 4. Process debt

| ID | Item | Evidence | Closed when |
|---|---|---|---|
| **TD-19** | Phase prompts have shipped defects that would have produced false passes: a Phase 0 gate command that could not fail; a Phase 1 change list missing two call sites and the `window.open` auth problem | Phase 0 D1/F1–F2, Phase 1 F2/F4 | Gate commands are executed and their output inspected before a phase is signed off — not assumed |
| **TD-20** | Migrations are only exercised against SQLite in the test suite; `TD-18` proves that is insufficient | Phase 1 D3 | Migration round-trip against Postgres runs in CI |

---

## 5. Reconciliation

When a phase closes, update this file in the same commit as its report:

1. Move newly blocked items into §1 or §2.
2. Move newly deferred findings into §3 with a target phase.
3. Strike closed rows — **do not delete them**; move to §6 with the commit that closed them.
4. Update *Last reconciled*.

---

## 6. Closed

_None yet._
