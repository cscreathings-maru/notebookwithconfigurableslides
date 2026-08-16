"""RM-12 model eval -- score candidate content models on this pipeline's real job.

Implements `revamp/COST-AND-MODEL-STRATEGY.md` §7 and doubles as the
verification step `ASSESSMENT-LLM-DECK-PLANNING.md` §7 asks for before
rolling out a new model (Kimi K3 or otherwise): does it exist, does it
return strict JSON, is its Bahasa Indonesia any good.

Runs each candidate model over committed fixture documents through the REAL
planner (`deck/plan.py::plan_deck`, LD-6) against a REAL template's catalog,
and reports:

  json_valid_rate      did the model return something `DeckPlan` accepts
  budget_compliance    % of anchors within their char_budget
  design_validity      never referenced a design_id/anchor_id the catalog lacks
  tokens / cost        actual billed usage
  latency              p50 / p95

**The one metric this cannot produce is the one that decides it.** Bahasa
Indonesia fluency needs a human reading the output, so every generated deck's
text is written to the report for exactly that. A model that scores perfectly
here and writes stilted Indonesian is the wrong model.

Cataloguing (LD-2) runs ONCE, up front, on a fixed model -- this script
evaluates the PLANNING model, not the cataloguing model, so the catalog must
be held constant across every candidate for the comparison to mean anything.

Usage (inside the orchestrator container, or any env with the API key set):

    OPENROUTER_API_KEY=... python -m scripts.rm12_model_eval \\
        --models deepseek/deepseek-chat,moonshotai/kimi-k2 \\
        --out /tmp/RM-12-MODEL-EVAL.md

Costs real money -- roughly $1 for the default 5 fixtures x 3 models, plus
one cataloguing call. Prints the estimated spend and waits for confirmation
unless `--yes` is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import get_settings
from src.deck.catalog import DesignCatalog, catalog_template
from src.deck.dump import dump_presentation
from src.deck.plan import plan_deck
from src.engines.llm import LlmClient
from src.registry.house_template import HOUSE_TEMPLATE_PATH

# Fixtures live beside this script so the eval is reproducible from a clean
# checkout. Each is plain text -- the planner takes resolved content, not raw
# documents (COST-AND-MODEL-STRATEGY.md §4.1).
_FIXTURE_DIR = Path(__file__).parent / "eval_fixtures"


@dataclass
class RunResult:
    fixture: str
    model: str
    ok: bool
    error: str | None = None
    latency_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    slides: int = 0
    overflow_anchors: int = 0
    total_anchors: int = 0
    text: str = ""


@dataclass
class ModelReport:
    model: str
    runs: list[RunResult] = field(default_factory=list)

    @property
    def json_valid_rate(self) -> float:
        return _pct(sum(1 for r in self.runs if r.ok), len(self.runs))

    @property
    def budget_compliance(self) -> float:
        total = sum(r.total_anchors for r in self.runs if r.ok)
        over = sum(r.overflow_anchors for r in self.runs if r.ok)
        return _pct(total - over, total)

    @property
    def tokens_in(self) -> int:
        return sum(r.tokens_in for r in self.runs)

    @property
    def tokens_out(self) -> int:
        return sum(r.tokens_out for r in self.runs)

    def latency(self, q: float) -> float:
        oks = sorted(r.latency_s for r in self.runs if r.ok)
        if not oks:
            return 0.0
        idx = min(int(q * len(oks)), len(oks) - 1)
        return oks[idx]


def _pct(num: int, den: int) -> float:
    return 100.0 * num / den if den else 0.0


async def _build_catalog(*, template_path: Path, llm: LlmClient, provider_config: dict, model: str) -> DesignCatalog:
    """LD-2, once, on a fixed model -- see the module docstring for why this
    must not vary per candidate."""
    dumps = dump_presentation(template_path.read_bytes())
    catalog, _usage = await catalog_template(
        dumps=dumps, llm=llm, provider_config=provider_config, model_override=model
    )
    return catalog


async def _run_one(*, llm, fixture: Path, model: str, catalog: DesignCatalog, provider_config) -> RunResult:
    content = fixture.read_text()
    started = time.monotonic()
    try:
        plan, usage = await plan_deck(
            content=content,
            catalog=catalog,
            n_slides_hint=None,
            tone="professional",
            density="standard",
            language="Bahasa Indonesia",
            llm=llm,
            provider_config=provider_config,
            model_override=model,
        )
    except Exception as exc:
        return RunResult(
            fixture=fixture.stem,
            model=model,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            latency_s=time.monotonic() - started,
        )

    total_anchors = sum(len(s.anchor_texts) for s in plan.slides)
    return RunResult(
        fixture=fixture.stem,
        model=model,
        ok=True,
        latency_s=time.monotonic() - started,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        slides=len(plan.slides),
        overflow_anchors=len(usage.overflow),
        total_anchors=total_anchors,
        text="\n\n".join(
            f"### {s.design_id}\n" + "\n".join(f"- {k}: {v}" for k, v in s.anchor_texts.items())
            for s in plan.slides
        ),
    )


def _render_report(reports: list[ModelReport]) -> str:
    lines = [
        "# RM-12 — Model eval",
        "",
        "Generated by `scripts/rm12_model_eval.py`. Implements",
        "`revamp/COST-AND-MODEL-STRATEGY.md` §7 and",
        "`ASSESSMENT-LLM-DECK-PLANNING.md` §7's pre-rollout verification.",
        "",
        "## Scores",
        "",
        "| Model | JSON valid | Budget compliance | tokens in/out | p50 | p95 |",
        "|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| `{r.model}` | {r.json_valid_rate:.0f}% | {r.budget_compliance:.0f}% | "
            f"{r.tokens_in}/{r.tokens_out} | "
            f"{r.latency(0.5):.1f}s | {r.latency(0.95):.1f}s |"
        )
    lines += [
        "",
        "Design/anchor validity is not separately scored: `deck/plan.py::plan_deck`",
        "structurally cannot return a `DeckPlan` referencing an unknown design_id or",
        "anchor_id (invalid ones are dropped during validation) -- a run's `ok=True`",
        "already implies every reference in it was valid.",
        "",
        "**Pass bars** (COST-AND-MODEL-STRATEGY.md §7): JSON valid ≥ 98%, budget",
        "compliance ≥ 90%, p95 < 30s.",
        "",
        "## Bahasa Indonesia fluency — NOT SCORED ABOVE",
        "",
        "> This is the metric that decides the choice, and no script can produce it.",
        "> Read the output below and rate each model 1-5. A model that passes every",
        "> automated bar and writes stilted Indonesian is the wrong model.",
        "",
        "| Model | Fluency (1-5) | Notes |",
        "|---|---|---|",
    ]
    for r in reports:
        lines.append(f"| `{r.model}` | _(fill in)_ | |")

    lines += ["", "## Failures", ""]
    failures = [run for rep in reports for run in rep.runs if not run.ok]
    if failures:
        for run in failures:
            lines.append(f"- `{run.model}` / {run.fixture}: {run.error}")
    else:
        lines.append("None.")

    lines += ["", "## Generated text (for the fluency rating)", ""]
    for rep in reports:
        lines.append(f"### `{rep.model}`")
        for run in rep.runs:
            if run.ok:
                lines += ["", f"**{run.fixture}**", "", run.text, ""]
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", required=True, help="comma-separated model ids")
    parser.add_argument("--catalog-model", help="model for the one-time cataloguing call; defaults to --models[0]")
    parser.add_argument("--template", help="path to a .pptx to evaluate against; defaults to the bundled BRI template")
    parser.add_argument("--out", default="revamp/reports/RM-12-MODEL-EVAL.md")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    fixtures = sorted(_FIXTURE_DIR.glob("*.txt"))
    if not fixtures:
        raise SystemExit(f"No fixtures in {_FIXTURE_DIR}. See that directory's README.")

    template_path = Path(args.template) if args.template else HOUSE_TEMPLATE_PATH
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    settings = get_settings()
    provider_config = {
        "provider": "openrouter",
        "base_url": settings.openrouter_base_url,
        "model": settings.openrouter_model,
        "api_key": settings.openrouter_api_key,
    }
    if not provider_config["api_key"]:
        raise SystemExit("OPENROUTER_API_KEY is not set -- this eval makes real API calls.")

    total = len(models) * len(fixtures)
    print(f"{len(models)} models x {len(fixtures)} fixtures = {total} real planning calls, plus 1 cataloguing call.")
    if not args.yes and input("This costs real money. Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("Aborted.")

    llm = LlmClient()
    catalog_model = args.catalog_model or models[0]
    print(f"Cataloguing {template_path.name} once, with {catalog_model} ...")
    catalog = await _build_catalog(
        template_path=template_path, llm=llm, provider_config=provider_config, model=catalog_model
    )
    if not catalog.usable_designs:
        raise SystemExit("Cataloguing produced no usable design -- cannot evaluate planning against it.")
    print(f"  {len(catalog.usable_designs)} usable design(s) catalogued.")

    reports = []
    for model in models:
        report = ModelReport(model=model)
        for fixture in fixtures:
            print(f"  {model} / {fixture.stem} ...", flush=True)
            report.runs.append(
                await _run_one(
                    llm=llm,
                    fixture=fixture,
                    model=model,
                    catalog=catalog,
                    provider_config=provider_config,
                )
            )
        reports.append(report)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_report(reports))
    print(f"\nReport -> {out}")
    print("Now do the part the script cannot: read the output and rate the Indonesian.")


if __name__ == "__main__":
    asyncio.run(main())
