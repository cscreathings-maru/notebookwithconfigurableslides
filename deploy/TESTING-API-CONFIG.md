# API & Environment Configuration — Testing Reference (VPS)

**Live host:** `https://notebook.umarsyukri.com` · **VPS path:** `~/Notesslide/deploy`
**Config file:** `deploy/.env` (copied from [`.env.example`](.env.example)) · loaded by `docker-compose.yml`
**Companion:** [TESTING-USERS-AND-RBAC.md](TESTING-USERS-AND-RBAC.md)

Every value below lives in `deploy/.env`. Edit with `nano .env`, then apply:
`docker compose up -d <service>` (most), or rebuild for **build-time** vars (see ⚠️ rows).

---

## 1. Minimum config to test (the short list)

To exercise **auth + RBAC + list/read** (no external API keys needed):

| Key | Set to | Why |
|---|---|---|
| `OIDC_DEV_MODE` | `true` | Accept self-minted HS256 dev tokens (no live IdP) |
| `NEXT_PUBLIC_DEV_MODE` | `true` | ⚠️ build-time — shows the "Dev token" box on `/login` |
| `ORCH_SECRET_KEY` | `openssl rand -hex 32` output | Signs/validates dev tokens **and** derives BYOK encryption. Keep stable. |
| `ENVIRONMENT` | `development` | Enables dev-mode behaviors |
| `PUBLIC_BASE_URL` | `https://notebook.umarsyukri.com` | Correct links/redirects |
| `POSTGRES_PASSWORD` / `DATABASE_URL` | a real password (matching in both) | System of record |

To additionally test **ingest → outline → generate**, you also need the LLM + engine keys in §2–§4
**and** the two blockers in §6 resolved.

> ⚠️ **Build-time vars** (`NEXT_PUBLIC_*`) are baked into the browser bundle. Changing them requires:
> `docker compose build --no-cache frontend && docker compose up -d --force-recreate frontend`.
> All other vars are runtime — `docker compose up -d <service>` is enough.

---

## 2. App LLM — DeepSeek (BYOK, product-facing)

The model the product uses for analysis + slide generation.

| Key | Example | Notes |
|---|---|---|
| `DEEPSEEK_API_KEY` | `sk-...` | **Required for generation.** Get from <https://platform.deepseek.com>. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible endpoint |
| `DEEPSEEK_MODEL` | `deepseek-chat` | |

> Per-tenant BYOK is set via the API (`PUT /api/v1/tenant/llm-config`, admin) or by `seed_qa` using
> the `QA_LLM_*` vars (§7). These `DEEPSEEK_*` values are the stack-level default/engine config.

---

## 3. Embeddings (Open Notebook needs them; DeepSeek has none)

Pick **one**:

| Option | Keys | Notes |
|---|---|---|
| **A — local (default, data stays on VPS)** | `OLLAMA_URL=http://ollama:11434`, `EMBEDDING_MODEL=bge-m3` | Pull once: `docker compose exec ollama ollama pull bge-m3` |
| **B — external** | `OPENAI_API_KEY=sk-...` (or Mistral/Voyage) | Set instead of Ollama |

---

## 4. Presenton — slide rendering engine

| Key | Example | Notes |
|---|---|---|
| `PRESENTON_URL` | `http://presenton:80` | Internal only |
| `PRESENTON_AUTH_USERNAME` | `admin` | |
| `PRESENTON_AUTH_PASSWORD` | strong value | Not `changeme` |
| `PRESENTON_CAN_CHANGE_KEYS` | `false` | |
| `IMAGE_PROVIDER` | `pexels` | or `dall-e-3` / `gemini_flash` |
| `PEXELS_API_KEY` | `...` | Required when `IMAGE_PROVIDER=pexels`. Free key: <https://www.pexels.com/api/>. Swap key if you change provider. |

> ⚠️ Presenton currently **crash-loops** on this VPS — see §6.

---

## 5. Infra & internal engines (usually leave as compose defaults)

