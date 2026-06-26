# Contract — Orchestrator Public API (MVP)

The orchestrator is the **only** public surface. All endpoints require an authenticated OIDC
session; tenant is resolved server-side from the token (never from the path/body). Roles:
`admin`, `author`, `viewer`. JSON over HTTPS. Long operations return a job and are polled.

Base path: `/api/v1`. Errors use a consistent shape: `{ "error": { "code", "message" } }`.

## Auth

- `GET /auth/me` → current user, tenant, role.
- OIDC login/callback handled by the SSO provider (Keycloak/Authentik); orchestrator validates the
  token and maps `oidc_subject` → user.

## Projects

- `POST /projects` (author) `{ name }` → `Project`. Creates an Open Notebook notebook internally.
- `GET /projects` → tenant's projects.
- `GET /projects/{id}` → project detail (404 if other tenant).

## Sources

- `POST /projects/{id}/sources` (author) multipart file **or** `{ url }` → `Source` (status
  `queued`); enqueues an ingest job.
- `GET /projects/{id}/sources` → list with status.
- `GET /sources/{id}` → status + error.

## Stakeholder Profiles (admin)

- `POST /profiles` `{ name, audience, template_id, tone, verbosity, slide_min, slide_max,
  language, section_structure, prompt_config }` → new profile **version**.
- `GET /profiles` → approved + draft profiles (author sees approved only).
- `PUT /profiles/{id}` → creates a new version (never mutates).
- `POST /profiles/{id}/approve` → status `approved`.

## Templates (admin)

- `POST /templates` `{ name, brand_tokens }` and optional PPTX upload → registers a Presenton
  template (tenant-namespaced); supports import-from-PPTX.
- `GET /templates` → list.
- `POST /templates/{id}/approve`.

## Outlines

- `POST /projects/{id}/outline` (author) `{ profile_id }` → builds a structured outline from the
  project analysis + profile, validates it, returns `Outline` (`valid`, `content`).
- `GET /outlines/{id}` → outline.
- `PUT /outlines/{id}` (author) `{ content }` → edited outline (re-validated).

## Generations

- `POST /projects/{id}/generations` (author) `{ outline_id }` → `Generation` (status `queued`);
  enqueues a generate job. 409 if any referenced source is not `ready`.
- `GET /generations/{id}` → status, `consistency_report`, artifact links when ready.
- `GET /generations/{id}/download?format=pptx|pdf` → signed, access-controlled artifact URL.
- `GET /projects/{id}/generations` → version history with provenance (profile/template version,
  model).

## Usage & Audit (admin)

- `GET /usage?from=&to=` → per-user/per-tenant counts, tokens, estimated cost.
- `GET /audit?from=&to=` → audit events.

## Jobs

- `GET /jobs/{id}` → `{ type, status, progress, attempts }` for polling ingest/generate.

## Cross-cutting rules

- Every mutating call writes an `AuditEvent`; every LLM-backed call writes a `UsageRecord`.
- 403 (not 404) only when authenticated but lacking role; cross-tenant access returns 404 to avoid
  resource enumeration.
- All engine ids stay server-side; clients only ever see orchestrator UUIDs.
