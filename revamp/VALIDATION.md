# Validating Phases 0–2

Copy-paste commands to check what actually works, with the output that means **pass**.

Every command here has been run. Where something cannot be validated yet, this says so
rather than offering a command that looks like it proves something.

---

## Where the three phases stand

| Phase | Gate | Reality |
|---|---|---|
| **0 — Stop the bleeding** | `FAIL` | 3 of 7 criteria pass. The 4 blocked ones all need the Presenton source. |
| **1 — Critical fixes** | `FAIL` | 3 of 6 tasks done (T-1.4, T-1.5, T-1.6). T-1.1/T-1.2/T-1.3 need Presenton. |
| **2 — Architecture stabilisation** | `FAIL` | 6 of 9 gates pass, 3 partial. **G1 and G2 — the phase's stated purpose — both pass.** |

**One root cause explains every gap: the slide engine is not in version control.**
See [`TECH-DEBT.md`](TECH-DEBT.md) — `TD-01` blocks nine tracked items.

A `FAIL` gate here does not mean the work is broken. It means at least one criterion is
unmet, and the reports say exactly which. Tier A below is all green.

---

## Tier A — no Docker, no stack, works anywhere

This is the bulk of Phase 1 and 2. Run from the repo root.

### A1. Backend suite and coverage

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

**Pass:** `120 passed, 0 skipped` and `TOTAL ... 89%`.
Phase 2's gate G9 requires ≥ 87%. Baseline before the programme was 61 passed / 83%.

### A2. Backend lint

```bash
cd backend && ./.venv/bin/python -m ruff check src tests
```

**Pass:** `All checks passed!` — was 10 errors before Phase 2 (TD-12, TD-13).

### A3. Frontend types, lint, tests, coverage gate

```bash
cd frontend && npm run typecheck && npm run lint && npm run test:coverage
```

**Pass:** no `tsc` output, `✔ No ESLint warnings or errors`, `Tests 66 passed`, and
**exit code 0** — a non-zero exit means a per-module coverage threshold was missed.

### A4. The isolation fix is real, not just present

The T-2.1 tests must fail against the old implementation, or they prove nothing:

```bash
cd backend && ./.venv/bin/python -m pytest tests/contract/test_engine_isolation.py -q
```

**Pass:** `8 passed`. To confirm they can fail, temporarily neuter the filter in
`src/engines/open_notebook.py` (`if ref is None or ref not in allowed:` → `if False:`)
and re-run — 3 must go red. **Undo it afterwards.**

### A5. Confirm the blocker is still the blocker

```bash
git ls-files | grep -c '^presenton/'
```

**Expected: `0`.** This is the check Phase 0's G1 exists to satisfy. Any number above
zero means `TD-01` has been closed and most of the blocked work can restart.

### A6. E2E specs compile

```bash
cd frontend && npx playwright test --list
```

**Pass:** `Total: 13 tests in 5 files`. This proves they parse — **not** that they pass.
Nothing has run them; see Tier C.

---

## Tier B — needs Docker, but not Presenton

### B1. Clean-tree image build (Phase 0 T-0.5 / TD-04)

```bash
cd deploy && cp .env.lite.example .env.lite && \
docker compose -f docker-compose.lite.yml --env-file .env.lite \
  build init orchestrator worker frontend
```

**Pass:** all four build, exit 0.

```bash
cd deploy && docker compose -f docker-compose.lite.yml --env-file .env.lite build presenton
```

**Expected failure:** `unable to prepare context: path ".../presenton-custom" not found`.
This is 4/5 — the honest state of TD-04. A different error means something else broke.

### B2. Migration round-trip against real Postgres

SQLite passes migrations that fail on Postgres — that is how a 33-character revision id
shipped and broke on deploy (TD-18/TD-20).

```bash
cd deploy && docker compose -f docker-compose.lite.yml --env-file .env.lite up -d postgres && sleep 10 && \
docker compose -f docker-compose.lite.yml --env-file .env.lite run --rm --no-deps \
  --entrypoint sh orchestrator -c "alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic current"
```

**Pass:** ends with `0006_template_registration (head)`.

Tear down when finished:

```bash
cd deploy && docker compose -f docker-compose.lite.yml --env-file .env.lite down -v && rm -f .env.lite
```

> `.env.lite` is gitignored and holds real keys on the VPS. The `cp` above is only for a
> throwaway local check — **never run it on a host that already has a real one.**

---

## Tier C — blocked, and honestly so

None of the following can be validated today. Each needs the Presenton source.

| What | Gate | Tracked as |
|---|---|---|
| `/editor` serves Presenton, zero asset 404s | Phase 1 G1 | TD-05 |
| "🎨 Editor" opens the correct deck | Phase 1 G2 | TD-06 |
| **A branded template produces a visibly branded deck** | Phase 1 **G3** | **TD-07** |
| The 9-step manual journey | Phase 1 G8 | TD-08 |
| `/api/readyz` through Traefik | Phase 2 G5 | — |
| 5 smoke journeys against a live stack | Phase 2 G7 | TD-09 |
| Download / registration badge in a real browser | — | TD-10, TD-11 |

**Do not accept a green result for any of these.** If something reports pass here today,
it is measuring the wrong thing — which is the exact failure this programme deleted a
regex script for.

---

## Unblocking: the recovery step

On the VPS. The branch must be checked out first — this work is **not on `main`**:

```bash
cd /var/www/notebookfinal && git fetch origin && git checkout revamp/phase-1 && git pull
```

Then:

```bash
bash revamp/scripts/phase-0-vps-recover.sh
```

The script backs up before touching anything, stages but never commits, and hard-stops
if it finds a secret in the vendored tree. **It has never been executed** — it is
syntax-checked only (`bash -n`). Read it before running it.

Once `git ls-files | grep -c '^presenton/'` returns non-zero, Tier C opens up.

---

## After a full validation pass

Expected totals as of `655c91d`:

| Check | Value |
|---|---|
| Backend tests | 120 passed, 0 skipped |
| Backend coverage | 89% |
| `ruff` | 0 errors |
| Frontend tests | 66 passed |
| Frontend typecheck / lint | clean |
| E2E specs | 13 collected, **0 run** |
| Images building | **4 of 5** |

Anything below these is a regression. Anything above means a blocker was closed —
update [`TECH-DEBT.md`](TECH-DEBT.md) in the same commit.
