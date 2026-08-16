# Technical Assessment — LLM-planned, deterministically-rendered decks

Why the layout-based renderer produced a deck with no logo, why the fix I
first proposed (geometric capacity detection) is the wrong tool, and why
moving *understanding* to an LLM while keeping *execution* deterministic is
the right shape.

**Written:** 2026-08-15 · **Trigger:** the first deck rendered from the real
BRI template arrived missing its logo and design components.

**This is the second architecture pivot in this programme.** That is worth
naming rather than glossing: §6 examines what both pivots have in common, since
a third would be a pattern rather than bad luck.

---

## 1. What failed, with evidence

`deck/renderer.py` built slides from a template's **layouts**. That assumes
design lives in layouts and masters. In the real BRI template it does not:

| | shapes | images |
|---|---|---|
| **30 example slides** | **476** | **57** |
| 45 layouts | 182 | 29 |
| 3 masters | 11 | **0** |

The masters carry **no images at all** — there is no logo to inherit. And the
specific layouts the matcher selected are essentially empty:

| Layout chosen | static shapes | images |
|---|---|---|
| `TITLE_AND_BODY` | **0** | **0** |
| `TITLE_AND_TWO_COLUMNS` | **0** | **0** |
| `SECTION_TITLE_AND_DESCRIPTION` | 1 | 0 |

The design lives on the slides. Slide 21 (timeline) alone is 95 shapes and 3
images; slide 29 is a 39-image logo library.

So the renderer discarded the product and rebuilt from empty skeletons.

### 1.1 Why every test passed anyway

The render suite was written against `python-pptx`'s bundled template, which —
unlike a corporate deck — **does** put its design in layouts. The fixture
shared the code's assumption, so nothing could falsify it. Same shape as
`TD-32`, where every registration "succeeded" against a fake for months.

That is now a standing rule: **the real BRI template is the primary render
fixture** (`PLAN-SLIDE-CLONING.md` §7), and it already caught this.

---

## 2. The correct model: slides are a design vocabulary

A corporate template's slides are a vocabulary — "cover", "divider", "two key
points", "three cards", "nine points", "timeline", "matrix", "closing".
Rendering reuses them:

```
choose which designed slide serves each section
  → clone / reorder those slides
  → replace the text inside them
  → delete the rest
```

Nothing is constructed. This is exactly the process the user's reference
session followed by hand (unpack, read `presentation.xml`, map sections to
slide numbers, set order by `rId`).

**Proven feasible before planning** (`deck/clone.py`, shipped):

| Check | Result |
|---|---|
| Keep a subset + reorder | ✅ design intact (95-shape timeline survives) |
| Clone a slide's shapes | ✅ |
| Clone a slide **with images** | ✅ **only after** remapping `r:embed`/`r:link`/`r:id`; a naive `deepcopy` breaks all three images with `KeyError: rId3` while every shape count still matches |

---

## 3. Why geometric capacity detection is the wrong tool

The first fix proposed inferring capacity from geometry: "three congruent
boxes in a row = a 3-card design that holds 3 items."

That is the hardest part of the whole plan and the least likely to work:

- A slide's shapes include decoration, dividers, icons and background
  rectangles. Distinguishing *three content cards* from *three decorative
  dots* is not reliably a geometric question.
- Grouped shapes nest, so "three congruent groups" may be one group of three
  or three groups of one depending on how the designer built it.
- It is **brittle per template**: tuned against BRI, it would need retuning
  for the next deck, and every failure is silent — the matcher simply picks a
  design that does not fit.

Meanwhile, the same judgement stated as text is easy: *"three boxes at the same
y, equal width, each containing 'Lorem ipsum' placeholder text"* is a
description a language model handles well, and a human can verify at a glance.

**The task is recognition, not computation.** Geometry was the wrong instrument.

---

## 4. The cost insight that changes the decision

Template understanding is **one-time per template**. A template is uploaded
once and used for hundreds of decks, so its analysis cost amortises to
approximately zero — which means we should use the *best* model there, not the
cheapest.

| Work | Frequency | Tokens (in/out) |
|---|---|---|
| **Template cataloguing** (30 slides → design catalog) | **once per template** | ~15,000 / 2,000 |
| **Deck planning** (content + catalog → slide plan) | per generation | ~10,000 / 3,000 |
| Rendering | per generation | **0 — deterministic** |

### 4.1 Cost

Prices are **illustrative tiers, not quotes** — verify against OpenRouter when
choosing (§7). The structure is what matters, not the constants.

**Unit cost**

| | Catalogue a template (once) | Per deck |
|---|---|---|
| Tier A (~$0.30/$0.50 per 1M) | $0.0055 | $0.0045 |
| Tier B (~$0.60/$2.20) | $0.0134 | $0.0126 |
| Tier C (~$1.00/$4.00) | $0.023 | $0.022 |

**Monthly**

| Scenario | Tier A | Tier B | Tier C |
|---|---|---|---|
| 1 template, 100 decks/mo | $0.46 | $1.27 | $2.22 |
| 5 templates, 500 decks/mo | $2.28 | $6.37 | $11.10 |
| 20 templates, 2,000 decks/mo | $9.11 | $25.50 | $44.50 |

**Conclusion:** cataloguing the BRI template with the most expensive tier costs
**$0.023, once**. There is no reason to economise there. The per-deck call is
the only recurring spend, and it stays below the VPS bill at every realistic
volume.

