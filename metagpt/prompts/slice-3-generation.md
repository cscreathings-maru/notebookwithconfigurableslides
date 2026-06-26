Extend the existing orchestration backend with the core generation pipeline: build a validated outline, generate slides via Presenton, and enforce consistency. Do NOT build Presenton or Open Notebook — call them via the existing typed clients. Reuse projects, sources, profiles, templates, the job framework, and metering hooks.

Goal: from a project's analysis + a chosen stakeholder profile, produce an on-template, structurally consistent, editable PPTX (and PDF). Structure must be deterministic across runs; only wording varies.

Deliver:
1. Outline contract: a Pydantic JSON schema for an Outline = { sections[], talking_points[], data_bindings[] } with a schema_version. A validator that rejects or repairs invalid outlines.
2. Outline builder: compose a CONTROLLED prompt from (a) Open Notebook analysis/retrieval for the project and (b) the pinned stakeholder profile (section_structure, tone, audience, prompt_config), produce the structured outline JSON, and validate it. Low temperature; pinned model. Persist Outline with profile_id/version.
   - APIs: POST /api/v1/projects/{id}/outline {profile_id} → Outline; GET /api/v1/outlines/{id}; PUT /api/v1/outlines/{id} {content} (re-validate).
3. Param mapper: profile + validated outline → Presenton generate request: content, slides_markdown (derived from outline so STRUCTURE is fixed), instructions (prompt_config), tone, verbosity, n_slides (within slide_min..max), language, template (presenton_template_ref), include_title_slide, export_as. Request pptx then pdf.
4. Generation API + worker:
   - POST /api/v1/projects/{id}/generations {outline_id} → Generation (queued); 409 if any source not ready.
   - Worker calls Presenton, retrieves PPTX+PDF from the returned path, copies to tenant-prefixed MinIO keys, records presenton_presentation_id. Idempotent; failure leaves a resumable state, never a corrupt artifact.
   - GET /api/v1/generations/{id} (status + consistency_report + links); GET /api/v1/generations/{id}/download?format=pptx|pdf (signed URL).
5. Consistency checker: assert required sections present, slide count within range, template applied, banned-content rules; attach a consistency_report; flag/block on failure.
6. Provenance + UsageRecord: store sources used, profile version, template version, model/provider, params, tokens/cost.
7. Frontend: outline preview/edit, generate button with job progress, deck download.
8. Tests (write first): contract test for the Presenton generate mapping; an eval test that the same project+profile+template version yields the same section set and order; integration test for upload→analyze→outline→generate→download.

Constraints: the LLM never free-forms the whole deck — the validated outline drives structure. Engine ids/paths stay server-side.
