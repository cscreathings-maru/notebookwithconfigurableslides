# Phase &lt;N&gt; Test Report — &lt;Phase Name&gt;

> Copy this file to `revamp/reports/PHASE-<N>-REPORT.md` and fill every section.
> Sections are mandatory. If a section does not apply, write `N/A` and one line of justification — never delete it.

---

## 1. Metadata

| Field | Value |
|---|---|
| Phase | `<N> — <name>` |
| Date started | `YYYY-MM-DD` |
| Date completed | `YYYY-MM-DD` |
| Executed by | `<name / agent>` |
| Commit range | `<base-sha>..<head-sha>` |
| Branch | `<branch>` |
| Environment | `local` / `staging` / `VPS` |
| Presenton source revision | `<sha or submodule ref>` |

---

## 2. Gate summary

The phase is complete only when **every** row is `PASS`.

| # | Exit gate criterion | Verdict | Evidence |
|---|---|---|---|
| G1 | `<criterion, copied verbatim from the phase prompt>` | `PASS` / `FAIL` / `BLOCKED` | §&lt;section&gt; |
| G2 | | | |
| G3 | | | |

**Overall gate:** `PASS` / `FAIL`

---

## 3. Task results

| Task | Title | Severity | Status | Test proving it | Evidence |
|---|---|---|---|---|---|
| `T-N.1` | | 🔴/🟠/🟡 | `DONE` / `PARTIAL` / `DEFERRED` / `BLOCKED` | `<test id or path>` | `<commit / file:line / screenshot>` |
| `T-N.2` | | | | | |

**Any row that is not `DONE` requires a paragraph below explaining why, what was delivered, and what remains.**

### Deviations

`<none, or one subsection per deviation>`

---

## 4. Automated test execution

### 4.1 Backend

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src --cov-report=term
```

| Metric | Baseline (prev. phase) | This phase | Delta |
|---|---|---|---|
| Passed | | | |
| Failed | | | |
| Skipped | | | |
| Coverage (total) | | | |
| Duration | | | |

**Raw tail of output:**

```
<paste the final summary lines verbatim — not a paraphrase>
```

### 4.2 Frontend

*(From Phase 2 onward. Before that, record `N/A — no frontend test tier exists yet (T-2.5).`)*

```bash
cd frontend && npm run test -- --run && npm run typecheck
```

| Metric | Baseline | This phase | Delta |
|---|---|---|---|
| Passed | | | |
| Failed | | | |
| Coverage | | | |
| Type errors | | | |

```
<paste raw output>
```

### 4.3 End-to-end

*(From Phase 2 onward.)*

```bash
npx playwright test
```

| Journey | Verdict | Duration | Artefact |
|---|---|---|---|
| `<e.g. upload → generate → download>` | `PASS` / `FAIL` | | `<trace / screenshot path>` |

### 4.4 Per-task test evidence

For **every** task, both states must be recorded. A test that only passes proves nothing about the fix.

| Task | Test | Before fix | After fix |
|---|---|---|---|
| `T-N.1` | `<test path::name>` | `FAIL — <assertion message>` | `PASS` |

---

## 5. Manual verification

Steps actually performed by a human or driven browser. Not a plan — a record.

| # | Step | Expected | Observed | Verdict |
|---|---|---|---|---|
| M1 | | | | `PASS` / `FAIL` |
| M2 | | | | |

**Artefacts:** `<screenshots, HAR files, curl transcripts, container logs>`

---

## 6. Regression check

| Check | Verdict | Note |
|---|---|---|
| All previously passing backend tests still pass | | |
| Coverage did not decrease | | |
| No new `ruff` / `tsc` / `eslint` errors | | |
| Previous phases' gate criteria still hold | | |
| No previously working user journey broke | | |

**If any row is not `PASS`, the phase gate is `FAIL` regardless of task completion.**

---

## 7. Findings discovered during this phase

New defects found while working. **Recorded, triaged, and deferred — not fixed in this phase.**

| # | Finding | Severity | Evidence (`file:line`) | Proposed phase |
|---|---|---|---|---|
| F1 | | 🔴/🟠/🟡/⚪ | | |

---

## 8. Facts vs. assumptions

Keeps the programme honest about what was actually proven.

| Claim in this report | Basis |
|---|---|
| `<claim>` | `verified by test` / `verified by inspection` / `observed at runtime` / `inferred — needs confirmation` |

**Anything not verifiable in this phase and why:**

---

## 9. Sign-off

| Field | Value |
|---|---|
| Gate verdict | `PASS` / `FAIL` |
| Next phase authorised | `YES` / `NO` |
| Blockers carried forward | |
| Signed | `<name>` `YYYY-MM-DD` |

**Rationale (2–4 sentences — what the phase actually achieved, and what a user can now do that they could not before):**
