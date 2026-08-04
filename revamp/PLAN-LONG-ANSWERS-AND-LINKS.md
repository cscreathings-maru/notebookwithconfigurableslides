# Truncated answers and unusable link sources — assessment & plan

Status: **assessed, decisions taken, NOT started.** Written 2026-07-31 from two reports
against the deployed stack: answers cut off mid-sentence, and a URL source that reports
"Siap" but yields nothing.

**Decisions (product owner, 2026-07-31):**

| Question | Decision |
|---|---|
| Build now? | **No — plan only.** Nothing in F1–F5 is implemented. |
| Token ceiling | **8000**, with "Lanjutkan" as the overflow path rather than a higher cap |
| Link sources | **Fail honestly and guide to file upload.** Crawl4AI stays off; F3 descoped |

These are settled; §"Open questions" below is retained only as the reasoning that led
here, not as live questions.

---

## Issue 1 — answers are cut off

### It is not the markdown renderer

The renderer has no length limit. The cause is one line:

```python
# chat/service.py:157
max_tokens=1000,
```

A thousand tokens is roughly 700–800 words of Indonesian, or far less once tables are
involved — which matches the report exactly: the second screenshot stops **inside a
table cell** (`Validasi akurasi segmentasi (target ≥90% akurat`). That is what a token
cap looks like. A rendering fault would drop formatting, not stop mid-word.

For comparison, other callers already use more: `freeform_service` 1400,
`outline_llm_max_tokens` 2000. Chat has the **lowest cap in the codebase** and is the
only surface that produces long prose. It is also hard-coded — not in `config.py`, so
it cannot be tuned per deployment.

### The worse half: truncation is invisible

`engines/llm.py:171` reads only the message content:

```python
text = body["choices"][0]["message"]["content"] or ""
```

`finish_reason` is discarded. The API does return it — an OpenRouter response captured
during debugging this session ended `"finish_reason":"length"` — but nothing carries
it to the client. So a cut-off answer renders identically to a complete one, with no
badge, no warning and no way to continue.

This is the same failure shape as three earlier bugs in this codebase: the engine
said something specific, and we dropped it. A user cannot tell "the model had nothing
more to say" from "we cut it off".

### Options for the long-term ask

| | What it is | Effort | Gets us |
|---|---|---|---|
| **1. Raise + configure the cap** | `chat_llm_max_tokens` in config, default ~4000 | 1h | Stops most truncation immediately |
| **2. Surface `finish_reason`** | Persist it; badge + "Lanjutkan" button when `length` | 0.5 day | Truncation becomes visible and recoverable instead of silent |
| **3. Reader panel** | Long answers collapse in the bubble with "Lihat selengkapnya", opening a full-height reader in the right rail | 1 day | The "popup / new window" that was asked for |
| **4. Streaming (SSE)** | Tokens render as they arrive | 2–3 days | The actual Claude feel: no wall-clock wait, no perceived limit |

**Recommendation: 1 + 2 now, 3 next, 4 when the rest is stable.**

Reasoning: 1 and 2 together remove the bug and the silence for an hour of work.
3 answers the stated request and is independent of streaming. 4 is the biggest UX
win but the biggest change — it alters the response contract, message persistence
(the turn can only be saved once the stream ends), error handling mid-stream, and
the optimistic-bubble logic. Doing 4 first would mean rebuilding it after 1–3 land.

**On the reader panel (3), a design note.** Not a modal — the same reasoning as
`PLAN-CHAT-GENERATION.md` §2. Long answers should open in the **right rail as a third
tab** beside Ringkasan and Studio, so the conversation stays visible next to the full
text. Opening a browser window loses the app shell, the citations and the session.

---

## Issue 2 — a URL source says "Siap" but has no content

Two independent defects, and the second is ours.

### 2a. Open Notebook cannot fetch that page

`OPEN_NOTEBOOK_ENABLE_CRAWL4AI` defaults to **false**
(`docker-compose.lite.yml:210`), and it has never been enabled on the VPS. Without it,
Open Notebook's link path uses a plain fetch: it reads server-rendered HTML and
nothing else.

`https://academy…` is almost certainly a JavaScript-rendered application, and likely
login-gated. A plain fetch of such a page returns an empty shell — no article text —
so there is nothing to chunk and nothing to embed. The chat then answers, correctly,
that it has no relevant information.

**Documented limits of link sources** (from the reference project and this stack's
configuration) — these should be surfaced in the UI, not discovered:

| Works | Does not work |
|---|---|
| Server-rendered articles, blogs, news, docs pages | JavaScript-rendered SPAs, unless Crawl4AI is enabled |
| Public pages | Anything behind a login, paywall or cookie wall — there is no credential path |
| Direct PDF links | Office binaries behind a URL — those must be uploaded |
| External hosts | Internal/private addresses, which SSRF validation rejects |

Enabling Crawl4AI fixes the first row only. It pulls ~150MB of Chromium, and it
installs into `/app/.venv` — **the same volume-less path as Docling (TD-27)**, so it
would be destroyed by the next `--force-recreate` in exactly the same way. TD-27
should be fixed first or the two problems compound.

Nothing fixes an authenticated page. For those the honest answer is "download it and
upload the file", and the UI should say so.

