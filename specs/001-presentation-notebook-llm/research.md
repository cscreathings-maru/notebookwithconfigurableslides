# Research & Evaluation — Presentation Notebook LLM

This document answers the seven evaluation questions from the brief and records the decisions
that flow into `plan.md`. Findings about the two engines are taken from their current READMEs.

## Engine facts that shape every decision

**Open Notebook** (MIT): Python/FastAPI + Next.js + SurrealDB + LangChain. Full REST API
(docs at `:5055/docs`). Ingests PDFs, Office docs, audio/video, web pages; full-text + vector
search; context-aware chat; customizable "transformations" (summaries/insight extraction); 18+
LLM/embedding providers via the Esperanto library; optional **single password** protection (not
multi-tenant). Docker-deployable.

**Presenton** (Apache 2.0): FastAPI + Next.js. AI presentation generation with a REST API —
`POST /api/v1/ppt/presentation/generate` taking `content`, `slides_markdown`, `instructions`,
`tone` (default/casual/professional/funny/educational/sales_pitch), `verbosity`
(concise/standard/text-heavy), `n_slides`, `language`, `template`, `include_table_of_contents`,
`include_title_slide`, `files`, `export_as` (pptx/pdf); returns `presentation_id`, `path`,
`edit_path`. Custom templates in **HTML + Tailwind**, can generate a template from an existing
PPTX, exports **editable PPTX**. Auth is **HTTP Basic against a single admin account per
instance**. BYOK across many providers; self-hostable via Docker.

The single most consequential fact: **neither engine is multi-tenant**. Open Notebook has one
optional password; Presenton has one admin per instance. Multi-tenancy therefore cannot be
delegated to them — it must be owned by our orchestrator, with the engines run as internal,
network-isolated services and their data namespaced per tenant.

## 1. Is this architecture technically feasible?

Yes. Both engines are API-first, Dockerized, BYO-LLM, and align on a FastAPI + Next.js stack, so
gluing them with a FastAPI orchestrator is low-friction. Open Notebook covers ingestion/analysis/
retrieval; Presenton covers generation/export with editable PPTX and custom templates — exactly
the two halves the product needs. The genuinely new work is not the AI plumbing but the
**enterprise envelope**: multi-tenant isolation, RBAC/SSO, a versioned template/profile registry,
a deterministic outline contract for consistency, async job handling, provenance, and cost
control. All of that is conventional web-platform engineering. Verdict: feasible, with the caveat
that the value and the risk both live in the orchestration layer, not the engines.

## 2. Best system design for combining the repositories

An **orchestrator-mediated, three-plane** design (see `plan.md` → Architecture Overview):

- Clients talk only to our orchestrator. The orchestrator is the sole holder of engine URLs and
  credentials, and the sole place tenancy/RBAC is enforced.
- Open Notebook and Presenton run as sibling containers on a private network with no public
  ingress. One Open Notebook **notebook per project**; Presenton called per generation.
- Our PostgreSQL is the system of record (tenants, users, projects, registry versions, generations,
  usage/audit). SurrealDB remains ON's private store; we don't reuse it for our domain.
- Object storage (MinIO) holds uploads and generated decks under tenant-prefixed keys.
- A worker tier (Redis + Arq/Celery) runs ingestion and generation as idempotent, resumable jobs.

Rejected alternatives: exposing the engines directly to the browser (breaks isolation and
security); forking/merging the two codebases into one (high maintenance, fights upstream upgrades);
relying on engine-native auth for tenancy (cannot isolate tenants).

## 3. Recommended backend/frontend stack

- **Orchestrator backend**: Python 3.11 + **FastAPI** (consistency with both engines and the
  LangChain ecosystem), Pydantic for the outline schema, SQLAlchemy + Alembic on **PostgreSQL**,
  **httpx** engine clients, **Arq or Celery** on **Redis** for jobs.
- **Frontend**: **Next.js (App Router) + React + TypeScript + Tailwind CSS**. Tailwind is a bonus
  because Presenton templates are HTML+Tailwind, so brand tokens can be shared.
- **Auth**: centralized **OIDC** via **Keycloak or Authentik** (multi-tenant realms/groups, SSO,
  RBAC) rather than hand-rolled auth.
- **Storage/infra**: **MinIO** (S3-compatible) for artifacts; **Traefik or Caddy** reverse proxy
  with TLS; Docker Compose on the VPS.
- **Observability**: OpenTelemetry tracing + Prometheus/Grafana + centralized logs (e.g. Loki).
- **LLM providers**: BYOK per tenant; both engines already support OpenAI/Anthropic/Google/Vertex/
  Azure/Ollama etc., so provider choice is a per-tenant config, not a code change.

This keeps one backend language across orchestrator and engines, and one component model (React/
Tailwind) across UI and slide templates.

## 4. Workflow between notebook analysis, LLM orchestration, and slide generation

The pipeline (detailed in `plan.md` → Workflow) is: **upload → analyze (Open Notebook) → build &
validate structured outline → map outline+profile to Presenton params → generate → consistency
check → record provenance → optional refine/re-generate**.

