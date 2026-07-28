# NoteAI Revamp — Phase Execution Prompts

Companion to [`../ENGINEERING-ASSESSMENT.md`](../ENGINEERING-ASSESSMENT.md).

This directory contains **one self-contained execution prompt per phase**. Each prompt is written so an engineer or agent starting with zero prior context can execute it correctly, and each ends by producing a **test report in an identical format** so progress is comparable across phases.

---

## Architecture decision (locked)

> **Presenton is hosted on the same origin under the `/editor` subpath.**
> One domain. One TLS certificate. One nginx rule. No cross-domain configuration.

**Mechanism:** build-time `basePath: '/editor'` in Presenton's `next.config.mjs`.

This is the decision recorded in `NOTEAI_TEST_REPORT.md` §Solution 1. It is chosen over §Solution 2 (expanding Traefik rules to capture root-level assets) for one reason:

- Both the NoteAI frontend and Presenton are Next.js applications.
- Both serve their static assets from `/_next`.
- A Traefik rule cannot disambiguate two byte-identical path prefixes at the same origin — no priority ordering resolves it.
- With `basePath`, Presenton emits `/editor/_next/...` instead. **The collision ceases to exist** rather than being arbitrated.

Same destination, working mechanism.

---

## Phase index

| Phase | File | Duration | Theme | Blocking? |
|---|---|---|---|---|
| **0** | [`PHASE-0-PROMPT.md`](PHASE-0-PROMPT.md) | 0.5 d | Stop the bleeding — get Presenton into version control | **Yes — blocks everything** |
| **1** | [`PHASE-1-PROMPT.md`](PHASE-1-PROMPT.md) | 3–4 d | Critical fixes — make the core loop work | Yes |
| **2** | [`PHASE-2-PROMPT.md`](PHASE-2-PROMPT.md) | 4–5 d | Architecture stabilisation — isolation, metering, tests | Yes |
| **3** | [`PHASE-3-PROMPT.md`](PHASE-3-PROMPT.md) | 5–8 d | Scope resolution — one pipeline, one set of guarantees | No |
| **4** | [`PHASE-4-PROMPT.md`](PHASE-4-PROMPT.md) | ongoing | Long-term hardening | No |

**Total to a genuinely working product: ~13–18 working days (Phases 0–3).**

### Dependency graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
   │            │
   │            ├─ T-1.1 basePath   requires vendored Presenton source
   │            ├─ T-1.3 brand tokens requires vendored Presenton source
   │            └─ T-1.2 editor link  requires T-1.1
   └─ nothing downstream is reproducible without a buildable stack
```

Phases run **in order**. Phase N may not begin until Phase N−1's exit gate is signed off.

---

## How to use a phase prompt

1. Open the phase file. Everything needed is inside it — do not assume the reader has seen the assessment.
2. Work the tasks in the listed order (dependencies are noted per task).
3. Run the phase's **Verification** block.
4. Produce the test report using [`TEST-REPORT-TEMPLATE.md`](TEST-REPORT-TEMPLATE.md), saved as `revamp/reports/PHASE-N-REPORT.md`.
5. Check the **Exit gate**. If any gate criterion is `FAIL`, the phase is not complete — do not proceed.

---

## Conventions used in every prompt

| Convention | Meaning |
|---|---|
| `T-N.x` | Task identifier, stable across the whole programme. Referenced by test reports. |
| **Evidence** | The `file:line` proving the defect exists. Verify it still matches before changing anything — the codebase may have moved. |
| **Acceptance** | A binary, observable condition. Not "improved" — either it holds or it does not. |
| **Out of scope** | Explicitly deferred. Do not opportunistically fix these; they belong to a later phase and widen the blast radius. |
| 🔴 / 🟠 / 🟡 | Severity from the assessment: Critical / High / Medium. |

---

## Non-negotiable rules for every phase

1. **No scope creep.** If you find a new defect, record it in the report's *Findings discovered during this phase* section. Do not fix it unless it blocks a task in the current phase.
2. **Every fix ships with a test** that fails before the change and passes after. State both in the report.
3. **Never let a regression pass.** The backend suite must stay green (baseline: 61 passed, 1 skipped, 83% coverage). A dropped test is a `FAIL` gate.
4. **Do not weaken a security boundary to make a task pass.** Tenant scoping and the "engine internals never reach the client" invariant are load-bearing. If a task appears to require breaking one, stop and escalate — T-1.2 is the one deliberate, reviewed exception.
5. **Silent fallbacks are forbidden.** This codebase's dominant failure mode is degradation that looks like success (`register_template` → `"default"`, `search()` → `[]`, `_load_job` → `return`). New code must surface failure, never conceal it.
6. **Commit per task**, referencing the task id: `fix(editor): bake basePath at build time (T-1.1)`.

---

## The consistent test report

Every phase produces the same document shape, so phases can be compared and the programme audited end to end:

1. **Metadata** — phase, date, commit range, executor
2. **Gate summary** — one row per exit criterion, `PASS` / `FAIL` / `BLOCKED`
3. **Task results** — one row per `T-N.x` with evidence links
4. **Automated test execution** — command, raw counts, coverage, delta vs. previous phase
5. **Manual verification** — steps actually performed, with observed output
6. **Regression check** — explicit confirmation nothing previously green went red
7. **Findings discovered during this phase** — new defects, triaged, not fixed
8. **Sign-off** — gate verdict and go/no-go for the next phase

See [`TEST-REPORT-TEMPLATE.md`](TEST-REPORT-TEMPLATE.md).

> **Note on the existing report format.** `automation/verify_noteai_revamp.py` is a regex-over-source-files checker. It asserts that `tailwind.config.ts` *contains the string* `2563EB`. It executes no application code and cannot detect a single defect in the assessment, yet `README.md` cites its "100% pass rate" as quality evidence. **Do not model the new reports on it, and do not extend it.** It is retired in Phase 2 (T-2.6).
