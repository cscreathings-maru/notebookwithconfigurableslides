# Phase 0 Test Report — Stop the Bleeding

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `0 — Stop the Bleeding` |
| Date started | `2026-07-28` |
| Date completed | **not complete — see §2** |
| Executed by | Claude Opus 5 (local workstation session) |
| Commit range | `b1e12de..894743d` (5 commits) |
| Branch | `revamp/phase-0` |
| Environment | `local` — macOS workstation |
| Presenton source revision | **UNKNOWN — source not reachable from this environment** |

---

## 2. Gate summary

| # | Exit gate criterion | Verdict | Evidence |
|---|---|---|---|
| G1 | Presenton source is committed; `git ls-files \| grep -c '^presenton/'` > 0 | **BLOCKED** | §5 M1 |
| G2 | `docker compose build` succeeds from a fresh clone into an empty directory | **BLOCKED** | §5 M2 |
| G3 | Stack starts and reaches a configured state with no `docker exec` intervention | **BLOCKED** | §5 M2 |
| G4 | No secret, key, or `.env` present in the committed tree | **PASS** | §4.1 V2 |
| G5 | Off-host backups of `presenton_data` and Postgres exist, checksums recorded | **BLOCKED** | §5 M3 |
| G6 | `git status --short` is clean | **PASS** | §4.1 V4 |
| G7 | Backend suite still 61 passed / 1 skipped | **PASS** | §4.1 |

**Overall gate: `FAIL`** — 3 of 7 criteria `PASS`, 4 `BLOCKED`.

> **Phase 1 must not start.** T-1.1 (`basePath`) and T-1.3 (brand tokens) both require editing and reading the Presenton source that G1 exists to recover.

### Why blocked

`G1`, `G2`, `G3`, `G5` all require the production VPS. Neither precondition holds in this environment:

| Precondition | State | Check |
|---|---|---|
| Presenton source present | **absent** | `ls ../presenton-custom` → `No such file or directory` |
| Docker daemon running | **down** | `docker info` → `Cannot connect to the Docker daemon` |

`PHASE-0-PROMPT.md` §Notes states: *"If the VPS is unreachable, stop and escalate immediately. Do not reconstruct Presenton from upstream and hope the deltas do not matter — the hand-mutations are exactly the part that is undocumented."*

That instruction was followed. **No attempt was made to fetch upstream Presenton and pass it off as the fork.** Doing so would have turned four honest `BLOCKED` gates into four false `PASS` gates — the precise failure mode documented as M2 in the assessment.

---

## 3. Task results

| Task | Title | Severity | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `T-0.1` | Recover and vendor the Presenton source | 🔴 | **BLOCKED** | `git ls-files \| grep -c '^presenton/'` → `0` | §5 M1 |
| `T-0.2` | Capture mutated runtime state as config | 🔴 | **BLOCKED** | — | §5 M1 |
| `T-0.3` | Back up live runtime data | 🟠 | **BLOCKED** | — | §5 M3 |
| `T-0.4` | Reconcile the working tree | ⚪ | **DONE** | `git status --short` → empty | `53d3d45`, `1e99a1e`, `9b79e59` |
| `T-0.5` | Prove reproducibility | ⚪ | **BLOCKED** | — | depends on T-0.1 |

### T-0.4 — DONE (detail)

Three commits, one concern each:

| Commit | Change |
|---|---|
| `53d3d45` | Untracked `backend/.coverage`; extended `.gitignore` to cover test/build artifacts **and** the Presenton runtime state (`app_data/`, `node_modules/`, `.next/`, `*.db`) ahead of T-0.1, so the engine source cannot drag in API keys or generated decks when it lands. |
| `1e99a1e` | Committed the in-flight `StudioPanel.tsx` editor-URL change **as-is**, deliberately unfixed. |
| `9b79e59` | Archived the superseded 26-criteria report to `docs/archive/NOTEAI_TEST_REPORT-2026-07-27.md`; committed the current overwrite. |

On `1e99a1e` — the change flips `/editor/presentation/${id}` → `/editor/presentation?id=${id}`. **Neither form works.** Both pass `Generation.id`; Presenton needs `Generation.presenton_presentation_id`, which the API deliberately never exposes (`api/generations.py:39-50`, `schemas/generation.py:51-68`). This is a backend contract defect, not a URL-format one. Committed only so the deployed state matches a commit; corrected in T-1.2.

