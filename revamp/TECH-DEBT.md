# Tech Debt Register

Carried-forward work from the revamp programme: gates that did not pass, tests that could
not run, and findings deferred to a later phase. One row per item, each with the evidence
that proves it is still open and the check that will prove it closed.

**Status legend:** `BLOCKED` — cannot proceed in any environment reachable today ·
`OPEN` — actionable now · `DEFERRED` — actionable, scheduled for a named later phase.

Last reconciled: **2026-07-29** (post Phase 0 recovery; editor round-trip deferred to backlog).

---

## 1. The Presenton engine delta

**Substantially revised 2026-07-29 after the recovery script ran.** The original framing —
*"an unversioned fork, hand-mutated, provenance unrecoverable"* — was wrong on every count:

| Assumed | Found |
|---|---|
| Source absent from the VPS | **Present**, untracked, at `presenton-custom/` |
| Unversioned fork | Clean git checkout of `github.com/presenton/presenton` @ `0.9.3-beta` |
| Unknown divergence | **Zero commits** ahead of upstream |
| Mutations throughout the source | **One uncommitted line**: `assetPrefix: '/editor'` |

The real risk was never that the engine was lost. It was that **one line and one runtime
config file lived in exactly one place**, with no history and no backup — the same shape of
problem, deserving the same urgency.

Backups now exist (see TD-03). Closing `TD-01` — committing that one-line delta with its
upstream provenance — still unblocks the rest.

| ID | Item | From | Status | Closed when |
|---|---|---|---|---|
| **TD-01** | Commit the engine delta with provenance. **Not a 205MB vendor** — the tree is unmodified upstream plus one line; prefer a real fork or submodule | Phase 0 T-0.1 | `OPEN` | The `assetPrefix`/`basePath` change is committed somewhere with history |
| **TD-02** | Capture mutated runtime state as committed config | Phase 0 T-0.2 | `DONE (uncommitted)` | Captured and redacted to `presenton/config/userConfig.example.json`; needs committing |
| **TD-03** | Off-host backup of `presenton_data` + Postgres, checksums recorded | Phase 0 T-0.3 | `PARTIAL` | Archives **taken with checksums** (pg 8K, presenton 17M, minio 57M) but **still on the host they exist to survive** — the `scp` has not run |
| **TD-04** | Prove reproducibility from a clean clone | Phase 0 T-0.5 | `PARTIAL` | `docker compose build` succeeds for **all 5** services (currently 4/5 — `presenton` context absent) |
| **TD-05** | Serve Presenton at `/editor` via build-time `basePath` | Phase 1 T-1.1 | `BLOCKED` | `/editor` returns 200, zero asset 404s in devtools |
| **TD-06** | Fix the editor deep-link identifier (`editor_url` on `GenerationResponse`) | Phase 1 T-1.2 | `BLOCKED` | "🎨 Editor" opens the correct deck |
| **TD-07** | **Wire `brand_tokens` through to the renderer** | Phase 1 T-1.3 | `BLOCKED` | A `#FF00FF` template produces a visibly magenta deck |
| **TD-08** | Walk the 9-step manual journey with screenshots | Phase 1 G8 | `BLOCKED` | All 9 steps recorded in a report |
| **TD-09** | Smoke journeys `04-editor` and `05-branding` | Phase 2 T-2.6 | `BLOCKED` | Both pass. **Verified they correctly SKIP** against a live stack rather than falsely passing (Phase 2 §5 M9) |

> **TD-07 is the programme's highest-value item.** It is the product's headline feature —
> the repository is named *notebookwithconfigurableslides* and the slides are not
> configurable. The data is modelled and stored correctly; only the wiring is missing.
> **No longer blocked:** the source is on the VPS and the theming contract is known —
> `POST /api/v1/ppt/themes` taking `{name, description, company_name, logo, logo_url, data}`
> (read from `api/v1/ppt/endpoints/theme.py` in the published image).

### Recovery path

This work lives on `revamp/phase-1`, **not `main`** — a plain `git pull` on the VPS will
report "Already up to date" and the script will not exist. Check the branch out first:

```bash
cd /var/www/notebookfinal && git fetch origin && git checkout revamp/phase-1 && git pull
```

```bash
bash revamp/scripts/phase-0-vps-recover.sh
```

Backs up before touching anything, stages but never commits, and hard-stops if it finds a
secret in the vendored tree.

**Executed 2026-07-29.** Backups taken with checksums, `userConfig.json` captured and
redacted, source copied. Two defects it surfaced, both since fixed: the build context was
resolved from the wrong base (`e6e3adf`), and `.next-build` escaped the rsync excludes,
producing a 205MB tree of which 168MB was compiled output (`a535bc0`).

---

## 2. Verified-by-test but not walked in a browser

Shipped and covered by automated tests, but no human or headless browser has exercised the
real path. Distinct from `BLOCKED`: nothing prevents this except a running stack.

| ID | Item | From | Status | Closed when |
|---|---|---|---|---|
| **TD-10** | Deck PPTX/PDF download in a real browser | Phase 1 T-1.5 | `OPEN` | A browser click saves an openable file |
| **TD-11** | Registration-fallback badge renders in the templates UI | Phase 1 T-1.6 | `OPEN` | Badge observed on a `fallback` template |

