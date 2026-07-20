# NotebookLLM-Lite — Deploy on Hostinger VPS (KVM2)

This guide assesses running the **lite** demo stack on a Hostinger **KVM2** VPS and
gives the exact pre-deploy configuration steps. It complements
[`DEPLOY-LITE.md`](./DEPLOY-LITE.md) (which explains the stack itself); this file is
the VPS-specific runbook.

---

## 1. Status recap (what you're deploying)

- Single-tenant **demo** build: no login, no quotas (`LITE_MODE=true`).
- LLM (outline + analysis + slides) → **OpenRouter**; embeddings → **OpenAI**.
- **No GPU and no local model** — all inference is offloaded to APIs.
- 11 containers: `traefik, frontend, orchestrator, worker, init, postgres, redis,
  minio, surrealdb, open-notebook, presenton`.
- Files: `deploy/docker-compose.lite.yml`, `deploy/.env.lite.example`.
- Repo: `github.com/cscreathings-maru/notebookwithconfigurableslides`.

---

## 2. KVM2 capacity assessment

### Hostinger KVM2 specs (confirm in hPanel — plans change)

| Resource | KVM2 (typical) |
|---|---|
| vCPU | 2 cores |
| RAM | 8 GB |
| Disk | 100 GB NVMe |
| Bandwidth | 8 TB |
| IPv4 | 1 dedicated |

### Estimated stack footprint (idle → under load)

| Service | RAM idle | RAM under load | Notes |
|---|---|---|---|
| postgres | ~150 MB | ~300 MB | small demo data |
| redis | ~30 MB | ~60 MB | job queue |
| minio | ~150 MB | ~300 MB | object storage |
| surrealdb | ~120 MB | ~250 MB | Open Notebook store |
| open-notebook | ~300 MB | ~600 MB | analysis, calls APIs |
| **presenton** | ~400 MB | **~1–1.5 GB** | **wildcard**: PPTX/PDF render can spike |
| orchestrator | ~200 MB | ~400 MB | FastAPI |
| worker | ~200 MB | ~400 MB | Arq jobs |
| frontend | ~150 MB | ~300 MB | Next.js standalone |
| traefik | ~40 MB | ~60 MB | proxy |
| **Total** | **~1.8 GB** | **~4–4.5 GB** | one active generation |

### Verdict

| Dimension | KVM2 | Assessment |
|---|---|---|
| **RAM (8 GB)** | ✅ workable | Fine for 1–2 concurrent users. Add **swap** (below) as a safety net for PPTX-export spikes. |
| **CPU (2 vCPU)** | ✅ ok | Heavy lifting is on OpenRouter/OpenAI. The only CPU hog is the **Docker image build** (Next.js) — slow but fine once. |
| **Disk (100 GB)** | ✅ plenty | Images ~6–10 GB + data. No concern. |
| **GPU** | ✅ N/A | Not needed — no local models. |
| **Concurrency** | ⚠️ limited | Good for a **demo / handful of users**. Not for a public launch — that's the SaaS build's job. |

**Bottom line:** KVM2 is a fit for this demo. If you expect several people generating
decks at once, size up to **KVM4** (4 vCPU / 16 GB). For 1-at-a-time demoing, KVM2 is fine.

---

## 3. ⚠️ Critical security decision (read before anything else)

**Lite mode has NO authentication.** Whoever can reach the app is an admin and can
run generations against **your** OpenRouter/OpenAI keys (i.e. spend your money).
The compose binds Traefik to `127.0.0.1:8080` (localhost only) on purpose. Pick one
exposure model:

| Option | Use when | Public? | Auth |
|---|---|---|---|
| **A. SSH tunnel (recommended)** | Private demo, just you / your team | No | SSH keys |
| **B. Domain + TLS + Basic Auth** | You need to share a URL | Yes | Traefik basic auth over HTTPS |

Do **not** simply publish port 8080 to the internet with no auth. Section 8 covers
both options.

---

## 4. Pre-deploy configuration — step by step

### 4.1 Provision & log in

1. In hPanel, deploy the VPS with **Ubuntu 24.04 LTS** (clean, no panel needed).
2. SSH in as root:
   ```bash
   ssh root@YOUR_VPS_IP
   ```