| Area | Keys |
|---|---|
| Orchestrator | `LOG_LEVEL` (`INFO`) |
| PostgreSQL | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` |
| Redis | `REDIS_URL=redis://redis:6379/0` |
| MinIO (object store) | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`, `MINIO_ENDPOINT` |
| Open Notebook | `OPEN_NOTEBOOK_URL=http://open-notebook:5055`, `OPEN_NOTEBOOK_ENCRYPTION_KEY` |
| SurrealDB (ON storage) | `SURREAL_USER`, `SURREAL_PASSWORD`, `SURREAL_NAMESPACE`, `SURREAL_DATABASE` |
| OIDC (prod IdP) | `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUDIENCE` — *ignored while `OIDC_DEV_MODE=true`* |
| Frontend (public) | `NEXT_PUBLIC_API_BASE=/api/v1`, `NEXT_PUBLIC_OIDC_*`, `NEXT_PUBLIC_DEV_MODE` |

> All `change-me` / `changeme` placeholders must be replaced before anything but auth/RBAC works.
> Quick audit: `grep -nE 'change-?me' deploy/.env`.

---

## 6. Known blockers for end-to-end testing

| Blocker | Symptom | Status |
|---|---|---|
| **Open Notebook API mismatch** | `POST /api/v1/notebooks` → **404**; project-create → **502** | Code gap — orchestrator client pinned to a path the real image doesn't serve. Blocks create/ingest. |
| **Presenton crash-loop** | `docker compose ps` → `presenton Restarting` | Blocks generation/export; `orchestrator depends_on: [presenton]`. Check `docker compose logs presenton`. |

Until both are resolved, the generation chain (create → upload → outline → generate → download)
cannot complete. Auth, RBAC, list/read, and cross-tenant isolation are fully testable. See
[TESTING-USERS-AND-RBAC.md §6](TESTING-USERS-AND-RBAC.md#6-known-blockers-read-before-testing-generation).

---

## 7. QA seed variables (for `scripts/seed_qa.py`)

Not stored in `.env` — pass at seed time so test tenants get a working BYOK provider:

| Var | Example | Effect |
|---|---|---|
| `QA_LLM_API_KEY` | `sk-...` | **Omit → BYOK left unset**, generation fails *by design* (TC-08) |
| `QA_LLM_BASE_URL` | `https://api.deepseek.com/v1` | Provider endpoint |
| `QA_LLM_MODEL` | `deepseek-chat` | Model |
| `QA_LLM_PROVIDER` | `deepseek` | Provider label (default) |

```bash
export QA_LLM_API_KEY="sk-..." QA_LLM_BASE_URL="https://api.deepseek.com/v1" QA_LLM_MODEL="deepseek-chat"
docker compose exec -e QA_LLM_API_KEY -e QA_LLM_BASE_URL -e QA_LLM_MODEL \
  orchestrator python -m scripts.seed_qa
```

---

## 8. Apply & verify changes

```bash
# After editing .env:
docker compose up -d orchestrator worker          # runtime vars (backend)
# For NEXT_PUBLIC_* (build-time):
docker compose build --no-cache frontend && docker compose up -d --force-recreate frontend

# Verify a value actually reached a container:
docker compose exec orchestrator env | grep -E 'OIDC_DEV_MODE|ORCH_SECRET_KEY|DEEPSEEK_API_KEY'

# Health snapshot:
docker compose ps
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: notebook.umarsyukri.com" http://127.0.0.1:8181/   # want 200/307
```

> **Security:** `.env` holds live secrets — never commit it (`.gitignore` it). Rotate
> `ORCH_SECRET_KEY` before going public; rotating it invalidates all previously minted dev tokens.
> `OIDC_DEV_MODE=true` is for testing only — anyone with `ORCH_SECRET_KEY` can mint a token for any
> seeded user. Wire real SSO (`OIDC_*` + `OIDC_DEV_MODE=false`) before exposing this beyond QA.
