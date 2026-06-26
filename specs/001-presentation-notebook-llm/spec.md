# Feature Specification: Presentation Notebook LLM Platform (MVP)

**Feature Branch**: `001-presentation-notebook-llm`

**Created**: 2026-06-19

**Status**: Draft

**Input**: A multi-tenant SaaS for Indonesian corporate teams that ingests business documents,
analyzes them with Open Notebook, and generates stakeholder-tailored presentations through
Presenton, with company-specific templates and enforced consistency.

## Problem & Goal

Corporate teams routinely rebuild the same deck for different audiences — group-level
management, department leaders, external stakeholders — each needing a different structure, tone,
template, and level of detail. Doing this by hand, or with ad-hoc LLM prompting, is slow and
produces inconsistent results even when templates and instructions are predefined. This platform
lets a team upload source material once, pick a stakeholder profile, and generate an on-brand,
structurally consistent presentation, repeatably.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a stakeholder-tailored deck from documents (Priority: P1)

An author uploads one or more business documents (PDF, Office, CSV, web link) into a project,
selects a stakeholder profile (e.g. "Group Management"), and requests a presentation. The system
analyzes the sources, produces a structured outline appropriate to that audience, generates the
slides on the company template, and returns a downloadable, editable PPTX (and PDF).

**Why this priority**: This is the core value loop. If only this works, the product is already
useful — it replaces the slowest, most error-prone part of the current workflow.

**Independent Test**: Upload a sample quarterly report, pick "Group Management", generate. Verify
a PPTX downloads, opens in PowerPoint, uses the selected template, and follows that profile's
required section structure.

**Acceptance Scenarios**:

1. **Given** a project with at least one successfully ingested source, **When** the author
   selects a stakeholder profile and clicks Generate, **Then** the system returns a PPTX and PDF
   whose section structure matches the profile's defined structure and whose styling matches the
   selected template.
2. **Given** the same project, profile, and template version, **When** the author generates twice,
   **Then** both decks have the same slide sections and ordering (wording may differ, structure
   must not).
3. **Given** a source that is still being processed, **When** the author requests generation,
   **Then** the system blocks generation with a clear "analysis in progress" state rather than
   producing a partial deck.

---

### User Story 2 - Manage stakeholder profiles and company templates (Priority: P1)

A tenant admin defines the audience profiles their organization uses and maps each to a company
template, a tone/verbosity, a required slide structure, and a prompt configuration. Admins can
import an existing company PowerPoint as the basis for a template.

**Why this priority**: Without governed profiles and templates, output cannot be consistent or
on-brand — this is what differentiates the platform from raw LLM prompting. It is a prerequisite
for Story 1 to deliver real value, hence also P1.

**Independent Test**: As tenant admin, create a profile "External Stakeholders" mapped to a
template and a 6-section structure, save it, then confirm it appears as a selectable option in the
generation flow and drives the resulting structure.

**Acceptance Scenarios**:

1. **Given** a tenant admin, **When** they create a stakeholder profile with a name, template,
   tone, verbosity, target slide count, and section structure, **Then** the profile is saved as a
   new immutable version and becomes selectable by authors in that tenant only.
2. **Given** an existing company PPTX, **When** an admin imports it as a template, **Then** the
   system registers a reusable template that subsequent generations can target.
3. **Given** a profile in use, **When** an admin edits it, **Then** a new version is created and
   prior generations remain traceable to the version that produced them.

---

### User Story 3 - Review, refine, and re-generate (Priority: P2)

After generation, the author previews the outline and the deck, can adjust the outline or
instructions, and re-generates without re-uploading or re-analyzing the sources.

**Why this priority**: Improves quality and trust and reduces cost/latency by reusing analysis,
but the product is still viable without it (the author could edit the PPTX directly).

**Independent Test**: Generate a deck, edit one outline section title and reduce slide count, then
re-generate and confirm only the intended change is reflected and analysis was not re-run.

**Acceptance Scenarios**:

1. **Given** a generated outline, **When** the author edits a section and re-generates, **Then**
   the new deck reflects the edit and reuses existing source analysis (no re-ingestion).
2. **Given** a generated deck, **When** the author opens version history, **Then** they see prior
   versions with the profile, template version, and model used for each.

