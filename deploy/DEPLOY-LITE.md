# NotebookLLM-Lite — Deployment Guide (demo build)

This guide brings up the **lite** version of the platform: single-tenant, **no
login**, **no quotas/usage metering**, with every LLM call routed to **OpenRouter**
and document embeddings served by **OpenAI**. It's meant to demo the full pipeline
(upload → analyze → outline → generate PPTX/PDF) before you finalize the SaaS.

The full multi-tenant SaaS is **not deleted** — it's toggled off by `LITE_MODE`.
Flip the flag back and the OIDC/RBAC/BYOK/metering path returns unchanged.

---

## 1. What runs (and what's gone)

| Service | Role | In lite? |
|---|---|---|
| `traefik` | Single entrypoint, path-routes `/` and `/api` | ✅ |
| `frontend` | Next.js UI (static admin session) | ✅ |
| `orchestrator` | FastAPI API | ✅ |
| `worker` | Arq async jobs (ingest/generate) | ✅ |
| `init` | One-shot: DB migrate + seed default workspace | ✅ (runs once, exits) |
| `postgres` | System of record | ✅ |
| `redis` | Job queue | ✅ |
| `minio` | Object storage (uploads + decks) | ✅ |
| `surrealdb` | Open Notebook's internal store | ✅ |
| `open-notebook` | Ingestion + analysis engine | ✅ |
| `presenton` | Slide generation engine | ✅ |
| ~~`ollama`~~ | Local embeddings | ❌ removed (OpenAI embeddings instead) |
| ~~Keycloak/OIDC~~ | SSO / auth | ❌ not used (`LITE_MODE=true`) |

---

## 2. Prerequisites

- **Docker** + **Docker Compose v2** (`docker compose version` ≥ 2.20 for
  `service_completed_successfully`).
- **~6 GB free RAM** for the full stack.
- API keys:
  - **OpenRouter** key — https://openrouter.ai/keys (the product LLM).
  - **OpenAI** key — for Open Notebook embeddings (OpenRouter has no embeddings API).
  - **Pexels** key (free) — slide images, or switch `IMAGE_PROVIDER`.

---

## 3. Configuration

All configuration lives in **`deploy/.env.lite`**. Start from the template:

```bash
cp deploy/.env.lite.example deploy/.env.lite
```

Then edit `deploy/.env.lite`. The variables that **must** change before first run:

| Variable | What to set | Why |
|---|---|---|
| `OPENROUTER_API_KEY` | your OpenRouter key | outline + analysis + slides |
| `OPENROUTER_MODEL` | exact model slug (see §3.1) | which model the demo uses |
| `OPENAI_API_KEY` | your OpenAI key | Open Notebook embeddings |
| `PEXELS_API_KEY` | your Pexels key | slide imagery |
| `ORCH_SECRET_KEY` | long random string | at-rest crypto helpers |
| `POSTGRES_PASSWORD` / `DATABASE_URL` | matching password | DB auth |
| `MINIO_ROOT_PASSWORD` | strong password | object storage auth |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` | random string | engine at-rest crypto |
| `PRESENTON_AUTH_PASSWORD` | strong password | engine admin |

> **Never commit `deploy/.env.lite`.** Only `.env.lite.example` (no secrets) is tracked.

### 3.1 Choosing the model (`OPENROUTER_MODEL`)

This is the single knob for the LLM — the orchestrator (`get_config()`) and
Presenton both read it. Set it to an **exact OpenRouter slug**. Verify the slug
exists in the OpenRouter model list before deploying; a wrong slug returns a 400
from the provider. Examples:

```
OPENROUTER_MODEL=deepseek/deepseek-chat-v3     # general DeepSeek chat
OPENROUTER_MODEL=deepseek/deepseek-r1          # reasoning variant
```

To swap models later, change this one value and restart — no rebuild of the
backend is needed (`docker compose ... up -d orchestrator worker presenton`).

### 3.2 Config that is baked at BUILD time (frontend)

`NEXT_PUBLIC_*` values are compiled into the browser bundle, so changing them
requires **rebuilding the frontend image** (`--build`). These are already wired
as build args in `docker-compose.lite.yml`:

- `NEXT_PUBLIC_LITE_MODE=true` — static admin session, no login wall
- `NEXT_PUBLIC_DEFAULT_TENANT_NAME` — workspace name shown in the sidebar
- `NEXT_PUBLIC_API_BASE=/api/v1` — same-origin via Traefik (leave as-is)

### 3.3 Backend ↔ frontend lite flags must agree

| Flag | Where | Must be |
|---|---|---|
| `LITE_MODE` | backend (`deploy/.env.lite`) | `true` |
| `NEXT_PUBLIC_LITE_MODE` | frontend build arg | `true` |

If the backend is lite but the frontend isn't, the UI will try to hit `/auth/me`
with a token it never obtained. Keep them in sync.

---

## 4. Bring it up

```bash
cd "NotebookLLM-custom copy"

docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d --build
```

Startup order is handled for you:
1. `postgres`, `redis`, `minio`, `surrealdb` start.
2. `init` runs `alembic upgrade head` then `python -m scripts.seed_lite`
   (creates the default tenant + admin), then **exits**.
3. `orchestrator` and `worker` start only after `init` succeeds.
4. `frontend` starts after the orchestrator.

Watch progress:

```bash
docker compose -f deploy/docker-compose.lite.yml logs -f init          # migrate + seed
docker compose -f deploy/docker-compose.lite.yml ps                    # service health
```

Open **http://localhost:8080** — you land straight in the Projects workspace, no
login.

### 4.1 One-time: configure Open Notebook embeddings

The orchestrator passes the **analysis LLM** (OpenRouter) to Open Notebook per
request, but Open Notebook manages its **embeddings** provider internally. The
compose passes `OPENAI_API_KEY` and `EMBEDDING_MODEL` to the engine; confirm they
took effect on first run:

1. Temporarily expose the engine — uncomment the `ports:` line under
   `open-notebook` in `docker-compose.lite.yml`, then
   `docker compose -f deploy/docker-compose.lite.yml up -d open-notebook`.
2. Open its UI at **http://localhost:8502**, and under model/provider settings
   confirm the embeddings provider is **OpenAI** with model
   `text-embedding-3-small` (or your choice).
3. Re-comment the `ports:` line and `up -d` again to re-close the engine.

> If ingestion jobs fail with an embeddings error, this is the first thing to check.

---

## 5. Smoke test the pipeline

1. **Projects → New project.**
2. **Add a source** — upload a small PDF (or paste a URL). Watch the source move
   `queued → processing → ready` (the worker + Open Notebook are doing analysis;
   embeddings hit OpenAI, analysis hits OpenRouter).
3. **Create a Profile** (Profiles) and **approve** it; it references a Template.
4. **Build the outline** on the project (uses OpenRouter via the orchestrator).
5. **Generate** — Presenton renders slides via OpenRouter.
6. **Download** the PPTX and PDF.

Verify OpenRouter is actually being hit:

```bash
docker compose -f deploy/docker-compose.lite.yml logs orchestrator | grep -i outline
```

and confirm requests appear in your OpenRouter dashboard (the app sends
`HTTP-Referer` / `X-Title` for attribution).

---

## 6. Common operations

**Change the model or any key** (no rebuild):
```bash
# edit deploy/.env.lite, then:
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d orchestrator worker presenton
```

**Re-run migrations / re-seed** (idempotent):
```bash
docker compose -f deploy/docker-compose.lite.yml run --rm init
```

**Reset everything (wipes DB, storage, engine data):**
```bash
docker compose -f deploy/docker-compose.lite.yml down -v
```

**Tail a service:**
```bash
docker compose -f deploy/docker-compose.lite.yml logs -f worker
```

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| UI shows blank / redirects oddly | frontend built without `NEXT_PUBLIC_LITE_MODE=true` | rebuild: `up -d --build frontend` |
| `/api/v1/...` 500 on first generation | default tenant not seeded | `docker compose ... run --rm init` |
| Outline/generate 400 from provider | bad `OPENROUTER_MODEL` slug or missing key | fix `deploy/.env.lite`, restart |
| Source stuck in `processing`, then `failed` | embeddings misconfigured (OpenAI) | see §4.1 |
| Presenton export fails | `CUSTOM_MODEL`/key wrong, or image provider key missing | check `presenton` logs + keys |
| `init` exits non-zero | Postgres not ready / bad `DATABASE_URL` | check `postgres` logs, password match |

---

## 8. Security notes for the demo

- Traefik binds to **127.0.0.1:8080** only — the stack is not exposed off the
  host. To demo from another machine, front it with your own reverse proxy/TLS;
  do **not** publish it raw.
- Lite mode has **no authentication** by design. Anyone who reaches port 8080 is
  an admin. Keep it local or behind a trusted network only.
- Engines (`open-notebook`, `presenton`, `postgres`, `redis`, `minio`,
  `surrealdb`) publish **no host ports**; only Traefik does.
- Secrets live only in `deploy/.env.lite` (git-ignored) and are never sent to the
  browser.

---

## 9. Going back to full SaaS

Nothing was removed — to re-enable the multi-tenant platform:

1. Set `LITE_MODE=false` (backend) and `NEXT_PUBLIC_LITE_MODE=false` (frontend build arg).
2. Restore the OIDC vars (`OIDC_ISSUER`, `OIDC_CLIENT_ID`, …) and per-tenant BYOK.
3. Use the original `deploy/docker-compose.yml` (Keycloak/Authentik + Ollama as needed).
4. Seed real tenants with `scripts/seed_tenant.py` instead of `scripts/seed_lite.py`.

The auth/RBAC/quota/BYOK code paths reactivate automatically once `LITE_MODE` is off.