### 4.2 Create a non-root user

```bash
adduser deploy
usermod -aG sudo deploy
# copy your SSH key to the new user:
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```
Then reconnect as `deploy`: `ssh deploy@YOUR_VPS_IP`.

### 4.3 Harden SSH + firewall (UFW)

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
# For Option B (public) only, also:
# sudo ufw allow 80/tcp
# sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```
> For **Option A (SSH tunnel)** you do NOT open 80/443 — only SSH. That's the whole
> point: nothing is publicly reachable.

### 4.4 Add swap (safety net for RAM spikes)

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # confirm 4.0Gi swap
```

### 4.5 Install Docker + Compose plugin

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
newgrp docker           # apply group without re-login
docker version
docker compose version  # must be v2.20+ (for service_completed_successfully)
```

### 4.6 Clone the repo

```bash
cd ~
git clone https://github.com/cscreathings-maru/notebookwithconfigurableslides.git app
cd app
# (adjust if your default branch differs)
```

### 4.7 Create and fill the env file

```bash
cp deploy/.env.lite.example deploy/.env.lite
nano deploy/.env.lite
```

Fill **at minimum** (see `.env.lite.example` for the full list):

| Variable | Set to |
|---|---|
| `OPENROUTER_API_KEY` | your OpenRouter key |
| `OPENROUTER_MODEL` | exact slug, e.g. `deepseek/deepseek-chat-v3` |
| `OPENAI_API_KEY` | your OpenAI key (embeddings) |
| `PEXELS_API_KEY` | your Pexels key |
| `ORCH_SECRET_KEY` | `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` + `DATABASE_URL` | matching strong password |
| `MINIO_ROOT_PASSWORD` | strong password |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` | `openssl rand -hex 16` |
| `PRESENTON_AUTH_PASSWORD` | strong password |
| `PUBLIC_BASE_URL` | Option A: `http://localhost:8080` · Option B: `https://your.domain` |

Generate secrets quickly:
```bash
echo "ORCH_SECRET_KEY=$(openssl rand -hex 32)"
echo "OPEN_NOTEBOOK_ENCRYPTION_KEY=$(openssl rand -hex 16)"
```
> **Never commit `deploy/.env.lite`.** It is git-ignored.

---

## 5. Build & launch

Because KVM2 has 2 vCPU, the first build (Next.js + pip) takes ~10–20 min. Run it
in a resilient session so an SSH drop doesn't kill it:

```bash
sudo apt -y install tmux
tmux new -s deploy

docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d --build
# detach from tmux: Ctrl-b then d
```

Watch the one-shot migrate+seed, then health:
```bash
docker compose -f deploy/docker-compose.lite.yml logs -f init
docker compose -f deploy/docker-compose.lite.yml ps
```

### 5.1 One-time: Open Notebook embeddings check

