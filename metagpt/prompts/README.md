# MetaGPT Prompts — one per MVP slice

Each file is a **focused, self-contained requirement** for one bounded component. MetaGPT works
far better on a scoped prompt than on "build the whole platform," and these are sized so its
PM→architect→engineer→QA roles can produce a coherent module you then review and integrate.

## Rules baked into every prompt

- **Do NOT build Open Notebook or Presenton.** They are existing external services consumed over
  HTTP. Generate only the orchestrator backend and/or frontend code for that slice.
- Respect the constitution: tenant isolation, engines never client-exposed, deterministic outline
  contract, contract tests + evals, observability.
- Match the contracts in `specs/001-presentation-notebook-llm/contracts/` and the entities in
  `data-model.md`.
- Target stack: Python 3.11 + FastAPI + SQLAlchemy/Alembic + Postgres + Redis + Arq/Celery + httpx
  (backend); Next.js + TypeScript + Tailwind (frontend).

## How to run (see ../OPERATOR-GUIDE.md for full detail)

```bash
# from a dedicated codegen workspace, per slice:
metagpt "$(cat slice-0-platform-skeleton.md)"
# review ./workspace output → integrate the orchestrator/frontend parts → run tests
```

Generate slices in order (0 → 5); each builds on the prior. Feed the relevant contract file
alongside the prompt where your MetaGPT setup supports extra context.

## Slices

| File | Builds | Spec stories |
|------|--------|--------------|
| slice-0-platform-skeleton.md | compose stack, auth, tenancy, RBAC, job framework | US4 + foundation |
| slice-1-ingestion.md | project + source upload → Open Notebook analysis | US1 (inputs) |
| slice-2-registry.md | versioned profiles + templates, PPTX import | US2 |
| slice-3-generation.md | outline contract → Presenton generate → consistency check | US1 (core) |
| slice-4-refine-provenance.md | outline editing, regenerate, version history | US3 |
| slice-5-usage-audit.md | metering, quotas, audit dashboard | US5 |