### 2b. We report "ready" without checking anything was extracted

`open_notebook.py:229` decides readiness like this:

```python
if raw in _FAILED_STATES:  return failed
if raw in _READY_STATES:   return ready      # <-- no content check
if await self._is_embedded(source_id): return ready
return processing
```

`"completed"` is in `_READY_STATES`, so an engine command that finished **having
extracted nothing** is reported as ready. The `embedded` fallback below it is only
consulted when the status is ambiguous — the exact case where it matters is skipped.

That is why the rail shows a green "Siap" for a source with no content. It is the same
silent-success pattern as the `.docx` bug fixed earlier this session: a specific
failure replaced by a plausible healthy state.

**A source should only be `ready` when the engine reports both a terminal-success
status and actual embedded content.** Otherwise it is `failed`, carrying the engine's
own reason.

---

## Plan

### Phase F1 — stop truncating, stop hiding it *(~0.5 day)*

- `chat_llm_max_tokens` in `core/config.py`, default **8000**, env-overridable.
  Chosen over 4000 deliberately: the cap is the *safety net*, not the answer-length
  policy. Most replies land far below it, so average cost barely moves; what changes
  is that hitting it becomes rare. Anything still longer is handled by "Lanjutkan"
  rather than by raising the ceiling again
- Capture `finish_reason` in `LlmClient.chat`; return it on `ChatAnswer`
- Persist it on the assistant message; expose on the chat response
- UI: a "jawaban terpotong" badge plus a **Lanjutkan** action that re-prompts with the
  partial answer as context

### Phase F2 — honest source readiness *(~0.5 day)*

- `get_source_status` requires embedded content before reporting ready
- A source that completed with nothing extracted is `failed`, with the engine's reason
- UI: a failed URL source shows why, and offers "unduh lalu unggah berkasnya"
- Regression test: engine says `completed`, `embedded: false`, `embedded_chunks: 0`
  → orchestrator reports **failed**, never ready

### Phase F3 — link limits, documented rather than removed *(~0.25 day)* — **DESCOPED**

Crawl4AI stays **off**. The decision is to make link sources fail honestly rather than
to widen what they can reach — which also avoids compounding TD-27, since Crawl4AI
installs into the same volume-less `/app/.venv` as Docling.

Remaining scope is therefore documentation-in-the-UI only:

- Show the supported/unsupported table above as an inline hint beside the URL field
- A failed URL names the likely cause and points to file upload

Deferred (revisit only if link ingestion becomes a real user need):

- Enabling Crawl4AI for JS-rendered pages — **requires TD-27 closed first**
- Pre-flight fetch check at paste time

Authenticated pages remain out of scope permanently: there is no credential path for
link sources, and "download it and upload the file" is the honest answer.

### Phase F4 — the reader panel *(~1 day)*

- Answers over ~1200 characters collapse with "Lihat selengkapnya"
- Opens as a third right-rail tab: full text, citations, copy, download as `.md`
- Keyboard reachable; scrolls internally; no absolute positioning inside the message
  list (the Phase A clipping constraint)

### Phase F5 — streaming *(2–3 days, separate decision)*

Only after F1–F4. Requires an SSE endpoint, a streaming client reader, persisting the
turn on stream end, and mid-stream error handling. Worth doing, not worth rushing.

---

## Acceptance criteria

**AC-1** Given a question whose full answer exceeds 1000 tokens, when it is answered,
then the reply is complete — and if the model still hits the cap, the message carries
a visible truncation badge.

**AC-2** Given a truncated answer, when "Lanjutkan" is pressed, then the continuation
is appended and the badge clears.

**AC-3** Given a URL the engine cannot extract, when ingestion finishes, then the
source shows **failed** with the engine's own reason — never "Siap".

**AC-4** Given a failed URL source, then the UI states the likely cause and offers the
download-and-upload path.

**AC-5** Given the Sources panel, then the supported/unsupported link types are
visible before a URL is submitted, not after it fails.

**AC-6** Given an answer longer than the collapse threshold, when "Lihat selengkapnya"
is pressed, then the full text opens in the right rail with its citations, and the
conversation remains visible.

**AC-7** *(deferred with F3's Crawl4AI scope)* Enabling Crawl4AI survives
`docker compose up -d --force-recreate open-notebook` — i.e. TD-27 is closed rather
than duplicated. Not in scope while Crawl4AI stays off.

---

## Ordering note

F1 and F2 are independent of each other and of any container change, so either can go
first. F4 depends on nothing but is only worth doing once F1 exists — a reader panel
for answers that are still being truncated would present a complete-looking document
that is in fact cut off, which is worse than the current bubble.

---

## Open questions — resolved, kept as reasoning

1. **Crawl4AI**: enable it (+~150MB Chromium, slower first start) or keep link sources
   limited to server-rendered pages and steer users to file upload?
2. **Truncation cap**: 4000 is a safe default, but with `deepseek-v4-pro` at 1M
   context the ceiling could be far higher. Higher caps cost more per answer — this is
   a budget decision, not a technical one.
3. **Reader panel vs streaming first**: F4 is cheap and answers the request; F5 is the
   real fix for "feels like Claude". They are not mutually exclusive, only ordered.
