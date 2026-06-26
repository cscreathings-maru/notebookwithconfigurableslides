# Quickstart — Local Bring-Up

Goal: run the whole stack locally with Docker Compose, then exercise the upload → analyze →
generate loop. Everything runs on a private Docker network; only the orchestrator and frontend are
exposed.

## Prerequisites

- Docker + Docker Compose
- A DeepSeek API key (or other provider) for the LLM
- (For MetaGPT codegen, separately) Python 3.9–3.11, Node.js + pnpm — see `metagpt/OPERATOR-GUIDE.md`

## 1. Configure

```bash
cd deploy
cp .env.example .env
# edit .env: set DEEPSEEK_API_KEY, AUTH_USERNAME/PASSWORD for Presenton,
# Postgres/MinIO creds, and a Presenton/Open Notebook secret.
```

## 2. Start the stack

```bash
docker compose up -d
docker compose ps        # all services healthy
```

Services: `orchestrator` (FastAPI), `frontend` (Next.js), `postgres`, `redis`, `minio`,
`open-notebook` (+`surrealdb`), `presenton`, `traefik`. Only `frontend`/`orchestrator` (via
Traefik) are public; the engines are internal.

## 3. Initialize

```bash
# run DB migrations
docker compose exec orchestrator alembic upgrade head
# seed a tenant + admin (script provided by Slice 0)
docker compose exec orchestrator python -m scripts.seed_tenant --name "Acme" --admin you@acme.id
```

## 4. Smoke test the loop

1. Open the frontend, sign in via OIDC as the seeded admin.
2. Create a project; upload a sample PDF; wait for the source to reach `ready`.
3. As admin, create a template and a "Group Management" stakeholder profile.
4. As author, build an outline for that profile, review it, generate.
5. Download the resulting PPTX and PDF.

## 5. Verify isolation

Create a second tenant; confirm its user cannot list or fetch the first tenant's project,
generation, or download URL (expect 404).

## Health & troubleshooting

- `GET /api/v1/auth/me` — orchestrator up + session valid.
- Engine reachability is internal-only; check `docker compose logs open-notebook presenton`.
- Long jobs: poll `GET /api/v1/jobs/{id}` for progress.
- Open Notebook API docs (internal): `http://open-notebook:5055/docs`.
- Presenton generate endpoint (internal): `POST /api/v1/ppt/presentation/generate` (HTTP Basic).
