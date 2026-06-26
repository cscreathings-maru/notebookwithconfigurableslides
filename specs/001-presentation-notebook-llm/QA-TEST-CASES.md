# QA Test Cases & Test Accounts — Presentation Notebook LLM (MVP)

**Audience:** QA team · **Build under test:** `001-presentation-notebook-llm`
**Companion docs:** [spec.md](spec.md) · [ASSESSMENT-AND-TEST-PLAN.md](ASSESSMENT-AND-TEST-PLAN.md)

This is the hands-on QA pack: ready-to-use **test accounts**, how to **sign in**, and a
**runnable test-case checklist** mapped to requirements (FR-xxx) and MVP user stories (US1–US5).
Fill the **Result** and **Notes** columns as you execute.

---

## 1. Environment setup (one-time)

1. Bring up the stack (see [quickstart.md](quickstart.md)):
   ```bash
   cd deploy && cp .env.example .env      # set DEEPSEEK_API_KEY, Presenton creds, etc.
   # IMPORTANT for QA sign-in without a live IdP — in deploy/.env set:
   #   OIDC_DEV_MODE=true
   #   NEXT_PUBLIC_DEV_MODE=true          # exposes the "Dev token" box on the login page
   docker compose up -d
   docker compose exec orchestrator alembic upgrade head
   ```
2. Provide the BYOK provider the QA tenants will use, then seed the QA accounts:
   ```bash
   export QA_LLM_BASE_URL="https://api.deepseek.com/v1"
   export QA_LLM_MODEL="deepseek-chat"
   export QA_LLM_API_KEY="sk-..."         # the QA provider key
   docker compose exec -e QA_LLM_API_KEY -e QA_LLM_BASE_URL -e QA_LLM_MODEL \
     orchestrator python -m scripts.seed_qa
   ```
   Re-running `seed_qa` is safe (idempotent).

---

## 2. Test accounts

All accounts are pre-provisioned by `scripts/seed_qa.py`. **Login is passwordless in dev mode**:
you mint a short-lived bearer token for the account's email and either paste it into the login
page or send it as `Authorization: Bearer <token>`.

```bash
# Mint a token (default 8h TTL). The --sub value is the account email.
docker compose exec orchestrator python -m scripts.mint_dev_token --sub author@qa-acme.test
```

| # | Tenant | Email (= login subject) | Role | Tenant quota | BYOK | Purpose / used by |
|---|--------|--------------------------|------|--------------|------|-------------------|
| 1 | QA Acme | `admin@qa-acme.test` | admin | unlimited | ✅ | Registry admin, approvals, usage/audit dashboards |
| 2 | QA Acme | `author@qa-acme.test` | author | unlimited | ✅ | Core happy path: upload → outline → generate → refine |
| 3 | QA Acme | `viewer@qa-acme.test` | viewer | unlimited | ✅ | RBAC negative (read-only) |
| 4 | QA Acme | `disabled@qa-acme.test` | author (disabled) | unlimited | ✅ | Auth negative (disabled account) |
| 5 | QA Globex | `admin@qa-globex.test` | admin | unlimited | ✅ | Cross-tenant isolation (the "other" tenant) |
| 6 | QA Globex | `author@qa-globex.test` | author | unlimited | ✅ | Cross-tenant isolation attempts |
| 7 | QA Quota | `admin@qa-quota.test` | admin | **2 / month** | ✅ | Quota config / verification |
| 8 | QA Quota | `author@qa-quota.test` | author | **2 / month** | ✅ | Quota enforcement (block on 3rd) |
| 9 | QA NoKey | `author@qa-nokey.test` | author | unlimited | ❌ none | "No provider configured" failure path |

> **Tenant isolation note:** QA Acme and QA Globex are separate organizations. Anything created by
> Acme must be invisible/inaccessible to Globex and vice-versa.

### 2.1 How to sign in (two ways)

