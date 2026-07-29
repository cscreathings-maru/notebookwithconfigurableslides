# Architecture

How NoteAI is put together, why the load-bearing decisions were made, and where the
boundaries are. Written so the next person does not re-derive `/editor` from eight
commits of Traefik iteration.

Accurate as of Phase 2 (2026-07-29). Where a feature is partial, this says so.

---

## 1. Services

| Service | Role | Network |
|---|---|---|
| `traefik` | Path-routes everything on one origin | `edge` |
| `frontend` | Next.js 14 App Router, standalone output | `edge`, `appnet` |
| `orchestrator` | FastAPI at `/api/v1` — the system of record's owner | `edge`, `appnet` |
| `worker` | Arq consumer for ingest + generate | `appnet` |
| `init` | One-shot `alembic upgrade head` + seed, then exits | `appnet` |
| `postgres` | System of record | `appnet` |
| `redis` | Job queue (Arq) | `appnet` |
| `minio` | Artifact store (uploads, decks) | `appnet` |
| `surrealdb` | Open Notebook's store | `appnet` |
| `open-notebook` | Embeddings + retrieval | `appnet` |
| `presenton` | Slide rendering | `edge`, `appnet` |

Only `traefik` publishes a host port. Everything else is reachable only from inside
the compose networks — which is the root of the download defect described in §5.

---

## 2. The `/editor` decision (locked)

> **Presenton is served on the same origin under `/editor`, using a build-time
> `basePath` in its `next.config.mjs`.**

### Why not expand the Traefik rules

Both the NoteAI frontend and Presenton are Next.js apps. Both serve static assets from
`/_next`. **Traefik cannot disambiguate two byte-identical path prefixes on one
origin** — router priority does not help, because the prefix is the same string.

`deploy/docker-compose.lite.yml` still carries the failed attempt: a seventeen-way
`PathPrefix` alternation on the `presenton` router, with `/_next` necessarily absent
because listing it would steal the frontend's assets. That rule cannot succeed by
construction, and eight commits were spent discovering it.

### Why `basePath` works

`basePath: '/editor'` makes Presenton emit `/editor/_next/...`. **The collision stops
existing** rather than being arbitrated. It must be baked at build time: in standalone
mode Next.js does not read `next.config.mjs` at runtime, so Presenton's `start.js`
attempt to inject it is inert.

### The residual allowlist

`basePath` rewrites `Link`/`Image`/router navigation. It does **not** rewrite
client-side `fetch()`. Presenton's Python API is called at root paths (`/api/v1/ppt/…`,
`/api/can-change-keys`, …), so the router rule keeps an explicit allowlist for those.

That allowlist steals paths from the orchestrator at priority 20. Nothing collides
today, which is exactly why it will regress silently — a route-collision test is the
guard (T-1.1, still blocked).

**Status: BLOCKED.** Implementing this needs Presenton's source, which is not in the
repository. See §7.

---

## 3. Two generation paths

Both write the same `Generation` row and use the same job, worker, object store and
download endpoint.

```
governed:  sources → outline (profile-pinned) → consistency → deck
freeform:  content source (custom | chat | summary | notebook) → deck        ← primary
```

`POST /projects/{id}/generations` is polymorphic: `content_source` selects freeform,
`outline_id` selects governed. Collapsing this is deferred to Phase 3.

**Divergence between the two is this codebase's recurring failure mode.** The freeform
path shipped without quota or metering (fixed T-2.2), and brand tokens are still wired
into neither (T-1.3, blocked). Anything that applies to a generation belongs in
`generation/preflight.py`, called by both, not copied into each.

---

## 4. Isolation

Two boundaries, enforced differently.

### Postgres — structurally airtight

`TenantScopedRepository._scoped()` returns a `SELECT` pre-filtered by `tenant_id`.
There is no API to bypass it, so an unfiltered query cannot be written. Cross-tenant
access surfaces as 404, never 403 — a 403 would leak the resource's existence.

### The engine tier — enforced on our side

**Open Notebook's search index is global.** `POST /api/search` accepts no notebook
filter; `fn::vector_search` and `fn::text_search` scan every embedding in the instance.
One engine serves every project of every tenant.

Scoping therefore happens in `OpenNotebookClient.search()`, against the engine source
ids recorded on the caller's own tenant-scoped `Source` rows —
`SourceRepository.engine_source_refs()` — not against anything the engine reports about
itself. That is a stronger authority than an engine-returned notebook reference.

It **fails closed**: an empty allow-set issues no request, and a hit whose source cannot
be resolved is dropped. An empty guide is a visible, recoverable bug; a guide grounded
in another tenant's documents is a breach. Availability failures still degrade to no
grounding, which is a different thing and remains correct.

Results are matched on `parent_id`, not `id`: for `source_insight` rows the engine
aliases `id` to the insight's own id, so matching `id` would silently lose recall.

---

## 5. Artifacts and downloads

Two presign paths, deliberately separate — conflating them caused a real defect.

| Path | Audience | Mechanism |
|---|---|---|
| Ingestion | Open Notebook, on `appnet` | Presigned MinIO URL. Works: the consumer is inside the network. |
| Deck download | The user's browser | **Streamed through the orchestrator.** |

MinIO is on `appnet` only, with no Traefik labels and no published ports, so a URL
presigned against `MINIO_ENDPOINT` (`http://minio:9000`) names a host no browser can
resolve. Decks are proxied instead: nothing new is exposed, artifacts stay behind the
existing tenant + RBAC guards, and it composes with the same-origin decision.

Because that endpoint is bearer-authenticated, the client cannot reach it by
navigation — `window.open()` sends no `Authorization` header. It fetches a `Blob` and
saves it via an object URL (`frontend/src/lib/download.ts`).

---

## 6. Jobs

`get_db()` commits at dependency teardown, **after** the handler returns. Enqueuing
inside the handler therefore publishes a job before its row exists.

`JobService.commit_and_dispatch()` commits first. Every generation and ingestion path
uses it. A worker that finds no row raises `JobRowMissing` after an error-level log, so
Arq retries — the previous silent return, combined with `_job_id=idempotency_key` and
`keep_result=3600`, stranded generations at `queued` permanently with no diagnostic.

---

## 7. Known gaps

The engine that renders every slide **exists only as mutable container state on one
host**. It has never been in version control and has no backup. Everything blocked on
that is tracked in [`revamp/TECH-DEBT.md`](../revamp/TECH-DEBT.md); `TD-01` is the root.

Consequences visible in the code today:

- `/editor` routing is unimplemented (§2)
- The editor deep link sends an identifier Presenton has never seen
- **`brand_tokens` are stored correctly and never reach the renderer** — the product's
  headline feature does not function
- `docker compose build` succeeds for 4 of 5 services; `presenton`'s build context
  does not exist

---

## 8. Conventions worth knowing

- **Make failure visible.** The recurring defect class here is: something fails, gets
  replaced with a plausible default, and reports success. Template registration
  returning `"default"` from two nested handlers is the canonical example. New error
  handling must record what happened, not conceal it.
- **Engine ids never reach clients.** `_PUBLIC_PARAM_KEYS` and the response schemas
  enforce this. Expose a capability (a URL), not a handle.
- **Alembic revision ids must be ≤ 32 characters** — `alembic_version.version_num` is
  `varchar(32)`. A longer id passes on SQLite and fails on first deploy to Postgres.
- **Migrations round-trip against Postgres**, not only the SQLite test database.
