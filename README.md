# NoteAI — Presentation Notebook LLM with Configurable Slides

**NoteAI** (rebranded from Maru) is a stakeholder-tailored presentation generation engine built on top of a Retrieval-Augmented Generation (RAG) workspace. It transforms local documents and project notes into professional, branded slide decks (`.pptx` and `.pdf`) using the **Presenton** engine.

---

## 🌟 Key Features & Highlights

### 1. 🎨 Fresh & Premium Visual Identity (NoteAI)
- **Modern Aesthetics**: Built with a clean white background, vibrant **Blue-600 (`#2563EB`)** primary palette, and curated typography (**Inter** and **JetBrains Mono**).
- **Human-Crafted UI**: Replaced AI-generated placeholder layouts with premium card-based containers, subtle micro-animations (`shadow-elevated`, hover transitions), and dark-themed navigation sidebars (`bg-ink`).

### 2. 🛠️ Rich Template Configuration (`/templates`)
- **4-Section Wizard**: Configure templates across *General Settings*, *Brand & Aesthetics*, *Layout & Formatting*, and *Base Template Upload*.
- **Live Brand Tokens**: Visual color pickers for Primary, Secondary, and Accent colors, along with font typography selectors.
- **Custom PPTX Uploads**: Upload custom `.pptx` base decks directly to the Presenton engine. All configuration is bundled into clean `brand_tokens` payloads.

### 3. 👥 Stakeholder Profile Manager (`/profiles`)
- **Card & Grid Layout**: Clean grid-based editor to define target audience, presentation tone (e.g., professional, persuasive, concise), verbosity, and slide count limits.
- **Interactive Section Structure Builder**: Build custom slide outlines and talking points with interactive reordering (↑/↓) and deletion controls.

### 4. 🚀 3-Pane Workspace & Studio Panel (`/projects`)
- **Interactive Workspace**: Seamlessly manage **Sources** (file uploads & URLs), interact with **Guide & Chat Panel** (with distinct blue vs. gray bubble styling), and generate presentations in the **Studio Panel**.
- **Live Generation Tracking**: Real-time status badges (*Generating* 🟡, *Ready* 🟢, *Failed* 🔴) with instant browser downloads for `.pptx` and `.pdf` exports.

### 5. 📊 Usage Dashboard & Quotas (`/usage`)
- **Stat Cards**: Monitor generations, token consumption (In/Out), and estimated costs at a glance with iconography.
- **Animated Quota Indicator**: Real-time progress bar tracking monthly generation limits.
- **Audit Logs**: Filterable, cleanly styled data tables tracking usage by user and organization.

### 6. 🌐 Bilingual Localization
- Complete OIDC and UI localization supporting both **English (`en`)** and **Bahasa Indonesia (`id`)**.

---

## 🏗️ Architecture & Tech Stack

- **Frontend**: Next.js 14 (App Router), React 18, Vanilla Tailwind CSS, TypeScript, i18n localization.
- **Backend**: FastAPI (Python 3.11+), Alembic, Object Store integration, Presenton presentation generation engine.
- **Authentication**: OIDC SSO integration with local developer fallback mode (`DEV_MODE`).

---

## 🚦 Quickstart & Local Development

### Prerequisites
- Node.js 20+ & npm
- Python 3.11+ & virtualenv / Poetry
- Docker & Docker Compose (optional, for full containerized deployment)

### 1. Run Backend API Server
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt # or pip install -e .
pytest tests/                   # Run backend integration tests
python src/main.py              # Start FastAPI server on :8000
```

### 2. Run Frontend Web App
```bash
cd frontend
npm install
npm run dev                     # Start Next.js dev server on :3000
```

---

## 🧪 Testing

Three tiers, each of which executes real code. **What they cover is stated honestly below** — see [revamp/TECH-DEBT.md](./revamp/TECH-DEBT.md) for what is knowingly untested.

```bash
# Backend — unit, integration, contract (SQLite-backed, no engines required)
cd backend && ./.venv/bin/python -m pytest tests/ -q --cov=src

# Frontend — Vitest + React Testing Library
cd frontend && npm run test:coverage

# End-to-end smoke — needs a RUNNING stack
docker compose -f deploy/docker-compose.lite.yml up -d
cd frontend && E2E_BASE_URL=http://localhost:8099 npm run test:e2e
```

| Tier | Location | Covers |
|---|---|---|
| Backend | `backend/tests/` | Tenant + engine isolation, quota/metering, the LLM client, health, ingestion, generation |
| Frontend | `frontend/src/**/*.test.ts(x)` | API client, URL resolution, download, section builder, en/id key parity |
| E2E smoke | `frontend/e2e/smoke/` | Shell, project lifecycle, generation + download, editor, branding |

**Two E2E journeys (`04-editor`, `05-branding`) skip rather than pass** while the Presenton engine is not vendored — they report as skipped, never as green.

> **A note on the previous suite.** Earlier versions of this README cited
> `automation/verify_noteai_revamp.py` as evidence of "100% pass across 26 criteria".
> That script asserted that *source files matched regex patterns* — it started no
> server and issued no request. It reported success while `/editor` returned 404,
> downloads were unreachable from a browser, branding never reached the renderer, and
> retrieval leaked across projects. It has been deleted; the archived report it produced
> carries a banner to the same effect.

---
*Developed by CSC Deathings / NoteAI Team.*
