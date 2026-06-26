# Presentation Notebook LLM Constitution

The non-negotiable principles governing the design, implementation, and operation of the
Presentation Notebook LLM platform — a multi-tenant SaaS that turns business documents into
stakeholder-tailored presentations by orchestrating Open Notebook (analysis) and Presenton
(slide generation) behind a custom application layer.

## Core Principles

### I. Engine Isolation, Orchestrator-Mediated Access

Open Notebook and Presenton are treated as **internal engines, never public surfaces**. No
browser, tenant, or third party may call them directly. All access flows through our
orchestration API, which owns authentication, tenancy, RBAC, validation, and auditing. The
engines run on a private network segment with no inbound public routes. Their own
authentication (Open Notebook's optional password; Presenton's single admin account) is a
defense-in-depth layer, **not** the system's tenancy boundary. Consequence: any feature that
would expose an engine endpoint to a client is rejected by design.

### II. Tenant Isolation & Data Sovereignty (NON-NEGOTIABLE)

Every stored object — document, notebook, analysis, outline, template, generated deck, log —
is scoped to exactly one tenant and is unreachable across tenant boundaries. Tenant identity is
resolved server-side from the authenticated session, never from a client-supplied parameter
alone. Uploaded corporate data and its derivatives stay on the controlled VPS / in-region
storage; sending tenant content to an external LLM requires that the tenant's configured
provider and region permit it, and such egress is logged. Cross-tenant data exposure is a P0
incident. Isolation is enforced in our layer because neither upstream engine is multi-tenant.

### III. Deterministic, Governed Output Over Free Generation

Consistency is the product. The LLM never free-forms an entire deck. Generation follows a
**structured outline contract** (a validated schema of sections, talking points, and data
bindings) produced under controlled prompts, then handed to Presenton with a fixed template and
parameters. Templates, stakeholder profiles, and prompts live in a **versioned registry** with
approval gates — not hard-coded and not editable ad hoc in production. Given the same inputs,
profile, and template version, output structure must be reproducible.

### IV. Test-First, Contract-Tested, Eval-Gated

Tests are written and approved before implementation (Red-Green-Refactor). Every integration
with Open Notebook and Presenton is covered by **contract tests** pinned to a specific engine
version, so upstream changes fail loudly in CI rather than silently in production. Output
quality is protected by an **evaluation harness**: golden inputs produce decks checked for
required sections, slide counts, brand rules, and structural diff against approved baselines.
A change that regresses the eval suite does not ship.

### V. Observability, Cost Control & Reliability

Every request is traced end-to-end (upload → analysis → outline → generation → export) with
structured logs and a correlation id. Token usage, latency, and spend are metered per tenant and
per generation, with quotas and alerts. All engine calls have timeouts, bounded retries with
backoff, idempotency keys, and circuit breakers; long operations run as asynchronous jobs with
visible progress. No silent failures: errors surface to the user with an actionable state and to
operators with enough context to debug.

## Security, Compliance & Deployment Constraints

Authentication is centralized (OIDC) with role-based access (at minimum: tenant admin, author,
viewer). Secrets and per-tenant LLM keys are encrypted at rest and never logged. The platform
deploys as containers on a controlled VPS via Docker Compose for the MVP, with object storage
for artifacts and automated backups of all stateful stores (PostgreSQL, SurrealDB, Presenton
`app_data`). An auditable trail records who generated what, for which stakeholder, from which
sources, using which template and model version. Network egress to LLM providers is explicit and
per-tenant configurable to support data-residency requirements.

## Development Workflow & Quality Gates

Work proceeds through the Spec-Driven flow: constitution → spec → plan → tasks → implement, with
each feature specified before it is built. Pull requests must pass linting, type checks, unit and
contract tests, and the output-consistency eval suite. Engine versions are pinned and upgraded
deliberately behind contract tests. Prompts and templates change only through the versioned
registry with a reviewer's approval. Any deviation from these principles must be recorded in the
plan's Complexity Tracking with justification and the rejected simpler alternative.

## Governance

This constitution supersedes other practices for this project. Amendments require a documented
rationale, review, and a migration note; principle changes bump the MAJOR version, new
principles or material expansions bump MINOR, and clarifications bump PATCH. Every plan includes
a Constitution Check gate that must pass before design and again before implementation. Reviewers
are expected to verify compliance, and complexity must always be justified against a simpler
alternative.

**Version**: 1.0.0 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-06-19
