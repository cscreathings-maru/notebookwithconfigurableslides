# Run on Windows — step-by-step

How to develop this project on your local Windows PC with the multi-model loop (Claude plans,
DeepSeek codes), then deploy to your VPS later. Nothing here changes the architecture — only the
host. The same `deploy/docker-compose.yml` runs locally and on the VPS.

> **Strong recommendation: use WSL2 (Ubuntu) for everything.** It makes Docker, the bash helper
> scripts, Aider, and Python "just work," and avoids Windows path/line-ending headaches. Steps
> below assume WSL2; native-PowerShell notes are called out where they differ.

---

## Part A — One-time setup

### A1. Install WSL2 + Ubuntu
In **PowerShell (Admin)**:
```powershell
wsl --install -d Ubuntu
```
Reboot if prompted, then open **Ubuntu** from the Start menu and create your Linux user. Do the
rest inside this Ubuntu shell.

### A2. Install Docker Desktop
Install Docker Desktop for Windows, and in **Settings → Resources → WSL Integration**, enable your
Ubuntu distro. Verify in Ubuntu:
```bash
docker --version && docker compose version
```

### A3. Install dev tools (inside Ubuntu)
```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git
# Node + pnpm
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
sudo npm i -g pnpm
```

### A4. Install Aider (the build-loop orchestrator)
```bash
python3.11 -m pip install --user pipx && python3.11 -m pipx ensurepath
pipx install aider-chat
aider --version
```

### A5. Get your API keys
- **Anthropic (Claude)** — planning/architect + review. https://console.anthropic.com
- **DeepSeek** — coding + the app runtime. https://platform.deepseek.com
- **Pexels** (free) — Presenton slide images. https://www.pexels.com/api
Keep dev-loop keys and app-runtime keys separate (two `.env` files, below).

### A6. Create your code repo
Keep the **Spec Kit docs** (this folder) and the **code** as separate git repos.
```bash
mkdir -p ~/code/notebookllm-platform/{backend,frontend,deploy}
cd ~/code/notebookllm-platform && git init
# copy the deploy files from this project into the code repo:
cp /mnt/c/Users/<you>/www/spec-kit/Project/NotebookLLM-custom/deploy/docker-compose.yml deploy/
cp /mnt/c/Users/<you>/www/spec-kit/Project/NotebookLLM-custom/deploy/.env.example deploy/
cp /mnt/c/Users/<you>/www/spec-kit/Project/NotebookLLM-custom/automation/aider.conf.example.yml .aider.conf.yml
cp /mnt/c/Users/<you>/www/spec-kit/Project/NotebookLLM-custom/automation/.env.example .env
```
(Your Windows files are under `/mnt/c/...` inside WSL. Adjust `<you>`.)

### A7. Fill the two env files
- `~/code/notebookllm-platform/.env` → dev-loop keys: `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`.
- `~/code/notebookllm-platform/deploy/.env` → app-runtime keys: `DEEPSEEK_API_KEY`, `PEXELS_API_KEY`,
  Postgres/MinIO/Presenton creds, OIDC, secrets. (Copy from `.env.example`, replace every `changeme`.)

---

## Part B — Bring up the engines + infrastructure (Docker)

You only need this running to *test* the app; pure code-writing with Aider doesn't require it.

```bash
cd ~/code/notebookllm-platform/deploy
docker compose up -d
docker compose ps                          # all healthy?
docker compose exec ollama ollama pull bge-m3   # one-time: embedding model for Open Notebook
```

**Configure Open Notebook providers (first run).** Open Notebook sets provider keys in its UI.
Temporarily expose it by uncommenting its `ports:` line in `docker-compose.yml`, `docker compose up -d`
again, open `http://localhost:8502` → **Settings → API Keys**: add **DeepSeek** (LLM) and point
embeddings at the local **Ollama** (`bge-m3`). Then re-comment the port and `up -d` once more so it's
internal again. Presenton is already configured for DeepSeek + Pexels via env — no UI step needed.

To stop / reset:
```bash
docker compose down            # stop
docker compose down -v         # stop AND wipe data volumes (fresh start)
```

---

## Part C — The build loop (how planning + DeepSeek coding actually work)

Repeat this for each slice, in order (`slice-0` → `slice-5`). The loop is: **I plan → DeepSeek
codes → tests run → I review the gate → you approve.**

