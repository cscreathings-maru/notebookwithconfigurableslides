Extend the existing orchestration backend (FastAPI, Python 3.11, SQLAlchemy/Postgres, Redis+Arq, httpx) with document ingestion. Do NOT build Open Notebook — call its REST API via the existing typed client. Reuse the tenant-context, RBAC, job framework, and tenant-scoped repository already in the project.

Goal: an author uploads documents/URLs to a project; the system ingests and analyzes them via Open Notebook and tracks per-source status.

Deliver:
1. Models + migrations for Project and Source per the data model. Project maps 1:1 to an Open Notebook notebook (store on_notebook_id). Source stores kind (pdf/office/csv/text/url), original_uri (MinIO key or URL), on_source_id, status (queued/processing/ready/failed), error, analysis_ref.
2. APIs (all tenant-scoped, author role):
   - POST /api/v1/projects {name} → creates a project AND an Open Notebook notebook.
   - GET /api/v1/projects, GET /api/v1/projects/{id}
   - POST /api/v1/projects/{id}/sources (multipart file OR {url}) → stores original in MinIO under a tenant-prefixed key, creates Source (queued), enqueues an ingest job.
   - GET /api/v1/projects/{id}/sources, GET /api/v1/sources/{id}
3. Ingest worker: push the source into the project's Open Notebook notebook using the tenant's BYOK provider config; poll/await analysis; on success set status=ready and store analysis_ref (summary/insights reference); on failure set status=failed with error. Idempotent and resumable.
4. Object storage helper: tenant-prefixed MinIO keys.
5. Tests: contract test for the Open Notebook ingest/analyze calls (pinned version); integration test for upload → ready; a corrupt/unsupported file flags the source failed without breaking the project. Write tests first.

Constraints: never expose on_notebook_id/on_source_id to clients; generation must be blocked elsewhere until sources are ready (expose status accurately).
