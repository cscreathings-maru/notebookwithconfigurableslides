Extend the existing orchestration backend with a VERSIONED registry for stakeholder profiles and company templates. Do NOT build Presenton — register templates via its API through the existing typed client. Reuse tenant-context, RBAC (admin role), and the data layer.

Goal: tenant admins define audience profiles and company templates that drive consistent, on-brand generation; every edit creates a new immutable version.

Deliver:
1. Models + migrations:
   - StakeholderProfile (versioned): id (stable across versions), version, name, audience, template_id + pinned template_version, tone (default/casual/professional/funny/educational/sales_pitch), verbosity (concise/standard/text-heavy), slide_min, slide_max, language, section_structure (JSON ordered required sections), prompt_config (JSON controlled prompt + exemplars), status (draft/approved/archived).
   - Template (versioned): id, version, name, presenton_template_ref, source_pptx_uri, brand_tokens (JSON colors/fonts), status.
2. Versioning rule: editing creates a NEW version; a version referenced by any Generation is immutable. Implement and test this invariant.
3. APIs (admin):
   - Profiles: POST /api/v1/profiles, GET /api/v1/profiles, PUT /api/v1/profiles/{id} (new version), POST /api/v1/profiles/{id}/approve.
   - Templates: POST /api/v1/templates (with optional PPTX upload → import-as-template via Presenton, store engine ref, tenant-namespaced name), GET /api/v1/templates, POST /api/v1/templates/{id}/approve.
4. Authors can read approved profiles/templates only; both are strictly tenant-scoped.
5. Frontend (admin area): profile editor (name, audience, template, tone, verbosity, slide range, language, section-structure builder, prompt config) and template manager (create, import PPTX, approve).
6. Tests: contract test that a used version is immutable and edits produce new versions; tenant-scoping test. Write tests first.

Constraints: store Presenton template refs namespaced per tenant; never expose engine refs to clients.
