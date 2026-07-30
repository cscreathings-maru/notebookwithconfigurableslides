# Plan — Open Notebook ingestion, then slide generation

Priority as stated: **fix Open Notebook first, slides second.**

Everything below is grounded in the 2026-07-30 03:09 worker run and in
`lfnovo/open_notebook:v1-latest` read directly. Anything **UNVERIFIED** is marked.

---

## What that run actually proved

The queue reconciliation worked — `found: 2, enqueued: 2` — and the two stranded jobs ran.
They did not both fail:

| Source | Engine states | Outcome |
|---|---|---|
| `source:4dorihyuxggkiiksyzp6` | `new → running → completed` | **ready** ✓ |
| `source:af5jjai9g3os0nq7r88u` | `new → failed` | **failed** ✗ |

**Open Notebook is not broken.** One source went through the entire pipeline — fetch,
extract, embed, index — in 7.15s. SurrealDB, the embedding provider and the API all work.

So the earlier hypothesis that no embedding model was configured is **disproven**. A
missing embedding model could not have produced a `completed` source.

**One file fails.** From the UI those two sources are `00-overview.md` (TEXT) and
`Panduan Onbo…` (OFFICE). The likely failing one is the OFFICE file, which needs a
document extractor the `.md` file does not.

---

## Findings from the run and the engine source

**F1 — The engine explains itself; we discarded it.** `SourceStatusResponse` declares
`message` as **required** plus optional `processing_info`. `get_source_status()` read only
`status`. The user saw *"Analysis failed for this source."* — a string this codebase wrote.
**Fixed** (`c18622e`): the engine's reason now reaches `Source.error`.

**F2 — `POST /api/sources/json` returned 500, then 200 on retry.** The T-2.3 backoff
absorbed it, so it cost 1s instead of a failed ingest. Worth knowing the engine is flaky
under first contact; not worth acting on yet.

**F3 — The engine guards uploads, not URLs.** `_assert_file_supported` rejects
unextractable **file uploads** with 415 up front, added specifically to avoid *"a
background job that fails and then burns the full retry budget before surfacing a generic
error"* (their issue #975). We send `type: "link"` with a presigned URL, so that guard
never runs for us — extraction failure surfaces only as a background `failed`.

**F4 — `PRESENTON_URL=deck.umarsyukri.com`, with no scheme.** That is why `/api/readyz`
reported Presenton `down / UnsupportedProtocol` while the container was healthy. It is
also what the orchestrator uses for every engine call. **Config bug on the deployment**,
now reported as `misconfigured` rather than an outage.

---

## Phase N-1 — Make the failure legible *(done, needs deploying)*

| Task | State |
|---|---|
| N-1.1 Capture `message` + `processing_info` into `Source.error` | **done** `c18622e` |
| N-1.2 Timeout carries the last engine status | **done** `c18622e` |
| N-1.3 Fix `PRESENTON_URL` to include `http://` | **OPEN** — one-line env edit |

**Gate N-1:** the failed source's row carries the engine's own explanation, visible in the
UI and via `GET /api/v1/projects/{id}/sources`.

---

## Phase N-2 — Fix the actual extraction failure

**Cannot be specified until N-1 is deployed and the real message is read.** Guessing here
would repeat the mistake this programme keeps correcting. The plan branches on what the
message says:

| If the engine says | Then |
|---|---|
| Unsupported type / no extractor | **N-2a** — decide supported formats and reject at upload |
| Fetch failed / 403 / expired | **N-2b** — presign TTL vs. engine fetch timing |
| Extraction crashed on this file | **N-2c** — file-specific; try a re-upload, then report upstream |
| Embedding/model error | **N-2d** — provider config, despite the other source succeeding |

### N-2a — Reject unsupported formats at upload *(most likely)*

The engine already does this for uploads and returns 415. We bypass it by sending a URL,
so we should do the equivalent ourselves:

- Add a supported-extension allowlist to `ingestion/kinds.py`, sourced from what the
  engine's extractor actually handles — **read it, do not assume**.
- Reject at `POST /projects/{id}/sources` with a clear message naming the extension,
  **before** a job is enqueued. A user learns immediately instead of watching "Antre"
  for three days.
- Keep the engine-side failure path as the backstop; a pre-flight check is not a
  guarantee.

### N-2b — Presign TTL

`ingest_source` regenerates the presigned URL at run time, so a stale URL is unlikely.
But `ingest_presign_ttl_seconds` must exceed the engine's queue delay plus download time.
**UNVERIFIED** — worth confirming against the configured value if the message points at
fetching.

---

## Phase N-3 — Stop sources from going quiet

Even with a legible error, the pipeline has two remaining silences:

- **N-3.1 Surface `Source.error` in the UI.** The API returns it; the sources list shows
  only a status pill. A failed source should show *why*, on hover or inline.
- **N-3.2 Add a retry action.** `POST /sources/{id}/reingest`, mirroring the template
  re-register: a failed source is currently terminal, and re-uploading is the only route.
- **N-3.3 A source stuck in `processing` past the poll budget is invisible.** The job
  raises and Arq retries, but nothing tells the user. Show elapsed time, or mark stalled.

---

## Phase N-4 — Then slides

Only after ingestion is dependable, because every slide path depends on grounding.

| Task | Depends on |
|---|---|
| N-4.1 Verify the guide generates from a `ready` source | N-2 |
| N-4.2 Verify chat cites only that project's sources (T-2.1 in practice) | N-2 |
| N-4.3 Get one template to `registration_status: registered` | `/reregister`, deployed |
| N-4.4 Generate a deck from that branded template | N-4.3 |
| N-4.5 **Download it and confirm the branding is present** — gate G3 | N-4.4 |

**N-4.5 is the programme's outstanding gate.** Everything for it is now in place except a
registered template.

---

## Order

```
N-1.3 (fix PRESENTON_URL)  →  deploy N-1  →  READ THE MESSAGE  →  N-2x  →  N-3  →  N-4
```

The third step is not a formality. Four contracts in this programme were assumed and all
four were wrong — the theming path, the registration payload, the editor route, the search
filter. The engine will say what happened; the plan should follow that, not precede it.

---

## Immediate command

The failed source's reason is already retrievable from the engine directly, without
waiting for a deploy:

```bash
cd /var/www/notebookfinal && docker compose -f deploy/docker-compose.lite.yml \
  --env-file deploy/.env.lite exec -T open-notebook \
  curl -s http://localhost:5055/api/sources/source:af5jjai9g3os0nq7r88u/status
```

That returns the `message` and `processing_info` this plan branches on.