A vision-based variant (render slides to PNG, use a vision model) costs
~$0.03–0.08 once — also trivial. **Cost is not what rules vision out**; the
LibreOffice dependency is (`ASSESSMENT-ARCHITECTURE-2026-08-15.md` §5.3
deliberately avoided it). Keep it as the fallback if text dumps prove
insufficient.

---

## 5. Python vs raw XML — the question contains a false premise

**`python-pptx` *is* XML manipulation.** A `.pptx` is a ZIP of XML parts;
`python-pptx` opens it and exposes those parts through `lxml`. These are not
two approaches.

The real comparison is **raw XML text editing (unzip/edit/rezip)** versus
**`python-pptx`'s object model** — and the shipped `deck/clone.py` already does
raw XML where it matters:

```
copy.deepcopy(shape._element)        # an lxml element
new.shapes._spTree.append(element)   # splice into the shape tree
sldIdLst.remove(entry)               # the same presentation.xml edit, in code
```

| | Raw XML | python-pptx + lxml |
|---|---|---|
| Full OOXML control | ✅ | ✅ (via `._element`) |
| Relationships / content types | **by hand** | automatic |
| Ease of producing an unopenable file | high | low |
| Automated testing | hard | ✅ |
| Fits | one deck, human verifying | a service, unattended |

`python-pptx` is used as a **safe container** for XML work: relationship and
content-type management comes free, and that is precisely what broke when the
naive clone was attempted.

**Why the reference session used raw XML:** in an interactive chat there is no
repo, no dependencies and no suite — unzip/edit/rezip is the shortest path and
a human inspects the result immediately. Optimal for that context.

On "which is more successful": that session succeeded because a human verified
each step for one specific deck. A service must succeed **unattended, across
arbitrary templates**. Different bar, not a better technique.

**Recommendation: keep `python-pptx`, drop to `lxml` where needed.** Moving to
raw-XML-only means reimplementing relationship and content-type management,
which is where corrupt files come from.

---

## 6. What both pivots have in common

Pivot one removed Presenton because an undocumented HTTP contract could not be
verified from inside this codebase. Pivot two is replacing layout-based
rendering because an assumption about where design lives was never tested
against a real artifact.

Both are the same failure: **a load-bearing assumption with no test that could
falsify it.** In the first case the contract lived on another host; in the
second the fixture agreed with the assumption.

The structural answer is in this plan and is not optional:

1. **The real BRI template is the primary fixture**, not a synthetic one.
2. **A human sees the catalog before it is used** — the LLM's reading of the
   template is reviewed once, at onboarding, not trusted silently.
3. **G-gates that require a human opening the file** stay in the exit criteria.
   The suite was fully green while producing a logo-less deck; automated tests
   are necessary here and demonstrably not sufficient.

---

## 7. Model choice — and what I cannot verify

The user has chosen **Kimi K3 via OpenRouter**.

**I cannot confirm that model exists or what it costs.** My knowledge covers
the Kimi K2 line; a K3 is past my cutoff. That is a limit of mine, not a
judgement about the choice — but it means I must not hard-code assumptions
about it.

The design consequence: **the model is configuration, resolved at runtime and
verified at deploy** — never baked into code or tests. Verify before rolling
out:

```bash
curl -s https://openrouter.ai/api/v1/models | \
  jq -r '.data[] | select(.id|test("kimi|moonshot";"i")) |
         [.id, .pricing.prompt, .pricing.completion, .context_length] | @tsv' | column -t
```

Two properties this architecture actually depends on, both worth confirming on
the real model rather than assuming:

| Requirement | Why it matters | If unmet |
|---|---|---|
| **Strict JSON output** (`response_format: json_object`) | Both calls return structured plans; a prose reply fails the generation | Fall back to a JSON-reliable model for these two calls only — per-task routing already exists (`COST-AND-MODEL-STRATEGY.md` §6) |
| **Context ≥ ~32k** | The template dump is ~15k tokens for 30 slides | Chunk the dump per slide (more calls, still one-time) |

Bahasa Indonesia fluency remains the metric that decides the content model, and
remains unmeasurable by script — `scripts/rm12_model_eval.py` exists precisely
to put the generated text in front of a human.

---

## 8. What we are accepting

Stated plainly, because the user has already acknowledged it and it should be
on the record:

**Deck quality now depends on the planning model.** There is no deterministic
scoring layer left as a safety net for *which design fits which content*.

Three things bound that risk, and they are the reason this is an acceptable
trade rather than a gamble:

1. **The catalog is human-reviewed once.** The LLM's understanding of the
   template is corrected at onboarding and then fixed — errors do not recur
   per deck.
2. **The planning call chooses from a closed set.** It selects among catalogued
   designs; it cannot invent one. A bad plan is a wrong *choice*, not a
   corrupt file.
3. **Rendering stays deterministic.** Given a plan, output is reproducible and
   testable. The model cannot produce an invalid `.pptx`.

What is genuinely lost: a model having a bad day produces a poorly-organised
deck, and only a human notices. That is the same bar as the rest of the
product's LLM surfaces (chat, guide, outline), so it is a consistent risk
rather than a new class of one.

---

**Plan:** [`PLAN-LLM-DECK-PLANNING.md`](./PLAN-LLM-DECK-PLANNING.md)