---

### User Story 4 - Multi-tenant onboarding, access, and isolation (Priority: P1)

An organization is onboarded as a tenant. Its users sign in with role-based access (admin,
author, viewer). All of that tenant's data is isolated from every other tenant.

**Why this priority**: The product is multi-tenant SaaS from day one; isolation and auth are a
release blocker, not an enhancement.

**Independent Test**: Create two tenants with one project each; confirm a user in tenant A cannot
list, open, generate from, or download anything belonging to tenant B via UI or API.

**Acceptance Scenarios**:

1. **Given** two tenants, **When** a tenant-A user requests any tenant-B resource by id, **Then**
   the system denies access and the attempt is logged.
2. **Given** a viewer role, **When** the user attempts to create a profile or generate a deck,
   **Then** the action is denied by RBAC.

---

### User Story 5 - Track usage, cost, and an audit trail (Priority: P3)

Tenant admins see who generated what, for which stakeholder, from which sources, and the token/
cost consumed, with quotas and alerts.

**Why this priority**: Important for enterprise governance and cost control, but the core
generation loop functions without it for an initial pilot.

**Independent Test**: Generate several decks, then confirm the admin dashboard shows per-user and
per-tenant generation counts and an estimated cost, and that exceeding a quota is blocked/flagged.

**Acceptance Scenarios**:

1. **Given** completed generations, **When** an admin opens the usage view, **Then** counts and
   estimated cost per user and per tenant are shown for a selected period.
2. **Given** a tenant at its monthly quota, **When** a user generates, **Then** the system blocks
   or flags per policy and records the event.

### Edge Cases

- A source fails to ingest (corrupt/unsupported/too large) — the project surfaces a per-source
  error and generation proceeds only from successfully processed sources, with a warning.
- The LLM provider times out or rate-limits mid-generation — the job retries with backoff and, on
  exhaustion, fails cleanly with a resumable state, never a corrupt deck.
- Presenton is busy/unavailable — generation requests queue and report position rather than
  erroring immediately.
- A scanned/image-only PDF — OCR is attempted; if text cannot be extracted, the source is flagged
  as non-analyzable.
- Very large corpus exceeds model context — analysis falls back to retrieval/summarization rather
  than truncating silently.
- Mixed-language sources (Indonesian + English) — output language follows the profile/request
  setting regardless of source language.
- A template or profile is edited mid-generation — the in-flight job uses the version pinned at
  job start.

## Requirements *(mandatory)*

### Functional Requirements

**Ingestion & Analysis**

- **FR-001**: System MUST let an author create a project (workspace) and upload/attach multiple
  sources (PDF, common Office formats, CSV, plain text, and web URLs) to it.
- **FR-002**: System MUST ingest and analyze sources via Open Notebook, producing reusable
  artifacts (extracted text, summaries, key insights, and searchable/embedded content) scoped to
  the project and tenant.
- **FR-003**: System MUST report per-source processing status (queued, processing, ready, failed)
  and prevent generation from sources that are not ready.

**Stakeholder Profiles & Templates**

- **FR-004**: Tenant admins MUST be able to define stakeholder profiles, each specifying: display
  name, target audience, company template, tone, verbosity/detail level, target slide count or
  range, required section structure, output language, and a prompt configuration.
- **FR-005**: System MUST store profiles and templates in a versioned registry; edits create new
  versions and never mutate versions already used by past generations.
- **FR-006**: Admins MUST be able to register company templates, including importing an existing
  PowerPoint file as the basis for a template.
- **FR-007**: Profiles and templates MUST be tenant-scoped and selectable only within their tenant.

**Generation Pipeline**

- **FR-008**: System MUST produce a structured outline (sections + talking points + data bindings)
  from the project's analysis and the chosen stakeholder profile, and MUST validate that outline
  against a defined schema before slide generation.
- **FR-009**: System MUST generate slides by calling Presenton with the validated outline, the
  profile's template, tone, verbosity, slide count, and language, and MUST request editable PPTX
  plus PDF export.
- **FR-010**: System MUST run a consistency check on each generated deck (required sections present,
  slide count within range, template applied, banned-content rules) and flag or block decks that
  fail.