Confirm embeddings are on OpenAI (OpenRouter can't do them) per
[`DEPLOY-LITE.md` §4.1](./DEPLOY-LITE.md). Temporarily uncomment the
`open-notebook` `ports:` line, verify at `http://localhost:8502` **via an SSH
tunnel** (never open 8502 to the internet), then re-comment and `up -d`.

---

## 6. Access the app

### Option A — SSH tunnel (recommended for a private demo)

On **your laptop** (not the VPS):
```bash
ssh -L 8080:localhost:8080 deploy@YOUR_VPS_IP
```
Leave that terminal open, then browse to **http://localhost:8080** locally. Traffic
is encrypted by SSH; nothing is exposed publicly. This needs **no domain, no TLS,
no extra auth** — ideal for confirming the demo before you finalize the SaaS.

### Option B — Public URL with TLS + Basic Auth

Only if you must share a link. This requires editing the compose (kept out of the
committed file so the default stays safe). Do all of this:

1. **DNS:** point an A record `notebook.yourdomain.com → YOUR_VPS_IP`.
2. **Open the firewall:** `sudo ufw allow 80/tcp && sudo ufw allow 443/tcp`.
3. **Create an override** `deploy/docker-compose.vps.yml`:
   ```yaml
   services:
     traefik:
       command:
         - "--providers.docker=true"
         - "--providers.docker.exposedbydefault=false"
         - "--entrypoints.web.address=:80"
         - "--entrypoints.websecure.address=:443"
         - "--certificatesresolvers.le.acme.email=you@example.com"
         - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
         - "--certificatesresolvers.le.acme.tlschallenge=true"
         - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
       ports:
         - "80:80"
         - "443:443"
       volumes:
         - "letsencrypt:/letsencrypt"
     frontend:
       labels:
         - "traefik.http.routers.frontend.rule=Host(`notebook.yourdomain.com`)"
         - "traefik.http.routers.frontend.entrypoints=websecure"
         - "traefik.http.routers.frontend.tls.certresolver=le"
         - "traefik.http.routers.frontend.middlewares=demo-auth"
         - "traefik.http.middlewares.demo-auth.basicauth.users=USER:HTPASSWD_HASH"
     orchestrator:
       labels:
         - "traefik.http.routers.api.rule=Host(`notebook.yourdomain.com`) && PathPrefix(`/api`)"
         - "traefik.http.routers.api.entrypoints=websecure"
         - "traefik.http.routers.api.tls.certresolver=le"
         - "traefik.http.routers.api.middlewares=demo-auth"
   volumes:
     letsencrypt:
   ```
4. **Generate the basic-auth hash** and paste it into `HTPASSWD_HASH` above
   (escape `$` as `$$` inside compose):
   ```bash
   sudo apt -y install apache2-utils
   htpasswd -nbB demo 'your-strong-password'
   ```
5. **Rebuild the frontend** so the browser calls the same origin — set
   `PUBLIC_BASE_URL=https://notebook.yourdomain.com` in `deploy/.env.lite`, then:
   ```bash
   docker compose -f deploy/docker-compose.lite.yml -f deploy/docker-compose.vps.yml \
     --env-file deploy/.env.lite up -d --build
   ```
   HTTPS + a login prompt now guard the app. `NEXT_PUBLIC_API_BASE=/api/v1` stays
   same-origin, so no CORS changes are needed.

---

## 7. Verify it works

1. Open the app (tunnel or URL) → you land in **Projects**, no login (lite).
2. New project → upload a small PDF → source goes `queued→processing→ready`.
3. Create + approve a Profile → Build outline → Generate → download PPTX/PDF.
4. Confirm spend shows up in your **OpenRouter dashboard** (the app sends
   `HTTP-Referer`/`X-Title`).

---

## 8. Operations

```bash
# Logs
docker compose -f deploy/docker-compose.lite.yml logs -f worker

# Change model/keys (no rebuild): edit deploy/.env.lite, then
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d orchestrator worker presenton

# Update to latest code
git pull
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d --build

# Re-run migrations/seed (idempotent)
docker compose -f deploy/docker-compose.lite.yml run --rm init

# Full reset (wipes DB + storage + engine data)
docker compose -f deploy/docker-compose.lite.yml down -v
```

### Backups (worth doing before a demo)
```bash
# Postgres
docker compose -f deploy/docker-compose.lite.yml exec postgres \
  pg_dump -U orch orchestrator > backup_$(date +%F).sql
# MinIO data lives in the `minio_data` volume; snapshot with `docker run --rm -v ...`.
```

---

## 9. Cost & monitoring

- **VPS:** flat monthly (KVM2).
- **OpenRouter + OpenAI:** pay-per-use — this is the variable cost. Because lite has
  no quotas, **set spend limits in the OpenRouter and OpenAI dashboards** so a demo
  (or an exposed instance) can't run away with your balance.
- **Watch RAM:** `docker stats` during a generation. If Presenton pushes you near
  8 GB regularly, either the 4 GB swap absorbs it or you move to KVM4.

---

## 10. Recommendation summary

- ✅ **Deploy on KVM2 for the demo** — it fits, no GPU needed.
- ✅ **Use Option A (SSH tunnel)** while you're validating — safest, zero public
  surface, no auth wiring.
- ✅ **Add 4 GB swap** and **set API spend caps** before first run.
- ⚠️ **Never expose lite mode publicly without Option B's auth.**
- ⬆️ **Move to KVM4 + the full SaaS build** (`LITE_MODE=false`, OIDC/RBAC back on)
  when you go past a private demo.