On `9b79e59` — a provenance banner was prepended to the archive. Without it, a future reader finds a report claiming *"100% pass, 26 criteria"* and re-inherits the false confidence the archive exists to document. `README.md:79` still cites it; that correction belongs to T-2.7 and was **not** made here (rule 1: no scope creep).

### Deviations

**D1 — Two defects in the phase prompt itself, corrected during execution (`894743d`).**

| Defect | Impact | Fix |
|---|---|---|
| G1's check `git ls-files \| grep -c presenton` | **False positive.** Matches `backend/src/engines/presenton.py` and `backend/tests/contract/test_presenton_mapping.py` — the orchestrator's own *client*. Returned `2` on a tree with **zero** vendored engine files. The gate would have passed while the phase's entire purpose went unmet. | Anchored to `'^presenton/'`. Verified: now returns `0`. |
| T-0.4 cited `git show 1188545:NOTEAI_TEST_REPORT.md` | Command **fails** — `1188545` is a blob hash, not a commit-ish. | Corrected to `git show HEAD:...`. |

The first is the more serious: a gate that cannot fail is worse than no gate. Caught only because the result was inspected rather than trusted.

**D2 — Scope addition: `revamp/scripts/phase-0-vps-recover.sh`.**
Not in the original task list. Added because four tasks are blocked on an environment this session cannot reach, and a reviewed script is more useful than prose instructions. It is **preparation, not execution** — it changes nothing until run on the VPS, and commits nothing even then.

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Baseline (`b1e12de`) | This phase (`894743d`) | Delta |
|---|---|---|---|
| Passed | 61 | 61 | **0** |
| Failed | 0 | 0 | 0 |
| Skipped | 1 | 1 | 0 |
| Coverage (total) | 83% | 83% | **0** |
| Duration | 2.95s | 2.24s | −0.71s |

```
--------------------------------------------------------
TOTAL                                 3041    515    83%
61 passed, 1 skipped, 79 warnings in 2.24s
```

Identical to baseline, as expected — **Phase 0 changes no application code.**

**Verification block:**

| # | Check | Result |
|---|---|---|
| V1 | `git ls-files \| grep -c '^presenton/'` | `0` — **G1 fails correctly** |
| V2 | Secret scan (`sk-or-`, `sk-*`, private keys, `xox*`) over tracked files | `CLEAN` |
| V3 | Backend suite | `61 passed, 1 skipped` |
| V4 | `git status --short` | empty |
| V5 | `bash -n phase-0-vps-recover.sh` | `PASS` |

### 4.2 Frontend

`N/A — no frontend test tier exists yet (T-2.5).` `StudioPanel.tsx` was committed unmodified, so no verification was applicable.

### 4.3 End-to-end

`N/A — introduced in Phase 2 (T-2.6).` Also unrunnable here: no Docker daemon.

### 4.4 Per-task test evidence

| Task | Test | Before fix | After fix |
|---|---|---|---|
| `T-0.4` | `git status --short` | `FAIL` — 3 modified, 3 untracked | `PASS` — empty |
| `T-0.4` | `git ls-files \| grep '\.coverage'` | `FAIL` — `backend/.coverage` tracked | `PASS` — no match |
| `T-0.4` | archive exists | `FAIL` — not present | `PASS` — 130 lines |
| `T-0.1` | `git ls-files \| grep -c '^presenton/'` | `0` | **`0` — still failing (BLOCKED)** |

---

## 5. Manual verification

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | Locate Presenton source | present at `../presenton-custom` | `ls: ../presenton-custom: No such file or directory`; `find / -maxdepth 6 -type d -name presenton-custom` → nothing; `git log --all -- "*presenton-custom*"` → empty | **FAIL — blocked** |
| M2 | Docker availability | daemon running | CLI 27.3.1 present; `docker info` → `Cannot connect to the Docker daemon` | **FAIL — blocked** |
| M3 | Back up volumes | archives off-host | not attempted — requires M2 | **BLOCKED** |
| M4 | Archived report readable and banner-marked | banner + 117 original lines | confirmed, 130 lines total | **PASS** |
| M5 | Recovery script syntax | parses clean | `bash -n` → `PASS`; shellcheck unavailable | **PASS** |