### Step 1 — Get the slice plan (Claude / me)
Ask me here in Cowork, e.g. *"Give me the slice-0 change-plan."* I produce a concrete plan: exact
files to create, the acceptance checks, and the tests to write first. (This is the "Claude = brain /
planning" part.) You paste that plan, or just the slice prompt file, into Aider next.

### Step 2 — Run Aider so DeepSeek writes the code
From the code repo, start Aider in architect mode. Claude drafts the approach; **DeepSeek writes the
actual code** and runs your tests:
```bash
cd ~/code/notebookllm-platform
# load dev keys for this shell:
export $(grep -v '^#' .env | xargs)

aider --architect \
  --model anthropic/claude-sonnet-4-5 \
  --editor-model deepseek/deepseek-chat \
  --test-cmd "pytest -q" --auto-test \
  --message-file "/mnt/c/Users/<you>/www/spec-kit/Project/NotebookLLM-custom/metagpt/prompts/slice-0-platform-skeleton.md"
```
What happens: Aider reads the slice requirement, the architect model plans, the editor model
(DeepSeek) edits files in the repo, then runs `pytest`; if tests fail it iterates until green. You
watch the proposed diffs and accept them. (`.aider.conf.yml` already sets these models, so you can
also just run `aider --message-file <slice>` once it's copied in.)

Tip: scope each run to the files a slice touches, e.g.
`aider backend/src/api/sources.py backend/src/workers/ingest.py --message-file slice-1...md`.

### Step 3 — Commit on a slice branch
```bash
git checkout -b slice-0
# Aider auto-commits each accepted change; or commit manually:
git add -A && git commit -m "slice-0: platform skeleton"
```

### Step 4 — Gate review (Claude / me = evaluation)
Bring the result back to me: paste the diff (`git diff main...slice-0`) or a failing test log. I
review it against `contracts/` and the constitution and run the **gate checklist** (isolation test,
engines stay internal, contracts honored, evals pass). I tell you pass or give exact fixes.

### Step 5 — Approve and continue
Pass → `git checkout main && git merge slice-0` → start the next slice. Fail → back to Step 2 with my
fix notes. After **slice-3** you have a working MVP (upload → analyze → generate).

---

## Part D — Running the app while you build it

Once a slice adds runnable code:
```bash
# backend (in one terminal)
cd ~/code/notebookllm-platform/backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e . && alembic upgrade head
uvicorn src.main:app --reload --port 8000

# frontend (in another terminal)
cd ~/code/notebookllm-platform/frontend
pnpm install && pnpm dev
```
Or run the whole thing via `docker compose up -d --build` once the Dockerfiles exist. Smoke test and
the isolation check are in `specs/001-presentation-notebook-llm/quickstart.md`.

---

## Part E — Later: deploy to the VPS

The same compose file runs on the VPS; what changes is hardening, not architecture:
1. Point a domain at the VPS; switch Traefik to TLS (Let's Encrypt) instead of plain `:80`.
2. Put real secrets in `deploy/.env` (rotate everything from the local `changeme` values).
3. Keep all the engine/db `ports:` lines commented (no public exposure) — only Traefik is public.
4. Set up automated backups for `pg_data`, `surreal_data`, `minio_data`, `presenton_data`.
5. `git pull` your code repo on the VPS, `docker compose up -d --build`, run `alembic upgrade head`.
6. (Optional) Move from a single VPS to multiple nodes only when load needs it — the orchestrator and
   workers are stateless by design, so this is mechanical.

---

## Quick reference

| Goal | Command |
|------|---------|
| Plan a slice | ask me: "slice-N change-plan" |
| Code a slice (DeepSeek) | `aider --architect --model anthropic/claude-sonnet-4-5 --editor-model deepseek/deepseek-chat --test-cmd "pytest -q" --auto-test --message-file <slice>` |
| Bring up stack | `cd deploy && docker compose up -d` |
| Pull embeddings model | `docker compose exec ollama ollama pull bge-m3` |
| Reset data | `docker compose down -v` |
| Gate review | paste `git diff` / test log back here |

## Common gotchas on Windows

- **Edit code inside WSL** (`~/code/...`), not on the Windows C: drive, for much faster file I/O.
- If Docker can't start: ensure **WSL2 backend** is on and virtualization is enabled in BIOS.
- Line endings: set `git config --global core.autocrlf input` to avoid CRLF noise in diffs.
- Engines failing LLM calls usually means the app network was marked `internal: true` — it must not
  be (the provided compose is already correct).
- Don't commit `.env` files — add them to `.gitignore`.
