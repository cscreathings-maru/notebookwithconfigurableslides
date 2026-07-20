# Testing Users & RBAC — Hands-on Guide (VPS)

**Live host:** `https://notebook.umarsyukri.com` · **VPS path:** `~/Notesslide/deploy`
**Companion:** [TESTING-API-CONFIG.md](TESTING-API-CONFIG.md) · canonical test cases live in
[`specs/001-presentation-notebook-llm/QA-TEST-CASES.md`](../specs/001-presentation-notebook-llm/QA-TEST-CASES.md)

This guide gets you from a fresh stack to **logged-in test users for every role**, and gives a
copy-paste curl per RBAC scenario. It assumes dev-mode auth (no live IdP), which is how this
deployment runs today.

> **It is NOT an RBAC problem if project-create returns 502.** Auth and roles work; the 502 is an
> **engine gap** (Open Notebook `POST /api/v1/notebooks` → 404) and Presenton crash-looping. See
> [§6 Known blockers](#6-known-blockers-read-before-testing-generation). Pure auth/RBAC/list/read
> cases below are fully testable right now.

---

## 1. One-time setup

```bash
cd ~/Notesslide/deploy

# Dev-mode auth must be on (already set on this VPS). Verify:
docker compose exec orchestrator env | grep -E 'OIDC_DEV_MODE|ENVIRONMENT'
#   OIDC_DEV_MODE=true   ENVIRONMENT=development   ← required for dev tokens

# Create the schema (idempotent):
docker compose exec orchestrator alembic upgrade head
```

Seed the **full QA fixture** (4 tenants, all roles, quotas, BYOK) in one command. Pass the BYOK
provider key so the tenants that need real generation are configured:

```bash
export QA_LLM_BASE_URL="https://api.deepseek.com/v1"
export QA_LLM_MODEL="deepseek-chat"
export QA_LLM_API_KEY="sk-...your-deepseek-key..."   # omit to leave BYOK unset (generation fails by design)

docker compose exec -e QA_LLM_API_KEY -e QA_LLM_BASE_URL -e QA_LLM_MODEL \
  orchestrator python -m scripts.seed_qa
```

`seed_qa` is **idempotent** — safe to re-run. Confirm the users landed:

```bash
docker compose exec postgres psql -U orch -d orchestrator \
  -c "SELECT email, role, status FROM user_account ORDER BY email;"
```

---

## 2. Test accounts (provisioned by `seed_qa`)

Each account's `oidc_subject` **is its email**, so minting a dev token is just `--sub <email>`.

| # | Tenant | Email (login subject) | Role | Quota | BYOK | What it's for |
|---|--------|-----------------------|------|-------|------|---------------|
| 1 | QA Acme | `admin@qa-acme.test` | admin | unlimited | ✅ | Registry admin, approvals, usage/audit |
| 2 | QA Acme | `author@qa-acme.test` | author | unlimited | ✅ | Core happy path (upload→outline→generate) |
| 3 | QA Acme | `viewer@qa-acme.test` | viewer | unlimited | ✅ | RBAC negative (read-only) |
| 4 | QA Acme | `disabled@qa-acme.test` | author *(disabled)* | unlimited | ✅ | Auth negative (disabled account → 401) |
| 5 | QA Globex | `admin@qa-globex.test` | admin | unlimited | ✅ | Cross-tenant isolation (the "other" org) |
| 6 | QA Globex | `author@qa-globex.test` | author | unlimited | ✅ | Cross-tenant isolation attempts |
| 7 | QA Quota | `admin@qa-quota.test` | admin | **2 / mo** | ✅ | Quota config |
| 8 | QA Quota | `author@qa-quota.test` | author | **2 / mo** | ✅ | Quota enforcement (block on 3rd) |
| 9 | QA NoKey | `author@qa-nokey.test` | author | unlimited | ❌ | "No provider configured" failure path |

> **Isolation:** Acme and Globex are separate orgs. Anything Acme creates must be invisible to Globex.

---

## 3. Sign in (two ways)

**Mint a token** (default 8h; `2>/dev/null` strips the key-length warning so you get a clean line):

```bash
docker compose exec orchestrator python -m scripts.mint_dev_token --sub author@qa-acme.test 2>/dev/null
```

- **UI:** open `https://notebook.umarsyukri.com/login` → paste into **"Dev token"** → *Use dev token*.
- **API:** send header `Authorization: Bearer <token>` on every request.

Convenience — capture a token into a shell variable for the curl examples below:

```bash
tok() { docker compose exec -T orchestrator python -m scripts.mint_dev_token --sub "$1" --ttl 3600 2>/dev/null | tr -d '\r'; }
ADMIN=$(tok admin@qa-acme.test); AUTHOR=$(tok author@qa-acme.test); VIEWER=$(tok viewer@qa-acme.test)
API="https://notebook.umarsyukri.com/api/v1"
```

Verify identity (any active user):

```bash
curl -s "$API/auth/me" -H "authorization: Bearer $AUTHOR" | python3 -m json.tool
# → { "email": "author@qa-acme.test", "role": "author", "tenant": ... }
```

---

## 4. Role → endpoint matrix

Roles are ranked **viewer (0) < author (1) < admin (2)**; a route needs *at least* its listed role.
Insufficient role → **403** (`insufficient_role`). Cross-tenant access → **404** (not 403, to avoid
resource enumeration). Missing/invalid/expired token or disabled user → **401**.

| Endpoint | Method | Min role |
|---|---|---|
| `/auth/me` | GET | any authenticated |
| `/projects` | GET · POST | viewer · **author** |
| `/projects/{id}` | GET | viewer |
| `/projects/{id}/sources` | GET · POST | viewer · **author** |
| `/sources/{id}` | GET | viewer |
| `/projects/{id}/outline` | POST | author |
| `/outlines/{id}` | GET · PUT | viewer · **author** |
| `/projects/{id}/generations` | GET · POST | viewer · **author** |
| `/generations/{id}` · `/generations/{id}/download` | GET | viewer |
| `/jobs/{id}` | GET | viewer |
| `/profiles` | GET · POST | viewer · **admin** |
| `/profiles/{id}` · `/profiles/{id}/approve` | PUT · POST | admin |
| `/templates` | GET · POST | viewer · **admin** |
| `/templates/{id}/approve` | POST | admin |
| `/usage` · `/audit` | GET | admin |
| `/tenant/llm-config` | GET · PUT | admin |

---

## 5. Copy-paste RBAC test cases

> Replace `<PID>` with a real project id where needed. Expected status is in the comment.

**TC-01 · viewer can read, cannot create (403)**
```bash
curl -s -o /dev/null -w "list=%{http_code}\n"  "$API/projects" -H "authorization: Bearer $VIEWER"            # 200
curl -s -o /dev/null -w "create=%{http_code}\n" -X POST "$API/projects" \
  -H "authorization: Bearer $VIEWER" -H "content-type: application/json" --data '{"name":"x"}'               # 403
```

**TC-02 · author can create** *(blocked today by §6 engine gap → 502, not 403)*
```bash
curl -s -o /dev/null -w "create=%{http_code}\n" -X POST "$API/projects" \
  -H "authorization: Bearer $AUTHOR" -H "content-type: application/json" --data '{"name":"proj 1"}'          # want 201; currently 502
```

**TC-03 · admin-only registry — author forbidden (403)**
```bash
curl -s -o /dev/null -w "tpl_author=%{http_code}\n" -X POST "$API/templates" \
  -H "authorization: Bearer $AUTHOR" -H "content-type: application/json" --data '{"name":"t","body":"..."}'  # 403
curl -s -o /dev/null -w "usage_admin=%{http_code}\n" "$API/usage" -H "authorization: Bearer $ADMIN"          # 200
curl -s -o /dev/null -w "usage_author=%{http_code}\n" "$API/usage" -H "authorization: Bearer $AUTHOR"        # 403
```

**TC-04 · disabled account rejected (401)**
```bash
DIS=$(tok disabled@qa-acme.test)
curl -s -o /dev/null -w "disabled=%{http_code}\n" "$API/auth/me" -H "authorization: Bearer $DIS"             # 401
```

**TC-05 · no/invalid token (401)**
```bash
curl -s -o /dev/null -w "none=%{http_code}\n"    "$API/projects"                                             # 401
curl -s -o /dev/null -w "garbage=%{http_code}\n" "$API/projects" -H "authorization: Bearer not.a.jwt"        # 401
```

**TC-06 · cross-tenant isolation (404, not 403)**
Create a resource as Acme, then try to read it as Globex — Globex must get **404**.
```bash
GLX=$(tok author@qa-globex.test)
# As Acme, get a project id (once create works), then:
curl -s -o /dev/null -w "globex_reads_acme=%{http_code}\n" "$API/projects/<ACME_PID>" \
  -H "authorization: Bearer $GLX"                                                                            # 404
```

**TC-07 · quota enforcement (block on 3rd)**
QA Quota is capped at 2 generations/month. After 2 successful generations, the 3rd must be rejected
with a quota error. *(Requires the generation flow, blocked by §6.)*

**TC-08 · no provider configured — clean failure**
`author@qa-nokey.test`'s tenant has no BYOK provider; ingestion/generation must fail **cleanly**
(clear error, no crash), not 500. *(Requires the ingest flow, blocked by §6.)*

---

## 6. Known blockers (read before testing generation)

These are **not** auth/RBAC issues. They block the create→ingest→generate chain end-to-end:

1. **Open Notebook contract mismatch.** Orchestrator calls `POST http://open-notebook:5055/api/v1/notebooks`,
   but the `lfnovo/open_notebook:v1-latest` image returns **404** for that path (its `/health` is 200).
   → Every `POST /projects` returns **502 (`EngineError`)**. Until the client is aligned to the real
   Open Notebook API (or the engine is swapped/stubbed), project creation can't succeed.
   Probe it directly:
   ```bash
   docker run --rm --network presentation-notebook-llm_appnet curlimages/curl:latest \
     -s -i -X POST http://open-notebook:5055/api/v1/notebooks \
     -H "content-type: application/json" --data '{"name":"probe","namespace":"qa-acme"}'
   ```
2. **Presenton crash-loop.** `docker compose ps` shows `presenton` `Restarting`. It backs the
   generation/export step and `orchestrator` declares `depends_on: [presenton]`. Diagnose:
   ```bash
   docker compose logs --tail=80 presenton
   ```

**What you CAN test now:** all of §5 except TC-02/07/08 — i.e. login, `/auth/me`, role gates (403),
disabled (401), missing/invalid token (401), list/read endpoints, and cross-tenant 404 on read.

---

## 7. Cleanup / reset

```bash
# Re-seed (idempotent — restores roles/status if a test mutated them):
docker compose exec -e QA_LLM_API_KEY -e QA_LLM_BASE_URL -e QA_LLM_MODEL \
  orchestrator python -m scripts.seed_qa

# Full reset (DESTROYS all data — wipes the Postgres volume):
docker compose down
docker volume rm presentation-notebook-llm_pg_data
docker compose up -d && docker compose exec orchestrator alembic upgrade head
```