- **Frontend (UI):** open the app → **Sign in** → paste the minted token into **"Dev token"** →
  *Use dev token*. You are now that user.
- **API (curl/Postman):** add header `Authorization: Bearer <token>` to every request.
  Verify identity with `GET /api/v1/auth/me` → returns your user, tenant, and role.

---

## 3. Test execution legend

- **Priority:** H (must pass to ship) · M (should pass) · L (nice to have)
- **Type:** Positive / Negative / Edge / Security
- **Result:** Pass / Fail / Blocked  ·  record build + date in **Notes**

---

## 4. Test cases

### 4.1 Authentication & session — US4 / FR-014

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-AUTH-01 | FR-014 | Positive | author@qa-acme | Token minted | `GET /auth/me` (or sign in via UI) | 200; returns email, tenant=QA Acme, role=author | H | | |
| QA-AUTH-02 | FR-014 | Negative | — | — | Call any endpoint with **no** Authorization header | 401 Unauthorized | H | | |
| QA-AUTH-03 | FR-014 | Negative | — | — | Call with a malformed/garbage bearer token | 401 Unauthorized | H | | |
| QA-AUTH-04 | FR-014 | Negative | — | Token TTL elapsed | Mint with `--ttl 60`, wait >60s, call `/auth/me` | 401 (expired) | M | | |
| QA-AUTH-05 | FR-014 | Negative | disabled@qa-acme | Account is disabled | Mint token, call `/auth/me` | 401 (account disabled) | H | | |

### 4.2 Multi-tenant isolation — US4 / FR-015 / SC-005

> Create resources as **Acme**, then attempt to reach them as **Globex**.

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-ISO-01 | FR-015 | Security | author@qa-globex | Acme has a project P | As Globex, `GET /projects/{P}` | 404 (not 403) | H | | |
| QA-ISO-02 | FR-015 | Security | author@qa-globex | Acme has a generation G | As Globex, `GET /generations/{G}` | 404 | H | | |
| QA-ISO-03 | FR-015 | Security | author@qa-globex | Acme has a source S | As Globex, `GET /sources/{S}` | 404 | H | | |
| QA-ISO-04 | FR-015 | Security | author@qa-globex | Acme generation G ready | As Globex, `GET /generations/{G}/download?format=pptx` | 404 | H | | |
| QA-ISO-05 | FR-007 | Security | author@qa-globex | Acme has profiles/templates | As Globex, `GET /profiles`, `GET /templates` | Only Globex items; never Acme's | H | | |
| QA-ISO-06 | FR-015 | Edge | author@qa-globex | — | List Acme project, copy its id, try `GET /projects/{id}` as Globex | 404; no data leak | M | | |

### 4.3 Role-based access control — US4 / FR-014

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-RBAC-01 | FR-014 | Negative | viewer@qa-acme | — | Attempt `POST /projects` | 403 Forbidden | H | | |
| QA-RBAC-02 | FR-014 | Negative | viewer@qa-acme | — | Attempt `POST /generations` | 403 | H | | |
| QA-RBAC-03 | FR-014 | Negative | author@qa-acme | — | Attempt `POST /profiles` (admin-only) | 403 | H | | |
| QA-RBAC-04 | FR-014 | Negative | author@qa-acme | — | Attempt `POST /templates` (admin-only) | 403 | H | | |
| QA-RBAC-05 | FR-014 | Positive | viewer@qa-acme | Acme has data | `GET /projects`, `GET /generations/{id}` | 200; read allowed | M | | |
| QA-RBAC-06 | FR-014 | Positive | admin@qa-acme | — | Create profile + template | 200/201 allowed | H | | |

