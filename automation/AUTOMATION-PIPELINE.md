# Automation Pipeline — Claude plans, DeepSeek codes

The development build loop for this project, using multiple models for what each is best at, with a
human gate at every slice. This replaces "one big MetaGPT run" with a controlled, multi-model loop.

## Why this shape

You wanted: an orchestrator ("Hermes"), Claude as the brain (planning + evaluation), DeepSeek for
code execution, and the two product engines on their best providers. The cleanest way to get a
"reasoner plans / cheaper model codes" loop on a real repo is **Aider's architect/editor mode** —
it natively takes a **reasoning model** to plan a change and a separate **editor model** to write
the diff, edits files in your git repo, runs your tests, and commits. So you don't need a separate
Hermes component; Aider *is* the inner-loop orchestrator, and Cowork (Claude) is the orchestrator
across slices and the evaluator at each gate.

## Role → model mapping

| Role | Model | Where it runs |
|------|-------|---------------|
| Spec / plan / tasks authoring + upkeep | **Claude** (Cowork = me) | here, in this folder |
| In-loop change planning / architecture | **Claude** (Aider *architect* model) | Aider on your machine/VPS |
| Code writing + edits | **DeepSeek** (Aider *editor* model) | Aider on your machine/VPS |
| Run tests + fix failures | **DeepSeek** (editor loop) | Aider + your test command |
| Slice-gate review + eval grading | **Claude** (Cowork = me) + automated eval suite | here + CI |
| Human approval | **You** | slice checkpoint |
| Product runtime LLM (the app itself) | **DeepSeek** (+ embeddings provider) | Open Notebook / Presenton |

Claude appears twice on purpose: as Aider's *architect* during a change, and as the independent
reviewer/evaluator at the gate (a second pair of eyes that didn't write the code).

## The per-slice loop (human-gated)

For each slice (`metagpt/prompts/slice-*.md` → mapped phases in `tasks.md`):

1. **Plan (Claude / Cowork)** — I turn the slice + relevant `contracts/` into a concrete
   change-plan: files to touch, acceptance checks, tests to write first.
2. **Build (Aider: Claude architect + DeepSeek editor)** — you run Aider on the slice. The
   architect (Claude) proposes the approach; the editor (DeepSeek) writes the code and tests,
   running your test command until green.
3. **Commit** — Aider commits to a `slice-N` branch.
4. **Evaluate (Claude / Cowork + suite)** — you bring the diff back to me; I review it against the
   contracts and the constitution and run the gate checklist below; the automated contract +
   consistency evals must pass.
5. **Gate (You)** — pass → merge and start the next slice; fail → I produce fix instructions and
   we loop back to step 2.

This keeps automation high *inside* a slice while you retain a checkpoint between slices — the safe
default for multi-tenant, security-sensitive code.

## Gate checklist (every slice)

- Cross-tenant access returns 404 (isolation contract test green).
- Engines remain internal — no published ports, no engine ids/URLs leaked to clients.
- New endpoints match `contracts/orchestrator-api.md`; engine calls match `contracts/engine-integration.md`.
- For slice 3+: consistency eval passes (same project+profile+template version → same section structure).
- Provenance + metering recorded for any generation path.
- Tests written first and passing; lint/type-check clean.

## Tooling setup (your machine / VPS)

Install Aider and set both keys (see `aider.conf.example.yml` and `.env.example` in this folder):

```bash
pip install aider-install && aider-install     # or: pipx install aider-chat
export ANTHROPIC_API_KEY=...        # Claude  (architect / planning)
export DEEPSEEK_API_KEY=...         # DeepSeek (editor / coding)
```

Run a slice in architect mode (Claude plans, DeepSeek edits):

```bash
cd notebookllm-platform        # your code repo (backend/ frontend/ deploy/)
aider --architect \
  --model anthropic/claude-sonnet-4-5 \
  --editor-model deepseek/deepseek-chat \
  --test-cmd "pytest -q" --auto-test \
  --message-file /path/to/specs/.../metagpt/prompts/slice-0-platform-skeleton.md
```

Review the diff, let it run tests, then commit on a slice branch. Repeat per slice. (Use
`deepseek-reasoner` as the editor only if you want heavier reasoning during coding; `deepseek-chat`
is the cost-effective default.)

> MetaGPT is now **optional** — handy only to bootstrap a greenfield first draft of a slice. For
> the "Claude-plans / DeepSeek-codes" loop on an evolving repo, Aider's architect/editor split is
> the better fit. If you do use MetaGPT with per-role models, that requires a small Python runner
> (see `metagpt/config2.example.yaml` note).

## Engine provider choices ("best options based on the repo")

**Open Notebook** (analysis):
- LLM / chat / transformations → **DeepSeek** (supported as an LLM provider).
- Embeddings → DeepSeek is **not** an embedding provider, so pick a separate one. For data
  residency on your VPS, run **local embeddings via Ollama** (e.g. `bge-m3`/`nomic-embed-text`);
  if external is acceptable, OpenAI/Mistral/Voyage embeddings also work.
- STT/TTS (podcasts) → out of scope for the MVP; leave unset.

**Presenton** (generation):
- LLM → **DeepSeek** via its OpenAI-compatible "custom" provider (already wired in
  `deploy/docker-compose.yml`).
- Images → **Pexels/Pixabay** (stock, cheapest) for the MVP, or DALL·E/Gemini for generated images
  (needs an OpenAI/Google key). Set `IMAGE_PROVIDER` + the matching key in `deploy/.env`.

So the **product** runs on DeepSeek (plus an embeddings + image provider), while the **development
of the product** runs on Claude (plan/eval) + DeepSeek (code). Two separate concerns, both DeepSeek-
centric for cost, with Claude where reasoning quality pays off.

## What I (Cowork) drive vs. what you run

- **I drive**: the Spec Kit artifacts, each slice's change-plan, and the evaluation/review at every
  gate — and I keep `spec.md`/`plan.md`/`tasks.md` in sync as scope shifts.
- **You run**: Aider (Claude+DeepSeek) and `docker compose` on your machine/VPS, because those need
  your API keys and provider network access, which this environment can't hold.

Hand me an Aider diff or a failing test log and I'll review/triage it as the gate step.
