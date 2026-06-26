# Implementation Plan: Presentation Notebook LLM Platform (MVP)

**Branch**: `001-presentation-notebook-llm` | **Date**: 2026-06-19 | **Spec**: ./spec.md

**Input**: Feature specification from `specs/001-presentation-notebook-llm/spec.md`

## Summary

Build a multi-tenant SaaS that turns uploaded business documents into stakeholder-tailored,
on-brand presentations. The system orchestrates two self-hosted engines — **Open Notebook**
(document ingestion, analysis, retrieval, chat) and **Presenton** (AI slide generation + PPTX/PDF
export) — behind a custom FastAPI orchestration service and a full Next.js frontend. The
orchestrator owns everything the engines don't: tenancy, RBAC, the versioned template/profile
registry, the deterministic outline contract that drives consistency, async job processing,
provenance, and cost metering. The engines are never exposed to clients. Deployment is Docker
Compose on a single VPS for the MVP, designed to scale out later.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator, matches both engines); TypeScript 5.x (frontend).

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy + Alembic, Arq or Celery (async jobs),
httpx (engine clients), Next.js 14 (App Router) + React + Tailwind CSS, an OIDC provider
(Keycloak or Authentik). Engines: Open Notebook (FastAPI/SurrealDB/LangChain) and Presenton
(FastAPI/Next.js), both via REST.

**Storage**: PostgreSQL (tenants, users, projects, profiles, templates, generations, usage/audit —
the system of record). SurrealDB stays as Open Notebook's internal store. Redis (queue/broker,
cache, idempotency). MinIO (S3-compatible object storage for uploads + generated PPTX/PDF).
Presenton `app_data` volume for its working state and templates.

**Testing**: pytest + httpx for unit/contract/integration; Playwright for frontend E2E; a custom
eval harness (golden inputs → structural assertions on generated decks).

**Target Platform**: Linux VPS, Docker Compose; all services containerized behind Traefik/Caddy.

**Project Type**: Web application (custom frontend + orchestration backend) integrating two
external API engines.

**Performance Goals (MVP pilot targets)**: document-to-deck p50 < 5 min and p95 < 10 min for a
15–25 page source set; support ~10–20 concurrent generations via the job queue; orchestrator API
p95 < 300 ms for non-generation endpoints.

**Constraints**: Self-hosted on one VPS (vertical scaling first); strict tenant isolation enforced
in our layer; engines on a private network only; BYOK per tenant with encrypted secrets; every
generation fully traceable.

**Scale/Scope (MVP)**: low tens of tenants, hundreds of users, thousands of generations; 3+
stakeholder profiles per tenant; PPTX + PDF output.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine Isolation** — PASS. Engines run on a private Docker network; only the orchestrator
  holds their URLs/credentials; no client-facing route reaches them.
- **II. Tenant Isolation & Data Sovereignty** — PASS by design. Tenant id is derived from the
  session and applied as a mandatory filter in every data-access path; uploads and artifacts live
  in tenant-prefixed object storage; provider/region is per-tenant. Risk noted: engines are not
  natively multi-tenant (see Complexity Tracking).
- **III. Deterministic, Governed Output** — PASS. The outline contract + versioned registry are
  first-class in the design; generation parameters are pinned per job.
- **IV. Test-First, Contract-Tested, Eval-Gated** — PASS as a process gate; contract tests against
  pinned engine versions and an eval harness are in scope from the first slice.
- **V. Observability & Cost Control** — PASS. Correlation ids, structured logs, per-tenant token/
  cost metering, timeouts/retries/circuit breakers on engine calls are in the baseline.

No principle is violated. The one item requiring justification (running not-natively-multi-tenant
engines under a multi-tenant product) is recorded in Complexity Tracking.

## Architecture Overview

Three planes, one mediator:

1. **Analysis plane — Open Notebook** (internal). One notebook per project; sources ingested via
   its REST API; provides summaries, transformations, vector/full-text search, and context chat
   the orchestrator uses to build outlines.
2. **Generation plane — Presenton** (internal). Receives a validated outline + template + tone/
   verbosity/slide-count/language via `POST /api/v1/ppt/presentation/generate`; returns
   `presentation_id`, `path`, `edit_path`; exports editable PPTX and PDF. Files uploaded first via
   `/api/v1/ppt/files/upload`.
3. **Orchestration plane — our service** (the only public surface). FastAPI app + Next.js UI +
   PostgreSQL + Redis + MinIO. Owns auth/tenancy/RBAC, the template/profile registry, the outline
   builder + schema validator, the job queue, the consistency checker, provenance, and metering.

Request path: Browser → Orchestrator API (authenticated, tenant-scoped) → {Open Notebook for
analysis, Presenton for generation} → artifacts to MinIO → metadata to PostgreSQL → response/job
status to client. See `research.md` for the detailed evaluation (the 7 questions) and
`data-model.md` for entities; sequence and the Presenton/Open Notebook contracts live in
`contracts/`.

## Workflow (analysis → orchestration → slides)

1. **Upload**: author adds sources to a project; orchestrator stores originals in MinIO and creates
   an async ingest job.
