# Contract — Engine Integration (Open Notebook + Presenton)

How the orchestrator consumes the two internal engines. Both run on a **private network**; only
the orchestrator holds their URLs and credentials. Versions are **pinned** and covered by contract
tests. These are the surfaces we depend on; treat anything not listed here as out of contract.

## Open Notebook (analysis engine)

- Base URL (internal): `http://open-notebook:5055` (REST API; interactive docs at `/docs`).
- Used for: creating notebooks, adding sources, triggering analysis/transformations, retrieving
  summaries/insights, and context retrieval for outline building.

Orchestrator usage (logical operations — confirm exact paths against the pinned version's
`/docs`):

| Operation | Purpose | Orchestrator maps to |
|-----------|---------|----------------------|
| Create notebook | one per Project | stores `on_notebook_id` |
| Add source (file/URL) | ingest a document | stores `on_source_id`, status `processing` |
| Poll source status | detect `ready`/`failed` | updates `Source.status` |
| Run transformation/summary | extract insights | stores `analysis_ref` |
| Search / context query | gather grounded content for outline | feeds outline builder |

Rules:
- One notebook per project; sources are namespaced by project → tenant.
- Provider/keys are the **tenant's** BYOK config, passed per request/instance, not a global key.
- Wrap every call with timeout + bounded retry; ingestion is async (job-backed).

## Presenton (generation engine)

- Base URL (internal): `http://presenton:80` (compose maps host `5000:80`).
- Auth: **HTTP Basic**, single admin account per instance (`AUTH_USERNAME`/`AUTH_PASSWORD`).
  This is engine-internal only — never a tenant boundary.

### Upload files (optional, when generating from documents)

`POST /api/v1/ppt/files/upload` → returns file refs to pass to generate.

### Generate presentation

`POST /api/v1/ppt/presentation/generate`  (Content-Type: application/json, HTTP Basic)

Request fields the orchestrator sets (from the pinned profile + validated outline):

| Field | Source | Notes |
|-------|--------|-------|
| `content` | outline summary / brief | main content |
| `slides_markdown` | derived from validated outline | **fixes structure** (don't let engine re-invent) |
| `instructions` | profile prompt_config | extra guidance |
| `tone` | profile.tone | default/casual/professional/funny/educational/sales_pitch |
| `verbosity` | profile.verbosity | concise/standard/text-heavy |
| `n_slides` | within profile slide_min..slide_max | |
| `language` | profile.language | |
| `template` | template.presenton_template_ref | tenant-namespaced |
| `include_table_of_contents` | profile | |
| `include_title_slide` | profile | |
| `files` | uploaded refs | optional |
| `export_as` | `pptx` then `pdf` | editable PPTX required |

Response: `{ "presentation_id", "path", "edit_path" }`. The orchestrator pulls the file from
`path`, copies it to MinIO under a tenant-prefixed key, and records `presenton_presentation_id`.
`edit_path` is internal-only.

### Templates

- Register/import company templates (incl. **generate-template-from-PPTX**) ahead of time;
  store the engine ref as `Template.presenton_template_ref`, namespaced per tenant.

## Multi-tenant & scaling rules (apply to both engines)

1. Engines are internal; no client ever calls them directly.
2. Tenant isolation is enforced in the orchestrator + resource namespacing (notebook per
   project/tenant; template names tenant-prefixed); never rely on engine auth for isolation.
3. Run Presenton as a **pool of instances** behind the job queue; pin a version; health-check;
   back up `app_data`. For strict tenants, dedicate an instance.
4. All calls: timeout, bounded retry w/ backoff, idempotency key, circuit breaker; failures leave a
   resumable job state, never a corrupt artifact.
5. Engine versions are pinned; upgrades go through contract tests before rollout.
