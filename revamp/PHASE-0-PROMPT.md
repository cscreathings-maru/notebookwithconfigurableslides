# Phase 0 — Stop the Bleeding

**Duration:** 0.5 day · **Severity:** 🔴 Critical · **Blocks:** every subsequent phase

---

## Role & context

You are working on **NoteAI**, a document→presentation platform. Architecture:

- `frontend/` — Next.js 14 (App Router, standalone output)
- `backend/` — FastAPI orchestrator (`/api/v1`), Postgres, Redis/Arq workers, MinIO
- **`presenton`** — the slide-rendering engine (Next.js UI + Python API), reached at `/editor`
- **`open-notebook`** — embeddings/retrieval engine backed by SurrealDB
- Traefik path-routes all of it on one origin

You are executing Phase 0 of a documented recovery programme. Read [`../ENGINEERING-ASSESSMENT.md`](../ENGINEERING-ASSESSMENT.md) §4 before starting if you have the budget; this prompt is otherwise self-contained.

---

## Why this phase exists

`deploy/docker-compose.lite.yml:160` builds the slide engine from a relative path:

```yaml
presenton:
  build:
    context: ../presenton-custom
```

**That directory has never been tracked in git.** Verified:

```bash
git log --all --oneline -- "*presenton-custom*"   # → empty
find / -maxdepth 6 -type d -name presenton-custom # → nothing
```

Consequences, in order of severity:

1. **The stack cannot be built from a fresh clone.** `docker compose build` fails immediately.
2. **The only copy is on one VPS**, and it has been hand-mutated — `NOTEAI_TEST_REPORT.md` §1.2 documents writing directly into `/app_data/userConfig.json` via `docker exec` to bypass a configuration error. That state exists in no file.
3. **Eight of the last ten commits** were attempts to fix routing into a component whose source was unavailable to the person fixing it.
4. **Phase 1 is impossible without it.** The agreed `/editor` architecture requires setting `basePath` in Presenton's `next.config.mjs`, and brand-token pass-through requires reading Presenton's generate-API contract. Neither can be done to a repository you do not have.

If that VPS is lost today, the product is unrecoverable.

---

## Scope

### In scope

- Bringing the Presenton source under version control
- Capturing the VPS's mutated runtime state as committed configuration
- Making `docker compose build` succeed from a clean clone
- Reconciling the working tree with a commit

### Out of scope — do not touch

- Any `basePath` / Traefik / routing change → **Phase 1 (T-1.1)**
- Any `brand_tokens` change → **Phase 1 (T-1.3)**
- Any backend or frontend source change beyond committing what already exists
- Refactoring, cleanup, or dependency upgrades of the Presenton source

**Phase 0 changes no behaviour.** Its only output is reproducibility. Resist every temptation to fix something while you are in there — you will not be able to attribute a Phase 1 regression if you do.

---

## Tasks

### T-0.1 — Recover and vendor the Presenton source 🔴

**Problem:** the slide engine exists only as untracked files on one host.

**Steps:**

1. On the VPS, locate the build context referenced by `docker-compose.lite.yml:160` (sibling of the repo root, `../presenton-custom`).
2. Establish provenance. Determine which upstream release it forked from:
   ```bash
   cd ../presenton-custom
   git log --oneline -5 2>/dev/null || echo "no git history — treat as unversioned fork"
   cat package.json | grep -E '"(name|version)"'
   ```
   Record the answer in the report. If provenance is unrecoverable, say so plainly rather than guessing.
3. Choose a vendoring strategy and record the rationale:

   | Strategy | Use when | Trade-off |
   |---|---|---|
   | **Git submodule** pointing at an org fork of upstream Presenton | Local changes are few and cleanly separable | Cleanest upstream merges; adds submodule friction |
   | **Subtree / direct vendor** into `presenton/` in this repo | Changes are extensive or provenance is lost | Simplest to build and reason about; upstream merges become manual |

   > **Recommendation:** if provenance is unclear — the likely case given the hand-mutation — **vendor directly** into `presenton/`. Optimising for a clean upstream merge path you may never use is not worth blocking Phase 1.

4. Commit the source. Exclude build output and secrets: `node_modules/`, `.next/`, `app_data/`, `*.db`, any `.env`.
5. Update `deploy/docker-compose.lite.yml` so `context:` points at the in-repo path. **This is the only line of existing config Phase 0 may change.**

**Acceptance:**
- `git ls-files | grep -c presenton` returns > 0
- `docker compose -f deploy/docker-compose.lite.yml build presenton` succeeds **from a fresh clone into an empty directory**
- No secret, API key, or `.env` file is present in the committed tree

---

### T-0.2 — Capture mutated runtime state as committed configuration 🔴

**Problem:** the running Presenton container was configured by hand. `NOTEAI_TEST_REPORT.md` §1.2 records injecting configuration into `/app_data/userConfig.json` through `docker exec` to bypass an "Instance Not Configured" block. A rebuild loses it.

**Steps:**

1. Extract the live state:
   ```bash
   docker compose -f deploy/docker-compose.lite.yml exec presenton \
     cat /app_data/userConfig.json > /tmp/presenton-userconfig.json
   ```
2. **Redact every secret** — API keys, tokens, passwords. Replace with `${ENV_VAR}` placeholders.
3. Commit the redacted structure as `presenton/config/userConfig.example.json`, documenting each field.
4. Determine how that config should be produced at boot: a container entrypoint that renders it from environment variables, or the native env vars Presenton already supports (`LLM`, `CUSTOM_LLM_URL`, `CUSTOM_LLM_API_KEY`, `CUSTOM_MODEL` are already set at `docker-compose.lite.yml:164-167`).
5. Document the mechanism in `presenton/README.md`.

