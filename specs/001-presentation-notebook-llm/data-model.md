# Data Model — Presentation Notebook LLM (MVP)

System of record is **PostgreSQL** (orchestrator). Open Notebook's SurrealDB and Presenton's
`app_data` are engine-internal and not modeled here. Every table except `tenant` carries a
`tenant_id` foreign key; all queries are filtered by the session's tenant. IDs are UUIDs;
timestamps are UTC.

## Entities

### Tenant

The organization; root of isolation.

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| name | string | |
| slug | string (unique) | URL/namespace key; used to namespace engine resources |
| status | enum(active, suspended) | |
| llm_provider | string | e.g. `deepseek` (BYOK per tenant) |
| llm_config_enc | bytes | encrypted provider config (base_url, model, key) |
| region | string | data-residency hint for egress |
| quota_monthly_generations | int | 0 = unlimited |
| created_at / updated_at | timestamp | |

### User

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id | uuid (FK) | |
| email | string | unique per tenant |
| oidc_subject | string | from SSO |
| role | enum(admin, author, viewer) | RBAC |
| status | enum(active, disabled) | |
| created_at | timestamp | |

### Project

A workspace; maps 1:1 to an Open Notebook notebook.

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id | uuid (FK) | |
| name | string | |
| on_notebook_id | string | Open Notebook notebook id (engine-internal ref) |
| created_by | uuid (FK user) | |
| created_at / updated_at | timestamp | |

### Source

An uploaded document/URL and its analysis state.

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id / project_id | uuid (FK) | |
| kind | enum(pdf, office, csv, text, url) | |
| original_uri | string | MinIO key (tenant-prefixed) or URL |
| on_source_id | string | Open Notebook source id |
| status | enum(queued, processing, ready, failed) | |
| error | string null | failure reason |
| analysis_ref | string null | pointer to derived summary/insights |
| created_at | timestamp | |

### StakeholderProfile (versioned)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | logical profile id (stable across versions) |
| tenant_id | uuid (FK) | |
| version | int | increments on edit; immutable once used |
| name | string | e.g. "Group Management" |
| audience | string | description |
| template_id | uuid (FK Template) | bound template |
| template_version | int | pinned |
| tone | enum(default, casual, professional, funny, educational, sales_pitch) | maps to Presenton |
| verbosity | enum(concise, standard, text-heavy) | maps to Presenton |
| slide_min / slide_max | int | target range |
| language | string | output language |
| section_structure | json | ordered required sections (the structure contract) |
| prompt_config | json | controlled prompt + few-shot exemplars |
| status | enum(draft, approved, archived) | governance gate |
| created_by / created_at | | |

### Template (versioned)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id | uuid (FK) | |
| version | int | |
| name | string | Presenton template name (tenant-namespaced) |
| presenton_template_ref | string | engine-side template id/name |
| source_pptx_uri | string null | original imported deck (MinIO) |
| brand_tokens | json | colors/fonts for the linter |
| status | enum(draft, approved, archived) | |
| created_by / created_at | | |

### Outline

The validated structure contract produced before generation.

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id / project_id | uuid (FK) | |
| profile_id / profile_version | | pinned |
| schema_version | string | outline JSON schema version |
| content | json | sections[], talking_points[], data_bindings[] |
| valid | bool | passed schema validation |
| created_at | timestamp | |

### Generation (Presentation)

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id / project_id | uuid (FK) | |
| outline_id | uuid (FK) | |
| profile_id / profile_version | | provenance |
| template_id / template_version | | provenance |
| source_ids | uuid[] | sources used |
| model / provider | string | provenance |
| params | json | tone, verbosity, n_slides, language sent to Presenton |
| presenton_presentation_id | string | engine ref |
| pptx_uri / pdf_uri | string | MinIO keys |
| status | enum(queued, analyzing, building_outline, generating, validating, ready, failed) | |
| consistency_report | json | linter result |
| created_by / created_at | | |

### Job

Async work unit (ingest or generate).

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id | uuid (FK) | |
| type | enum(ingest, generate) | |
| ref_id | uuid | source_id or generation_id |
| status | enum(queued, running, succeeded, failed) | |
| attempts | int | retry count |
| idempotency_key | string | |
| progress | json | step/percent |
| created_at / updated_at | | |

### UsageRecord / AuditEvent

| Field | Type | Notes |
|-------|------|-------|
| id | uuid (PK) | |
| tenant_id | uuid (FK) | |
| actor_user_id | uuid null | |
| action | string | e.g. generation.created, profile.updated |
| resource | json | type + ids + versions |
| tokens_in / tokens_out | int | metering |
| cost_estimate | decimal | |
| created_at | timestamp | |

## Relationships

- Tenant 1—N User, Project, StakeholderProfile, Template, UsageRecord.
- Project 1—N Source, Outline, Generation.
- StakeholderProfile N—1 Template (pinned version); Generation references the pinned profile and
  template versions for full provenance.
- Outline 1—1..N Generation (an outline can be regenerated).
- Job 1—1 Source (ingest) or Generation (generate).

## Invariants (enforced by the orchestrator)

1. No row is readable/writable outside its `tenant_id`.
2. A `StakeholderProfile`/`Template` version that any `Generation` references is immutable.
3. A `Generation` may only start when all referenced `Source`s are `ready`.
4. Every `Generation` stores the exact profile version, template version, model, and params used.
5. Engine-internal ids (`on_notebook_id`, `on_source_id`, `presenton_*`, `presenton_template_ref`)
   are never exposed to clients.