### 4.4 Ingestion & sources — US1 / FR-001, FR-002, FR-003

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-ING-01 | FR-001 | Positive | author@qa-acme | — | `POST /projects {name}` | 201; project created (ON notebook provisioned internally) | H | | |
| QA-ING-02 | FR-001/002 | Positive | author@qa-acme | Project exists | Upload a valid PDF; poll `GET /sources/{id}` | status: queued → processing → ready; `analysis_ref` set | H | | |
| QA-ING-03 | FR-001 | Positive | author@qa-acme | Project exists | Add a source by `{url}` | Source created, ingest starts | M | | |
| QA-ING-04 | FR-001 | Edge | author@qa-acme | Project exists | Upload a CSV / DOCX / TXT | Each accepted; kind detected | M | | |
| QA-ING-05 | FR-002 | Negative | author@qa-acme | Project exists | Upload a corrupt / unsupported file | Source → `failed` with an error message; project stays usable | H | | |
| QA-ING-06 | FR-002 | Negative | author@qa-nokey | NoKey tenant has no BYOK | Upload a valid file | Source → `failed` "No LLM provider configured" (terminal, no infinite retry) | H | | |
| QA-ING-07 | data-model inv.5 | Security | author@qa-acme | A ready source | Inspect `GET /sources/{id}` body | No `on_source_id` / `on_notebook_id` exposed | H | | |
| QA-ING-08 | FR-013 | Edge | author@qa-acme | Source in `processing` | Poll `GET /jobs/{id}` | Progress reported (step/percent) | M | | |

### 4.5 Stakeholder profiles & templates (registry) — US2 / FR-004, FR-005, FR-006, FR-007

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-REG-01 | FR-006 | Positive | admin@qa-acme | — | Create a template (name + brand tokens), then approve it | Template created (draft) then approved | H | | |
| QA-REG-02 | FR-006 | Positive | admin@qa-acme | — | Create a template **importing a .pptx** file | Template registered from PPTX; engine ref stored server-side | M | | |
| QA-REG-03 | FR-004 | Positive | admin@qa-acme | Approved template exists | Create profile "Group Management" (audience, tone, verbosity, slide 6–10, language, 6-section structure, prompt config) | Profile v1 created (draft) | H | | |
| QA-REG-04 | FR-004 | Negative | admin@qa-acme | Only a **draft** template | Create a profile bound to that draft template | Rejected: "must bind an approved template" | M | | |
| QA-REG-05 | FR-005 | Positive | admin@qa-acme | Approved profile exists | Edit the profile (`PUT`) | A **new version** is created; prior version unchanged | H | | |
| QA-REG-06 | FR-005 | Negative | admin@qa-acme | A profile version used by a Generation | Try to approve/modify that in-use version | 409 "version in use / immutable" | H | | |
| QA-REG-07 | FR-007 | Positive | author@qa-acme | Approved + draft profiles exist | As author, `GET /profiles` | Author sees **approved only** | M | | |
| QA-REG-08 | inv.5 | Security | admin@qa-acme | Template exists | Inspect template response body | No `presenton_template_ref` exposed | H | | |
| QA-REG-09 | FR-007 | Security | admin@qa-globex | Acme has templates | As Globex admin, list templates | Acme templates never appear | H | | |

### 4.6 Generation core — US1 / FR-008, FR-009, FR-020 / SC-001

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-GEN-01 | FR-008 | Positive | author@qa-acme | Ready source + approved profile | `POST /projects/{id}/outline {profile_id}` | 201; outline `valid=true`; sections match the profile's structure & order | H | | |
| QA-GEN-02 | FR-009/020 | Positive | author@qa-acme | Valid outline | `POST /generations {outline_id}`; poll to ready; download | PPTX **and** PDF produced; signed download URL returned | H | | |
| QA-GEN-03 | US1-AS3 | Negative | author@qa-acme | A source still `processing` | `POST /generations` | 409 `sources_not_ready`; no partial deck | H | | |
| QA-GEN-04 | FR-003 (G2) | Edge | author@qa-acme | One source `ready`, one `failed` | `POST /generations` | 202; deck builds from the ready source; failed one skipped (recorded in audit) | H | | |
| QA-GEN-05 | FR-003 (G2) | Negative | author@qa-acme | All sources `failed` | `POST /generations` | 409 `no_ready_sources` | M | | |
| QA-GEN-06 | FR-020 | Negative | author@qa-acme | Generation not yet ready | `GET /generations/{id}/download` | 400 "not ready for download" | M | | |
| QA-GEN-07 | inv.5 | Security | author@qa-acme | Ready generation | Inspect generation detail + download URL | No `presenton_*`, `edit_path`, or template ref; URL is object-store signed, not an engine path | H | | |
| QA-GEN-08 | SC-001 | Performance | author@qa-acme | 15–25 page source set | Time upload → downloadable deck | p95 < 10 min | M | | |

