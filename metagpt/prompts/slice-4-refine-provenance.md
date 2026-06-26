Extend the existing orchestration backend so authors can refine and re-generate presentations without re-ingesting sources, and can see full version history. Reuse the outline, generation, projects, and provenance already implemented. Do NOT touch the engines beyond the existing clients.

Goal: cheap, traceable iteration on a generated deck.

Deliver:
1. Outline editing → regenerate: PUT /api/v1/outlines/{id} re-validates the edited outline; POST a new Generation from the edited outline REUSES existing source analysis (no re-ingestion) and reuses the same pinned profile/template versions unless explicitly changed.
2. Version history: GET /api/v1/projects/{id}/generations returns each Generation with provenance — profile version, template version, model/provider, params, created_by, created_at, status.
3. Frontend: outline editor with validation feedback; version-history view; deck preview; a simple structural diff between two generations (section set/order).
4. Tests (write first): integration test proving an edit → regenerate path does NOT call Open Notebook ingestion again and reflects only the intended change; a test that history exposes complete provenance for each version.

Constraints: an in-flight job uses the versions pinned at job start; editing a profile/template must not mutate past generations.