- **FR-011**: Authors MUST be able to preview and edit the outline and instructions and re-generate
  without re-ingesting sources.
- **FR-012**: System MUST persist every generated deck with its source set, profile version,
  template version, model/provider, and parameters, and expose version history.
- **FR-013**: Long-running ingestion and generation MUST run asynchronously with visible progress
  and MUST be idempotent and resumable on transient failure.

**Tenancy, Access & Governance**

- **FR-014**: System MUST authenticate users via centralized OIDC SSO and enforce roles of at least
  tenant admin, author, and viewer.
- **FR-015**: System MUST resolve tenant context server-side and guarantee that no resource is
  accessible across tenants through any UI or API path.
- **FR-016**: System MUST keep Open Notebook and Presenton on a private network, reachable only by
  the orchestration service, never directly by clients.
- **FR-017**: System MUST let each tenant configure its LLM/image provider and keys, store them
  encrypted, and route that tenant's generations to the configured provider/region.
- **FR-018**: System MUST record an audit trail of generation and administrative actions (actor,
  tenant, action, resources, template/model version, timestamp).
- **FR-019**: System MUST meter token usage and estimated cost per generation and per tenant, and
  MUST support per-tenant quotas with alerting.

**Output**

- **FR-020**: Generated presentations MUST be downloadable as editable PPTX and as PDF, and stored
  in tenant-isolated object storage with access-controlled retrieval.

### Key Entities *(include if feature involves data)*

- **Tenant**: An organization. Root of all isolation; owns users, projects, profiles, templates,
  provider configuration, quotas.
- **User**: A member of one tenant with a role (admin/author/viewer).
- **Project (Notebook)**: A workspace grouping sources and generated presentations; maps to an
  Open Notebook notebook internally.
- **Source**: An uploaded document or URL plus its processing status and derived analysis
  artifacts.
- **Stakeholder Profile**: A versioned definition of an audience's structure, tone, verbosity,
  template, language, and prompt configuration.
- **Template**: A versioned company slide design registered in Presenton, optionally imported from
  an existing PPTX.
- **Outline**: The validated structured plan (sections, talking points, data bindings) produced
  before slide generation; the consistency contract.
- **Presentation (Generation)**: A produced deck with its PPTX/PDF artifacts and full provenance
  (sources, profile version, template version, model, parameters, status).
- **Usage/Audit Record**: Metered cost/token and actor-action events per tenant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An author can go from uploaded documents to a downloaded, on-template PPTX for a
  chosen stakeholder in under 10 minutes for a typical 15–25 page source set.
- **SC-002**: Re-generating the same project+profile+template version yields the same section
  structure (section set and order identical) in at least 95% of runs.
- **SC-003**: At least 90% of generated decks pass the automated consistency check without manual
  structural fixes.
- **SC-004**: Producing a stakeholder variant of an existing deck takes at least 70% less author
  time than the current manual workflow (measured against a baseline task).
- **SC-005**: Zero cross-tenant data access in security testing; 100% of generations carry complete
  provenance (sources, profile version, template version, model).
- **SC-006**: The system sustains the pilot's concurrent generation load (target defined in plan)
  with no failed jobs left in a corrupt state — every failure is retried or cleanly resumable.

## Assumptions

- Deployment is self-hosted on a controlled VPS (Docker), with the option to choose an Indonesian/
  in-region host for data residency; horizontal scaling is a later phase.
- Multi-tenancy and all access control are enforced by our orchestration layer, because neither
  Open Notebook (optional single password) nor Presenton (single admin account per instance) is
  natively multi-tenant.
- Tenants bring their own LLM/image provider keys (BYOK); the platform does not mandate a single
  provider, supporting cost and residency choices.
- Open Notebook is used as the ingestion/analysis/retrieval engine and Presenton as the slide
  generation/export engine; both are consumed via their REST APIs and run as internal services.
- Editable PPTX and PDF are the required output formats for the MVP; live collaborative editing in
  the browser is out of scope for v1.
- Initial stakeholder profiles cover at least: Group Management, Department Leaders, and External
  Stakeholders, configurable per tenant.
- Source languages may be Indonesian and/or English; output language is set by the profile/request.
