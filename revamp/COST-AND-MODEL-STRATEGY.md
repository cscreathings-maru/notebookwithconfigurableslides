# Cost and Model Strategy — in-process renderer

Companion to [`PLAN-MONOLITH-RENDERER.md`](./PLAN-MONOLITH-RENDERER.md). Answers: which
models, where, and what it costs.

**Written:** 2026-08-15

---

## 0. Read this first — two findings that reframe the question

### 0.1 Template fidelity is not a model-quality problem in this architecture

You asked for *"cheap but best render results, where best means following the template."*

**Under the monolith design, no model follows the template. `python-pptx` does.**

Layout fidelity comes from opening your `.pptx` and adding slides from its own masters —
fonts, colours, logo placement and placeholder geometry are inherited from the file,
deterministically, with no model involved (`PLAN` §2.2, D2). The LLM never emits a
coordinate, a colour or a font name; the `SlideSpec` type has no field for one.

So the two halves of your question separate cleanly:

| Goal | Determined by | Model cost |
|---|---|---|
| **Follows the template exactly** | `deck/renderer.py` — deterministic code | **$0** |
| Words are good, in fluent Indonesian | The content model | the only real spend |
| Right layout picked per slide | Deterministic scoring + small LLM tie-break | near $0 |

This is the strongest argument for the monolith that I did not make in the original
assessment: **it moves template fidelity out of the token budget entirely.** Today,
Presenton pays an LLM per slide to reverse-engineer your layouts, and still cannot be
exact. You would be paying for fidelity and not getting it.

### 0.2 At your volume, model price is a rounding error

Full math in §3. The summary, for a typical 12-slide deck:

| Tier | Per deck | 500 decks/mo | 5,000 decks/mo |
|---|---|---|---|
| Budget open-weight | ~$0.005 | **$2.44** | $24 |
| Mid open-weight | ~$0.014 | **$6.92** | $69 |
| Frontier-lite | ~$0.024 | **$12.10** | $121 |

Your Hostinger VPS costs more per month than any of these columns at 500 decks. **Below
roughly 1,000 decks/month, choose on quality and reliability, not price** — the difference
between the cheapest and the most expensive option is under $10/month.

That said, §4 covers the levers that *do* move cost by 5–10×, and none of them is the
model name.

---

## 1. What the model actually has to be good at

With layout removed from its job, the content model is judged on four things:

| # | Requirement | Why it matters here | Cheap models often fail this |
|---|---|---|---|
| 1 | **Bahasa Indonesia fluency** | `DEFAULT_LANGUAGE = "Bahasa Indonesia"` (`freeform_mapper.py:17`). Every deck is Indonesian by default | ⚠️ **Yes.** Many cheap models are benchmarked on English/Chinese. This is your biggest quality risk |
| 2 | **Strict JSON schema compliance** | `LlmClient` already uses `response_format={"type":"json_object"}` (`llm.py:136`). A malformed response fails the whole generation | ⚠️ Varies sharply by model *and* by OpenRouter provider routing |
| 3 | **Respecting character budgets** | The overflow mitigation (`ASSESSMENT` §5.3). "Keep each bullet under 90 characters" is a hard instruction-following test | ⚠️ **Yes.** Weak models ignore length constraints constantly |
| 4 | Summarising source material into slide-shaped content | Core task quality | Generally fine on mid-tier models |

Requirement 3 has a deterministic backstop (truncate at a word boundary, record the
overflow), so a weak model degrades to *shorter* slides rather than broken ones. But a
model that respects budgets natively produces visibly better decks. **This is the thing to
evaluate, and it is not on any public leaderboard.**

---

## 2. On DeepSeek V4 and Kimi V3 specifically

**I cannot verify either of those versions exists.** My knowledge has a cutoff and model
naming moves faster than anything else in this stack — I know the DeepSeek V3 line and the
Kimi K2 line, but I would be guessing about a "V4" or a "K3/V3", and guessing about the
model you are about to build a cost model on is worse than useless.

I have deliberately built §3 as a **formula with tier placeholders** rather than a table of
model names and prices. Plug in whatever OpenRouter actually lists on the day you decide:

```bash
curl -s https://openrouter.ai/api/v1/models | \
  jq -r '.data[] | select(.id|test("deepseek|kimi|moonshot|qwen";"i")) |
         [.id, .pricing.prompt, .pricing.completion, .context_length] | @tsv' | column -t
```