The orchestration insight that makes the product work: **separate "what to say" from "how it
looks," and make the LLM's structural freedom small**. The orchestrator uses Open Notebook to get
grounded content, then emits a **validated outline JSON** (sections, talking points, data
bindings) under a controlled, profile-specific prompt. That outline — not a free-text prompt — is
what drives Presenton (via `slides_markdown`/`instructions`), with the profile setting `template`,
`tone`, `verbosity`, `n_slides`, and `language`. Structure is thus deterministic across runs;
only wording varies. Analysis artifacts are cached per project so refine/re-generate is cheap.

## 5. Scalability & reliability challenges

- **Multi-tenant isolation over non-multi-tenant engines** (top risk): enforce in our layer;
  namespace ON notebooks and Presenton templates per tenant; private networking; per-tenant
  MinIO prefixes. For strict separation of large/sensitive tenants, run per-tenant or per-tier
  engine instances.
- **Presenton is stateful and single-admin**: scale by running a **pool of Presenton instances**
  behind the orchestrator with a queue, pin a version, healthcheck, and back up `app_data`. Don't
  treat it as elastically stateless without testing.
- **LLM latency, cost, rate limits, non-determinism**: async jobs, timeouts, bounded retries with
  backoff, idempotency keys, circuit breakers, low temperature, pinned model versions, response
  caching, and per-tenant quotas.
- **Heavy rendering**: PPTX/PDF and image generation are CPU/memory intensive — size the VPS,
  cap concurrency, queue overflow, and consider GPU only if using local models.
- **Stateful stores**: SurrealDB (ON), PostgreSQL, MinIO, Presenton `app_data` all need automated
  backups and restore drills; SurrealDB on a single node is a SPOF for analysis.
- **Single-VPS ceiling**: vertical-scale first; design stateless orchestrator + workers so moving
  to multiple nodes / k8s later is mechanical, not a rewrite.
- **Failure semantics**: every long job must fail into a resumable state, never a corrupt deck.

## 6. Improving presentation consistency & template governance

- **Deterministic outline contract**: a JSON schema for sections/points/data bindings, validated
  before generation; repair-or-reject on invalid. This is the primary consistency lever.
- **Versioned registry**: stakeholder profiles and templates are immutable versions with an
  approval gate; a generation pins the versions it used; edits never mutate history.
- **Profile = full styling+structure spec**: template name, tone, verbosity, target slide range,
  required sections, language, and prompt config + few-shot exemplars — all centralized, not in
  code.
- **Brand/structure linter**: post-generation check for required sections, slide-count range,
  template application, fonts/colors (Tailwind tokens shared with Presenton templates), and
  banned content; block or flag on failure.
- **Eval harness**: golden inputs → assert structural equality against approved baselines; gate
  merges on it; track variance over time.
- **Onboard company decks** via Presenton's "generate template from existing PPTX" so brand
  templates are first-class rather than reverse-engineered by hand.
- **Human-in-the-loop**: outline preview + approval and version diffs before publishing externally.

## 7. Is an API-first Presenton approach practical for enterprise?

Practical, with a wrapper. **For**: a clean REST generate endpoint, editable PPTX + PDF export,
custom HTML/Tailwind templates, template-from-PPTX, self-hosting (data stays in your VPS), an MCP
server, and broad BYOK provider support. **Against, for enterprise**: a **single admin account per
instance with HTTP Basic** — no native multi-tenancy, RBAC, or SSO; a stateful `app_data` volume;
and template provisioning that must be managed operationally. Net: do **not** expose Presenton to
tenants. Run it as an internal microservice behind the orchestrator, which supplies tenancy, RBAC,
SSO, quotas, and audit; provision per-tenant templates by naming convention; pool/queue requests;
pin the version behind contract tests; add healthchecks and replica autoscaling; and back up
`app_data`. With that envelope, API-first Presenton is a solid enterprise generation engine.

## Key decisions (carried into the plan)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tenancy boundary | Orchestrator only | Engines aren't multi-tenant |
| Engine exposure | Internal/private network | Security + isolation |
| System of record | PostgreSQL (separate from ON's SurrealDB) | Tenancy, registry versioning, provenance, billing |
| Consistency mechanism | Validated outline contract + versioned registry + linter + evals | Structure deterministic, wording flexible |
| Generation calls | Async via queue with retries/idempotency | LLM latency/cost/failure |
| Presenton scaling | Instance pool behind queue, version pinned | Stateful single-admin design |
| Providers | BYOK per tenant | Cost + data-residency control |
| Frontend | Next.js + Tailwind | Full custom UI; shares brand tokens with templates |

## Open questions to resolve during implementation

- Exact concurrency/SLA targets for the pilot (drives VPS sizing and Presenton replica count).
- Whether the strictest tenants require dedicated engine instances vs shared-with-namespacing.
- Data-retention and deletion policy per tenant (right-to-be-forgotten across MinIO + SurrealDB +
  Presenton `app_data`).
- Default model/provider per tenant tier and the cost-quota policy.