### 4.7 Determinism & consistency gate — US1 / FR-010 / SC-002, SC-003

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-CONS-01 | SC-002 | Positive | author@qa-acme | Same project+profile+template version | Build outline twice | Identical section **set and order** both times (wording may differ) | H | | |
| QA-CONS-02 | SC-002 | Positive | author@qa-acme | Same inputs | Generate twice | Both decks have the same slide sections & ordering | H | | |
| QA-CONS-03 | FR-010 | Positive | author@qa-acme | Standard generation | Open the produced PPTX; check `consistency_report` | Report `passed=true`; required sections present in the deck, slide count in profile range, template applied | H | | |
| QA-CONS-04 | FR-010 | Negative | admin/author@qa-acme | Profile/outline with a banned term (e.g. "TBD", "lorem ipsum") in content | Generate | Consistency `passed=false`; generation `failed`/flagged for review | H | | |
| QA-CONS-05 | FR-010 | Edge | admin@qa-acme | Profile with a very narrow slide range (e.g. 3–3) and many sections | Generate | Slide-count check catches out-of-range; flagged | M | | |
| QA-CONS-06 | SC-002 | Edge | author@qa-acme | Source in Indonesian, profile language = English | Build outline/generate | Output language follows the profile, not the source | M | | |

### 4.8 Review, refine & provenance — US3 / FR-011, FR-012

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-REF-01 | FR-011 | Positive | author@qa-acme | A generated deck | Edit one outline section's wording + reduce slide count → regenerate | New deck reflects the edit; **no re-ingestion** of sources | H | | |
| QA-REF-02 | FR-011 | Edge | author@qa-acme | An outline | `PUT /outlines/{id}` with an invalid structure (renamed/extra section) | Re-validated; `valid=false`; generation blocked until fixed | M | | |
| QA-REF-03 | FR-012 | Positive | author@qa-acme | ≥2 generations in a project | `GET /projects/{id}/generations` | History lists each with profile version, template version, model/provider, params, created_by, created_at, status | H | | |
| QA-REF-04 | FR-005 | Edge | admin@qa-acme | A generation exists; then edit its profile | Compare old generation's provenance | Past generation still references the **old** pinned versions (not mutated) | H | | |
| QA-REF-05 | US3 | Positive | author@qa-acme | Two generations | View structural diff between them | Section set/order differences shown | L | | |

### 4.9 Usage, quota & audit — US5 / FR-018, FR-019

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-USE-01 | FR-019 | Positive | admin@qa-acme | Several generations done | `GET /usage?from=&to=` (or usage dashboard) | Correct per-user & per-tenant counts, tokens, estimated cost | H | | |
| QA-USE-02 | FR-019 | Positive | author@qa-quota | Quota = 2; create 2 successful generations | Attempt a **3rd** generation | Blocked: 429 `quota_exceeded`; event recorded; alert emitted | H | | |
| QA-USE-03 | FR-019 | Edge | author@qa-quota | Quota = 2; one generation **failed** | Verify quota usage count | Failed generation does **not** consume quota | M | | |
| QA-USE-04 | FR-018 | Positive | admin@qa-acme | Mutating actions performed | `GET /audit?from=&to=` | Each generation + admin action logged (actor, tenant, action, resource+versions, timestamp) | H | | |
| QA-USE-05 | slice-5 | Security | admin@qa-acme | — | Inspect audit entries | No secrets/API keys present in audit data | H | | |
| QA-USE-06 | FR-019 | Security | admin@qa-globex | Acme has usage | As Globex admin, view usage | Only Globex figures; no cross-tenant aggregation | M | | |