**A local stack now starts.** `deploy/docker-compose.local.yml` substitutes the published
upstream image for the absent build context, so the orchestrator tier is exercisable —
that is how Phase 2's G5 was closed. These two still need a **browser** rather than curl,
and TD-11 additionally needs a template whose registration actually fell back.

---

## 3. Findings deferred to a named phase

| ID | Finding | Sev | From | Target | Closed when |
|---|---|---|---|---|---|
| **TD-14** | `workers/tasks.py` at **29% coverage** — lowest module in the tree, and where the T-1.4 enqueue race lived | 🟠 | Phase 1 F6 | **Phase 3** | Coverage ≥ 60% on `workers/` |
| **TD-15** | Migration `0006` backfills existing templates to `registered`. Templates that really fell back now *claim* to be healthy | 🟡 | Phase 1 F7 | **Phase 4** | A one-off re-registration pass, or an operator note |
| **TD-21** | Phase 2's gate G6 requires demonstrating the frontend tier "would have caught T-1.2" by reverting that fix. **T-1.2 was never fixed**, so there is nothing to revert — the gate assumes a Phase 1 that passed | 🟡 | Phase 2 F4 | **with TD-06** | The guard is demonstrated once T-1.2 lands |
| **TD-22** | Every boundary the orchestrator delegates across is untested at the engine tier. T-2.1's hole existed because `test_tenant_isolation.py` covers only Postgres; the pattern generalises | 🟠 | Phase 2 F6 | **Phase 4** | Engine contract tests run against real containers |
| **TD-23** | Option B (post-filtering) still sends every query to a shared index that computes similarity across all tenants' embeddings before results are discarded. Nothing leaves the boundary, but the index is not unshared | 🟠 | Phase 2 §8 | **Phase 4** | A namespace or instance per tenant, if `LITE_MODE=false` is to hold multi-tenant data |
| **TD-24** | **Editing round-trip: an edited deck is not downloadable.** Deck bytes are produced once at generation and stored in MinIO. Editing in the Presenton studio updates the engine's own copy, so the editor shows the edit and NoteAI's download returns the pre-edit file — silently. Full analysis and phased plan in [`PLAN-EDITOR-ROUNDTRIP.md`](PLAN-EDITOR-ROUNDTRIP.md) | 🟠 | 2026-07-29 | **backlog** | Edit a deck in the studio, download from NoteAI, and the file contains the edit |
| **TD-25** | Engine-side state (every template layout and deck edit) lives in one SQLite file in the `presenton_data` volume. One manual backup exists; no schedule, and no restore has ever been tested | 🟠 | 2026-07-29 | **backlog** | Scheduled off-host backup **and** a verified restore |
| **TD-26** | A NoteAI `Template` version is immutable once used by a `Generation`, but an engine-side layout edit changes rendering without bumping it — so a pinned "v1" can render differently over time. Unclear whether editing a template retro-changes decks already generated from it | 🟡 | 2026-07-29 | **backlog** | The rule is decided and documented; behaviour matches it |

---

## 4. Process debt

| ID | Item | Evidence | Closed when |
|---|---|---|---|
| **TD-19** | Phase prompts have shipped defects that would have produced false passes: a Phase 0 gate command that could not fail; a Phase 1 change list missing two call sites and the `window.open` auth problem; a Phase 2 evidence list missing a fourth unscoped search call site | Phase 0 D1/F1–F2, Phase 1 F2/F4, Phase 2 F1 | Gate commands are executed and their output inspected before a phase is signed off — not assumed |

---

## 5. Reconciliation

When a phase closes, update this file in the same commit as its report:

1. Move newly blocked items into §1 or §2.
2. Move newly deferred findings into §3 with a target phase.
3. Strike closed rows — **do not delete them**; move to §6 with the commit that closed them.
4. Update *Last reconciled*.

---

## 6. Closed

| ID | Item | Closed by | Note |
|---|---|---|---|
| **TD-12** | Undefined `OPEN_NOTEBOOK_API_VERSION` in a module-level-skipped contract test | `36d229c` (T-2.1) | Rewritten against the **verified real** `/api` surface; 7 tests, no skip. The suite now has 0 skipped. |
| **TD-13** | 6 × `F401` unused imports | `36d229c` (T-2.1) | `ruff check src tests` → `All checks passed!` |
| **TD-16** | Dead `PRESENTON_DOMAIN` / `NEXT_PUBLIC_PRESENTON_UI_URL` | `4688cc0` (T-2.7) | Removed from `.env.lite.example` and the compose build args |
| **TD-17** | README citing the archived report as quality evidence | `52272a2` (T-2.6) | Testing section rewritten; the citation is now a correction, not a claim |
| **TD-18** | Alembic revision id length convention undocumented | `4688cc0` (T-2.7) | Recorded in `docs/ARCHITECTURE.md` §8 |
| **TD-20** | Migrations only exercised against SQLite | `4688cc0` (T-2.7) | CI `migrations` job round-trips against real Postgres 16 |