2. **Analyze**: job pushes each source into the project's Open Notebook notebook; on completion,
   pulls summaries/insights; marks sources ready.
3. **Build outline**: orchestrator composes a controlled prompt = analysis context + stakeholder
   profile (structure, tone, audience) + brand rules, and produces a **structured outline JSON**;
   validate against the outline schema. Reject/repair if invalid. This is the consistency contract.
4. **Map to Presenton params**: profile version → `template`, `tone`, `verbosity`, `n_slides`,
   `language`, and `slides_markdown`/`instructions` derived from the outline so structure is fixed,
   not re-invented by the engine.
5. **Generate**: call Presenton; poll/await; retrieve PPTX + PDF; store in MinIO.
6. **Validate**: consistency checker asserts required sections, slide-count range, template applied,
   banned content; pass → publish, fail → flag for review.
7. **Record**: persist generation with full provenance + metered cost; expose version history.
8. **Refine**: author edits outline/instructions and re-generates, reusing existing analysis.

## Project Structure

### Documentation (this feature)

```text
specs/001-presentation-notebook-llm/
├── plan.md              # This file
├── research.md          # Evaluation of the 7 questions + key decisions
├── data-model.md        # Entities and relationships
├── quickstart.md        # Local bring-up of the stack
└── contracts/
    ├── orchestrator-api.md      # Our public API surface (MVP endpoints)
    └── engine-integration.md    # Open Notebook + Presenton calls we depend on
```

### Source Code (repository root)

```text
backend/                         # FastAPI orchestration service
├── src/
│   ├── api/                     # routers: auth, tenants, projects, sources,
│   │                            #          profiles, templates, generations, usage
│   ├── models/                  # SQLAlchemy models (tenant-scoped)
│   ├── schemas/                 # Pydantic request/response + outline schema
│   ├── services/
│   │   ├── ingestion/           # Open Notebook client + ingest orchestration
│   │   ├── outline/             # controlled outline builder + validator
│   │   ├── generation/          # Presenton client + param mapping
│   │   ├── consistency/         # brand/structure linter
│   │   ├── registry/            # versioned profiles + templates
│   │   ├── tenancy/             # tenant context, RBAC, isolation guards
│   │   └── metering/            # token/cost + audit
│   ├── workers/                 # Arq/Celery tasks (ingest, generate)
│   └── core/                    # config, security, logging, tracing
└── tests/
    ├── contract/                # pinned-version tests vs ON + Presenton
    ├── integration/             # end-to-end pipeline
    ├── eval/                    # golden-input deck-consistency suite
    └── unit/

frontend/                        # Next.js full custom UI
├── src/
│   ├── app/                     # routes: login, projects, project detail,
│   │                            #         generate, profiles, templates, usage
│   ├── components/              # uploader, profile picker, outline editor,
│   │                            #         deck preview, version history
│   └── services/                # typed orchestrator API client
└── tests/                       # Playwright E2E

deploy/
├── docker-compose.yml           # orchestrator, postgres, redis, minio, traefik,
│                                # open-notebook(+surrealdb), presenton
├── .env.example
└── ops/                         # backups, healthchecks, dashboards
```

**Structure Decision**: Web-application layout (`backend/` + `frontend/`) because the spec has a
distinct full custom UI and an orchestration backend. Open Notebook and Presenton are deployed as
sibling containers in `deploy/`, consumed over the private network — not vendored into our source.

## Phasing (MVP slices, each independently shippable)

- **Slice 0 — Platform skeleton**: Docker Compose with all services up; OIDC login; tenant + user
  model; tenant-scoped data access guard; health/observability baseline.
- **Slice 1 — Ingestion**: project + source upload → Open Notebook ingest → status (covers Story 1
  inputs, Story 4 isolation).
- **Slice 2 — Registry**: stakeholder profiles + templates, versioned; PPTX import (Story 2).
- **Slice 3 — Generation core**: outline builder + schema + Presenton generation + PPTX/PDF +
  consistency check (completes Story 1).
- **Slice 4 — Refine + provenance**: outline editing, re-generate-without-reingest, version history
  (Story 3).
- **Slice 5 — Usage & audit**: metering, quotas, dashboards (Story 5).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Run two engines that are not natively multi-tenant under a multi-tenant product | Open Notebook and Presenton provide the analysis and generation capability we don't want to rebuild; reuse is far faster than building ingestion+RAG+PPTX rendering from scratch | Building our own analysis + slide engine was rejected as months of work; relying on the engines' own auth (ON single password, Presenton single admin) was rejected because it cannot isolate tenants — so isolation moves entirely into our orchestrator with namespacing + private networking |
| Separate PostgreSQL alongside Open Notebook's SurrealDB | We need a relational system of record for tenancy, RBAC, registry versioning, provenance, and billing that SurrealDB-as-ON-internal-store should not own | Reusing SurrealDB for our domain was rejected to avoid coupling our schema to ON's internals and its upgrade cycle |
| Dedicated async worker tier (Arq/Celery + Redis) | Ingestion and generation are long, failure-prone, rate-limited LLM calls needing retries, idempotency, and progress | Synchronous request handling was rejected: it would block, time out, and risk corrupt partial decks |