### 4.10 Frontend smoke (UI) — US1–US5

| ID | Req | Type | Account | Preconditions | Steps | Expected | Pri | Result | Notes |
|----|-----|------|---------|---------------|-------|----------|-----|--------|-------|
| QA-UI-01 | US4 | Positive | author@qa-acme | Dev token | Sign in via "Dev token" box | Lands in app; nav reflects role (author sees no admin areas) | H | | |
| QA-UI-02 | US4 | Negative | viewer@qa-acme | Signed in as viewer | Look for create/generate actions | Create/generate hidden or disabled | M | | |
| QA-UI-03 | US1 | Positive | author@qa-acme | Project open | Upload a source; watch status | Live status updates to ready | H | | |
| QA-UI-04 | US1 | Positive | author@qa-acme | Ready source + profile | Pick profile → preview outline → Generate → progress → Download | Deck downloads (PPTX/PDF) | H | | |
| QA-UI-05 | US2 | Positive | admin@qa-acme | — | Use profile editor (section builder) + template manager | Profile/template saved and selectable | M | | |
| QA-UI-06 | US5 | Positive | admin@qa-acme | Some usage | Open usage dashboard + quota indicator | Counts/cost render; quota status visible | M | | |
| QA-UI-07 | a11y | Edge | author@qa-acme | — | Keyboard-only nav at 320/768/1024/1440 widths | No overflow; focus states visible; reduced-motion respected | M | | |

---

## 5. Edge & negative coverage summary (from spec §Edge Cases)

| Edge / negative case | Covered by |
|----------------------|-----------|
| Corrupt / unsupported source | QA-ING-05 |
| No LLM provider configured | QA-ING-06 |
| Generation requested while analysis in progress | QA-GEN-03 |
| Some sources failed, some ready (proceed with warning) | QA-GEN-04 |
| All sources failed | QA-GEN-05 |
| Banned/boilerplate content in deck | QA-CONS-04 |
| Mixed-language sources, profile sets output language | QA-CONS-06 |
| Profile/template edited after a generation (version pinning) | QA-REF-04, QA-REG-06 |
| Quota exceeded | QA-USE-02 |
| Cross-tenant access (all resource types) | QA-ISO-01…06 |
| RBAC denial per role | QA-RBAC-01…04 |
| Disabled account / expired / missing token | QA-AUTH-02…05 |

---

## 6. Acceptance criteria (QA exit gate)

| AC | Criterion |
|----|-----------|
| AC-1 | All **High** cases pass; zero cross-tenant leakage (QA-ISO-*) |
| AC-2 | Determinism holds across repeated runs (QA-CONS-01/02) |
| AC-3 | Consistency gate passes for ≥90% of decks and blocks bad ones (QA-CONS-03/04) |
| AC-4 | Document → downloadable deck within target time (QA-GEN-08) |
| AC-5 | Every generation carries complete provenance (QA-REF-03) |
| AC-6 | Quota enforced; failed decks don't consume quota (QA-USE-02/03) |
| AC-7 | No engine ids/paths or secrets exposed to clients (QA-*-07, QA-USE-05) |

---

## 7. Defect report template

```
ID:            <jira/issue id>
Test case:     <e.g. QA-GEN-04>
Account used:  <e.g. author@qa-acme.test>
Build/commit:  <hash or date>
Severity:      Critical / High / Medium / Low
Steps:         <numbered>
Expected:      <...>
Actual:        <...>
Evidence:      <screenshot / response body / job id / correlation id>
```