**Acceptance:**
- A container built from committed source and started with only `deploy/.env.lite` reaches a configured state **with no `docker exec`**
- No real credential is committed — verify with a secret scan before pushing
- `presenton/README.md` explains the configuration path in enough detail for someone who has never seen the container

---

### T-0.3 — Back up live runtime data 🟠

**Problem:** `presenton_data` and the Postgres volume hold generated decks and workspace state with no recorded backup.

**Steps:**

```bash
docker run --rm \
  -v notebookllm-lite_presenton_data:/data \
  -v "$PWD":/backup alpine \
  tar czf /backup/presenton_data-$(date +%F).tar.gz -C /data .

docker compose -f deploy/docker-compose.lite.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "orchestrator-$(date +%F).sql.gz"
```

Store **off** the VPS. Record location and checksums in the report. **Do not commit these archives** — they contain tenant data.

**Acceptance:** both archives exist off-host, checksums recorded, restore procedure written down.

---

### T-0.4 — Reconcile the working tree ⚪

**Problem:** two uncommitted modifications mean the deployed state matches no commit:

- `frontend/src/components/project/StudioPanel.tsx` — editor URL changed from `/editor/presentation/${id}` to `/editor/presentation?id=${id}`
- `NOTEAI_TEST_REPORT.md` — overwritten in the working tree; the previous 26-criteria verification report is still the committed version at `HEAD` (blob `1188545`)

**Steps:**

1. Commit the `StudioPanel.tsx` change as-is with an honest message. **Do not attempt to fix it** — the URL is wrong in a way neither variant addresses (it passes the wrong identifier entirely), and that is T-1.2's job.
   ```
   chore(editor): commit in-flight editor URL change as-is (pre-T-1.2)

   Neither URL form works — both pass the NoteAI generation id, which
   Presenton cannot resolve. Committed only so the deployed state matches
   a commit. Corrected in T-1.2.
   ```
2. Preserve the superseded report: `git show HEAD:NOTEAI_TEST_REPORT.md > docs/archive/NOTEAI_TEST_REPORT-2026-07-27.md`, then commit the current version. Prepend a provenance banner stating that its "100% pass" result came from a regex checker and is not evidence of quality — otherwise the archive re-creates the false confidence it documents.
3. Add `backend/.coverage` to `.gitignore` and `git rm --cached` it.

**Acceptance:** `git status --short` is clean; the superseded report is preserved at a stable path.

---

### T-0.5 — Prove reproducibility ⚪

The gate for the whole phase.

```bash
cd "$(mktemp -d)"
git clone <repo-url> noteai && cd noteai
cp deploy/.env.lite.example deploy/.env.lite
# fill in credentials
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite build
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d
docker compose -f deploy/docker-compose.lite.yml ps
```

**Acceptance:** every service reaches `running` from a clean clone with **zero manual container intervention**. Record the full transcript in the report.

> Expect `/editor` to still 404 and downloads to still fail. **That is correct.** Phase 0 fixes reproducibility, not behaviour. Do not fix them here.

---

## Verification

```bash
# 1. Presenton is tracked
git ls-files | grep -c presenton                    # > 0

# 2. No secrets committed
git grep -InE '(sk-or-|sk-[A-Za-z0-9]{20,}|BEGIN.*PRIVATE KEY)' -- . ':!*.example*'   # → empty

# 3. Backend suite unchanged (Phase 0 touches no backend code)
cd backend && ./.venv/bin/python -m pytest tests/ -q
# expect: 61 passed, 1 skipped

# 4. Clean-clone build (T-0.5)
```

---

## Deliverable

`revamp/reports/PHASE-0-REPORT.md`, using [`TEST-REPORT-TEMPLATE.md`](TEST-REPORT-TEMPLATE.md).

Phase 0 has little automated testing by nature — its evidence is **transcripts**. §4 must contain:
- the unmodified backend suite result (proving nothing regressed)
- the **full clean-clone build transcript** from T-0.5
- the secret-scan output

§8 must state explicitly which Presenton behaviours remain unverified because they were never observable outside the VPS.

---

## Exit gate

| # | Criterion |
|---|---|
| **G1** | Presenton source is committed; `git ls-files \| grep -c presenton` > 0 |
| **G2** | `docker compose build` succeeds from a fresh clone into an empty directory |
| **G3** | The stack starts and reaches a configured state with **no** `docker exec` intervention |
| **G4** | No secret, key, or `.env` is present in the committed tree (scan output attached) |
| **G5** | Off-host backups of `presenton_data` and Postgres exist, with checksums recorded |
| **G6** | `git status --short` is clean |
| **G7** | Backend suite still 61 passed / 1 skipped |

**All seven must be `PASS`. Phase 1 cannot start otherwise** — T-1.1 and T-1.3 both require editing the Presenton source.

---

## Notes for the executor

- **This phase is boring and it is the most important one in the programme.** Everything else assumes a buildable stack.
- If the VPS is unreachable, **stop and escalate immediately.** Do not reconstruct Presenton from upstream and hope the deltas do not matter — the hand-mutations are exactly the part that is undocumented.
- If a secret has ever been committed, rotate it. `git rm` does not remove it from history.
- Resist fixing anything. Every non-reproducibility change you make here becomes a confound when Phase 1 regresses.