**Artefacts:** commits `53d3d45`, `1e99a1e`, `9b79e59`, `894743d`; `docs/archive/NOTEAI_TEST_REPORT-2026-07-27.md`; `revamp/scripts/phase-0-vps-recover.sh`.

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | **PASS** | 61 passed, 1 skipped — identical |
| Coverage did not decrease | **PASS** | 83% → 83% |
| No new `ruff` / `tsc` / `eslint` errors | **PASS** | no source file modified except a committed-as-is `.tsx` |
| Previous phases' gate criteria still hold | **N/A** | first phase |
| No previously working user journey broke | **PASS** | no application code changed; deployed VPS untouched by this session |

**No regressions.** The one committed source change (`1e99a1e`) was already live on the VPS before this session; committing it altered no runtime behaviour.

---

## 7. Findings discovered during this phase

| # | Finding | Severity | Evidence | Proposed phase |
|---|---|---|---|---|
| F1 | G1's gate command was a false positive — matched the orchestrator's Presenton *client*, passing on a tree with zero engine files | 🟠 | `PHASE-0-PROMPT.md` (fixed in `894743d`) | **fixed in-phase** — a gate that cannot fail blocks the phase's own purpose |
| F2 | T-0.4 cited a blob hash as a commit-ish; the command errors | ⚪ | `PHASE-0-PROMPT.md` (fixed in `894743d`) | **fixed in-phase** |
| F3 | Root-level `.coverage` is regenerated whenever pytest runs with `--cov` from the repo root, not just `backend/` | ⚪ | observed during baseline capture | covered by `894743d` gitignore |
| F4 | `deploy/.env.lite.example:PRESENTON_DOMAIN` / `NEXT_PUBLIC_PRESENTON_UI_URL` still configure the retired subdomain model, contradicting the locked same-origin `/editor` decision | 🟡 | `deploy/.env.lite.example` | **T-1.2 / T-2.7** — already scoped |
| F5 | No `.gitignore` entry existed for `presenton/app_data/` before this phase. Vendoring in T-0.1 without it would have committed live API keys on the first `git add presenton/` | 🟠 | `.gitignore` before `53d3d45` | **pre-empted in `53d3d45`**; script also blocks on a secret scan |

F5 is worth flagging: the ordering in the prompt (hygiene last) would have created a real exposure. **T-0.4's gitignore work must precede T-0.1's vendoring**, not follow it. The prompt's task ordering should be amended before the next execution.

---

## 8. Facts vs. assumptions

| Claim | Basis |
|---|---|
| Presenton source is absent from this machine | **verified** — `ls`, `find /`, `git log --all` |
| Presenton has never been tracked in git | **verified** — `git log --all -- "*presenton-custom*"` returns empty |
| Backend suite unchanged at 61/1/83% | **verified by execution**, before and after |
| No secrets in tracked files | **verified by scan** — pattern-based; a novel credential format could evade it |
| Recovery script is syntactically valid | **verified** — `bash -n`. **Not verified by execution** — has never run against a live stack |
| Backups exist | **FALSE — none were taken.** No Docker daemon. |
| Stack builds from a clean clone | **unverified and currently false** — build context points at a non-existent directory |

**Not verifiable in this environment:**
- Every runtime property of Presenton — provenance, upstream fork point, extent of hand-mutation, contents of `/app_data/userConfig.json`
- Whether the VPS `presenton-custom` still exists at all
- Whether the running container is the only surviving copy

**The single largest open risk is unchanged by this phase:** the slide engine still exists only as mutable state on one host, with no backup. Phase 0's purpose is unmet.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | **FAIL** (3 PASS / 4 BLOCKED) |
| Next phase authorised | **NO** |
| Blockers carried forward | T-0.1, T-0.2, T-0.3, T-0.5 — all require VPS access |
| Signed | Claude Opus 5 · 2026-07-28 |

**Rationale.** Phase 0 is partially executed. Everything reachable from a local workstation is done: the working tree is reconciled and clean, the superseded verification report is preserved with a banner preventing its false-confidence claim from being re-inherited, build artifacts are untracked, and `.gitignore` now pre-emptively excludes the Presenton runtime state so vendoring cannot leak API keys. Two defects in the phase prompt were found and fixed — one of them a gate that could not fail.

**The phase's actual purpose — getting the slide engine into version control — is unmet**, because the source is not reachable from this environment. A user can do nothing today that they could not do yesterday; the risk this phase exists to eliminate is fully intact. `revamp/scripts/phase-0-vps-recover.sh` reduces the remaining work to one reviewed command on the VPS, but it has not been run.

**Phase 1 remains blocked.** T-1.1 and T-1.3 both require reading and editing the Presenton source.