That prints current id, input price, output price and context window for every candidate.
Prices there are **per token**, so multiply by 1,000,000 to compare against §3's tables.

Both families are reasonable candidates on architecture grounds — open-weight, strong
structured-output behaviour, aggressive pricing. **Neither has a track record I can vouch
for on Bahasa Indonesia slide copy**, which is exactly why §5 is an eval and not a
recommendation.

One provider-level caveat that bites people on OpenRouter: a single model id can be served
by several providers with different quantisation, different JSON-mode support and different
prices. Pin the provider explicitly for anything you depend on, or you will see quality
drift with no code change — the same class of invisible-config failure that made your deck
model silently follow the chat model (`docker-compose.lite.yml:227-232`).

---

## 3. The cost model

### 3.1 Token budget per deck

Two LLM calls per generation under the revised pipeline (`PLAN` §2.2).

**Call 1 — content planner (`deck/planner.py`)**

| Component | Tokens |
|---|---|
| System prompt + `DeckSpec` JSON schema | ~1,200 |
| Layout catalogue summary (roles + budgets) | ~600 |
| Source content — **the variable** | 3,000–25,000 |
| **Output:** `DeckSpec` JSON, ~250 tok/slide | 2,000–5,500 |

**Call 2 — layout tie-break (`deck/matcher.py`)** — only for ambiguous slides

| Component | Tokens |
|---|---|
| System prompt + shortlisted layouts | ~800 |
| Per-slide summaries (title, bullet count, has_chart) | ~600 |
| **Output:** assignment JSON | ~400 |

### 3.2 Three scenarios

| Scenario | Slides | Source | Input | Output |
|---|---|---|---|---|
| Light | 8 | 3k | ~5,000 | ~2,000 |
| **Typical** | **12** | **8k** | **~10,600** | **~3,400** |
| Heavy | 20 | 25k | ~28,000 | ~5,500 |

### 3.3 The formula

```
cost_per_deck = (input_tokens × price_in + output_tokens × price_out) ÷ 1,000,000
```

### 3.4 Worked table

Prices are **illustrative tiers, not quotes** — verify with the `curl` in §2.

| | Tier A ($0.30/$0.50) | Tier B ($0.60/$2.20) | Tier C ($1.00/$4.00) |
|---|---|---|---|
| Light | $0.0025 | $0.0074 | $0.0130 |
| **Typical** | **$0.0049** | **$0.0138** | **$0.0242** |
| Heavy | $0.0112 | $0.0289 | $0.0500 |
| **500 decks/mo (typical)** | **$2.44** | **$6.92** | **$12.10** |
| 5,000 decks/mo (typical) | $24.40 | $69.20 | $121.00 |

**Conclusion: pick on quality.** A 5× price difference is $10/month at realistic volume.

---

## 4. The levers that actually move cost

Ranked by impact. None of these is the model name.

### 4.1 🔴 Feed the outline, not the raw sources — up to 10× on input

The single largest lever. If `_resolve_content` hands the planner an entire notebook
(30–50k tokens), input cost dominates everything else and grows with the user's document
library.

You already produce a compact structured outline (`outline/schema.py`) and a guide.
**Feed those.** Source → outline is already an LLM step; do not then also re-send the raw
sources to the planner. Typical drops from ~10,600 to ~4,000 input tokens.

This is an architectural decision in `RM-6`, not a tuning knob — get it right at build time.

### 4.2 🟠 One call per deck, not one per slide — ~10×

Per-slide calls re-send the system prompt and schema every time (~1,800 tokens × 12 = 21,600
tokens of pure overhead) and lose narrative flow between slides. One call for the whole deck
is cheaper *and* produces a more coherent deck.

Reserve per-slide calls for a future "regenerate just this slide" action, where the user has
explicitly asked and the cost is obviously theirs.

### 4.3 🟠 Prompt caching — 50–90% off the stable prefix

System prompt + schema + layout catalogue (~1,800 tokens) is **byte-identical across every
generation using the same template**. Most providers price cache hits far below fresh
input. Order the prompt so the stable prefix comes first and the variable content last —
free to do at build time, impossible to retrofit cheaply once prompts are interleaved.

### 4.4 🟡 Retry discipline

A malformed-JSON retry doubles that generation's cost. Cap retries at 2, and log the
model id on every failure — if one model is retrying 20% of the time, its real price is
1.2× its listed price, which may reverse the ranking.

