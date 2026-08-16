# Plan — Render by cloning designed slides

Course-correction to [`PLAN-MONOLITH-RENDERER.md`](./PLAN-MONOLITH-RENDERER.md).
The monolith decision (drop Presenton, render in-process with `python-pptx`)
stands. **How** we render changes.

**Written:** 2026-08-15 · **Trigger:** the first real BRI deck rendered with
missing logo and missing design components.

---

## 1. What went wrong, with evidence

`deck/renderer.py` (RM-8) strips a template's slides and builds new ones from
its slide **layouts**. That assumes design lives in layouts and masters. In the
real BRI template it does not:

| | shapes | images |
|---|---|---|
| **30 example slides** | **476** | **57** |
| 45 layouts | 182 | 29 |
| 3 masters | 11 | **0** |

The masters carry **no images at all**, so there is no logo to inherit. And the
specific layouts the matcher chose are near-empty:

| Layout chosen by RM-7 | static shapes | images |
|---|---|---|
| `TITLE_AND_BODY` | **0** | **0** |
| `TITLE_AND_TWO_COLUMNS` | **0** | **0** |
| `SECTION_TITLE_AND_DESCRIPTION` | 1 | 0 |
| `TITLE` | 2 | 0 |

The design lives on the slides: slide 21 (timeline) is 95 shapes + 3 images,
slide 20 (nine points) is 21 shapes, slide 29 (logo library) is 41 shapes + 39
images.

So RM-8 threw away the product and rebuilt from empty skeletons. RM-15 made it
worse by *stripping those 30 slides* from the house template to save 14MB —
the 14MB was the design.

### Why the original reasoning still looks right in isolation

`python-pptx`'s own bundled template DOES put design in layouts, which is what
every test asserted against. The fixture agreed with the assumption, so nothing
failed until a real corporate deck arrived. **A fixture that shares your
assumption cannot falsify it** — the same shape of gap as `TD-32`, where every
registration "succeeded" against a fake.

---

## 2. The corrected model

A corporate template's slides are a **design vocabulary**: "cover", "divider",
"two key points (blue)", "three cards", "nine points", "timeline", "matrix",
"closing". Rendering is:

```
pick which designed slide serves each section
  -> keep/duplicate/reorder those slides
  -> replace the text inside them
  -> delete the rest
```

Nothing is constructed; existing design is *reused*. This is the process the
user's reference session followed (unpack, read `presentation.xml`, map
sections to slide numbers, set slide order by `rId`).

### 2.1 Feasibility — proven before planning

| Check | Result |
|---|---|
| Keep a subset + reorder | ✅ design intact (95-shape timeline survives) |
| Duplicate a slide's shapes | ✅ |
| Duplicate a slide **with images** | ✅ **after** remapping `r:embed`/`r:link`/`r:id` to the new slide's rels — a naive `deepcopy` breaks all three images with `KeyError: rId3` |

The remap is the load-bearing detail. It is spiked and working before this plan
was written, not assumed by it.

---

## 3. Locked decisions

| # | Decision | Consequence |
|---|---|---|
| **S1** | Render by cloning designed slides, not by building from layouts | `deck/renderer.py` is replaced, not patched |
| **S2** | **Capacity-first matching.** The matcher counts the content's components and looks for a design that holds exactly that many | Each design carries a capacity (a "3 cards" slide holds 3 items) |
| **S3** | **No fitting design → split across repeats of one design**, with `(lanjutan)` appended to continuation titles | 5 points into a 3-card design becomes two slides: "Manfaat" + "Manfaat (lanjutan)" |
| **S4** | A design may be used **any number of times** in one deck; the matcher decides from what the template offers | Image-safe cloning is mandatory, not optional |
| **S5** | The house template keeps **all 30 slides** | RM-15's strip is reverted; file returns to ~16.6MB |

---

## 4. What survives, what is rebuilt

**Survives (~50–60%)** — Presenton removal (RM-13), the unified generation
service (RM-11), `deck/planner.py`'s content-only contract, character budgets
(they become per-design capacity), the matcher's deterministic-scoring +
review-gate design (RM-7/RM-9), the review UI (RM-10 — data shape shifts, the
component largely stands), native charts, and every migration already applied.

**Rebuilt** — `deck/inspect.py` (catalog slides, not layouts), `deck/roles.py`
(design vocabulary with capacity), `deck/renderer.py` (clone/reorder/replace),
`deck/preview.py` (wireframe a slide), plus a `slide_catalog` migration.

This is a course correction, not a restart.

---

## 5. Tasks

| # | Task | Sev |
|---|---|---|
| **SC-0** | `deck/clone.py` — image-safe slide cloning. **Spiked and proven.** Tests pin the `r:embed` remap, because a naive copy silently corrupts images | 🔴 |
| **SC-1** | `deck/slides.py` — inspect a template's SLIDES into a `DesignCatalog`: per design, its role, its **capacity** (how many repeated components it holds), and its text anchors | 🔴 |
| **SC-2** | Capacity detection — group a slide's shapes into repeated components (3 cards = 3 congruent groups). The one genuinely hard inference; falls back to "1 item" when unsure rather than guessing high | 🔴 |
| **SC-3** | `deck/spec.py` — content carries item counts; planner is told each design's capacity | 🟠 |
| **SC-4** | `deck/matcher.py` — capacity-first (S2), then split with `(lanjutan)` (S3), then repeat designs freely (S4) | 🔴 |
| **SC-5** | `deck/renderer.py` — clone/reorder/replace; delete unused slides last | 🔴 |
| **SC-6** | Migration `slide_catalog`, service + worker wiring | 🟠 |
| **SC-7** | Restore the full 30-slide house template (revert RM-15's strip) | 🟠 |
| **SC-8** | Preview + review UI against designs | 🟡 |

---

## 6. Exit gate

| # | Criterion |
|---|---|
| G1 | A rendered deck **keeps the BRI logo and design furniture** — the failure that triggered this plan |
| G2 | A human opens the deck and confirms it looks like the template |
| G3 | Cloning a slide with images produces readable images (`pic.image.blob` succeeds) |
| G4 | 5 items into a 3-capacity design produces two slides, the second titled `… (lanjutan)`, with **no content dropped** |
| G5 | One design used 4× in a deck renders 4 intact copies |
| G6 | Determinism holds; suites green; ruff/eslint/typecheck clean |

**G1 and G2 cannot be closed by automated tests.** The suite was fully green
while producing a deck with no logo — that is precisely the failure mode here,
and it is why the gate names a human.

---

## 7. Fixture discipline (the process fix)

Every test that asserted rendering was correct passed against a template whose
design lived in layouts. Going forward, **the real BRI template is the primary
render fixture**, not `python-pptx`'s bundled one. A synthetic fixture may
supplement it; it may not stand in for it.