### 4.5 🟡 Regeneration loops

If a user regenerates 5× because the deck is wrong, cost is 5×. **The layout review step
(`RM-8`) is a cost control as much as a UX feature** — catching "wrong layout for slide 7"
in a review screen costs nothing, versus a full regenerate.

---

## 5. What removing Presenton saves

Not the headline reason to do it, but it is a real credit, and it runs the other way from
what you might expect:

| Current cost | Under the monolith |
|---|---|
| **Template registration** runs an LLM per slide to generate HTML layouts (`/template/async` — this is why it takes minutes). A 20-slide template ≈ 20 calls ≈ 100k tokens | **$0** — inspection is a local `python-pptx` parse, sub-second |
| Every re-register attempt pays that again | `reinspect` is free |
| **Deck generation** runs Presenton's *own* LLM (`CUSTOM_MODEL`) on top of your outline call | One call you control |
| Two LLM configs, one of them unobservable | One config, per-task routed (§6) |

**Your current per-deck LLM cost is probably higher than the monolith's**, because you pay
your model for the outline and Presenton's model for the slides. You just cannot see the
second invoice line, because it is billed against the same OpenRouter key with no
attribution.

---

## 6. Model routing — per task, not one global model

The pipeline has heterogeneous tasks. One global `OPENROUTER_MODEL` is what let the deck
engine silently inherit the chat model (`docker-compose.lite.yml:227-232`). Do not rebuild
that.

| Task | Calls | Quality need | Recommendation |
|---|---|---|---|
| Chat / guide | Many per session | **High** — user-facing prose | Existing config, unchanged |
| Outline drafting | 1 per deck | Medium-high | Same tier as content |
| **Deck content planning** | **1 per deck** | **High** — Indonesian, budgets, JSON | **The one to spend on.** Mid-tier |
| **Layout tie-break** | 0–1 per deck | Low — pick from a shortlist of 2–3 | Cheapest reliable JSON model |
| Chart data extraction | 0–1 per deck | Medium — numeric accuracy | Same as content, or deterministic parse |

**Design:** extend `TenantLlmConfigService` (`tenancy/llm_config.py`) with optional
per-task model overrides, falling back to the tenant default when unset. Log the resolved
model id on every call — you cannot cost-attribute what you do not record, and right now
nothing tells you which model produced which deck.

Provider pinning belongs here too (§2).

---

## 7. Settle it with an eval, not with vibes — `RM-12`

You have 264 backend tests and a documented evidence-first culture. Model choice deserves
the same treatment, and it is cheap: **~30 generations, well under $1 total.**

**Fixture:** 5 representative source documents — one BRI-style corporate report, one
meeting transcript, one long `.docx`, one short custom markdown, one chat summary. Commit
them.

**Candidates:** 3 models — your current default, plus the two cheapest credible options
from §2's `curl`.

**Score each on:**

| Metric | How | Pass bar |
|---|---|---|
| JSON validity | `DeckSpec` parses first try | ≥ 98% |
| Budget compliance | % of bullets within the placeholder budget | ≥ 90% |
| Indonesian fluency | **Human 1–5 rating** — the only one that needs a person | ≥ 4.0 |
| Layout-role validity | Never requests a role absent from the catalogue | 100% |
| Cost | Actual tokens billed | record |
| Latency | p50, p95 | < 30s p95 |

Record to `revamp/reports/RM-12-MODEL-EVAL.md`. Re-run when you change models — it is the
regression test for a dependency that changes underneath you without a version bump.

**Do not skip the fluency rating.** It is the one metric that cannot be automated, the one
your users will actually judge, and the one where a cheap model is most likely to lose.

---

## 8. Recommendation

1. **Do not optimise model price yet.** At 500 decks/month the spread is under $10.
2. **Build §4.1 (feed the outline) and §4.3 (cache-friendly prompt order) into the code
   now.** They are 10× and 5× levers respectively, and both are architectural — expensive
   to retrofit, free at build time.
3. **Route per task (§6)** from day one. Cheapest reliable model for the layout tie-break,
   mid-tier for content.
4. **Run the eval (§7)** before locking the content model. Budget compliance and Indonesian
   fluency will decide it, and neither is predictable from price or benchmarks.
5. **Revisit price only above ~2,000 decks/month.** Below that, engineering time spent
   saving $5/month is the most expensive thing in this document.
