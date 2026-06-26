# Running Spec Kit in this project (from Claude Cowork)

This folder is a ready-to-use **Spec Kit** project configured for Claude. You drive the
Spec-Driven Development (SDD) workflow by asking Claude in plain language — Claude reads the
matching command file in `.claude/skills/speckit-*/SKILL.md` and runs it, writing all output
into this folder.

## What's in here

- `.specify/templates/` — spec / plan / tasks / checklist / constitution templates
- `.specify/scripts/bash/` — helper scripts the workflow calls
- `.specify/memory/constitution.md` — project principles (created in step 1)
- `.claude/skills/speckit-*/` — the workflow command instructions
- `specs/<NNN-feature>/` — your generated `spec.md`, `plan.md`, `tasks.md`
- `CLAUDE.md` — project context Claude reads automatically

## The workflow (run in order)

In Cowork, just say the request. The phrase in parentheses is the underlying command.

1. **Set principles** (`/speckit.constitution`)
   "Set up the project constitution: prioritise local-first, privacy, and tested code."
   → writes `.specify/memory/constitution.md`

2. **Specify the feature** (`/speckit.specify`)
   "Create a spec: a custom NotebookLLM that ingests local documents and lets me chat over them."
   → creates `specs/001-.../spec.md` (the *what* and *why* — no tech choices)

3. **(Optional) Clarify** (`/speckit.clarify`)
   "Clarify any underspecified parts of the spec." → resolves ambiguities before planning.

4. **Plan** (`/speckit.plan`)
   "Build the plan. Use Python, FastAPI, and a local vector DB (Chroma)."
   → creates `plan.md` plus design docs (the *how* — your stack goes here)

5. **Break into tasks** (`/speckit.tasks`)
   "Generate the task list." → creates `tasks.md`

6. **(Optional) Analyze / Checklist** (`/speckit.analyze`, `/speckit.checklist`)
   Cross-check spec ↔ plan ↔ tasks for gaps before building.

7. **Implement** (`/speckit.implement`)
   "Implement the tasks." → Claude builds the code per `tasks.md`, into this folder.

## Tips

- Each feature gets its own numbered folder under `specs/`. Start a new feature any time with
  "specify a new feature: …".
- Keep the spec free of implementation detail; put tech choices in the plan step.
- You can edit any generated `.md` by hand, then ask Claude to continue from there.
- The full command set: constitution, specify, clarify, plan, tasks, analyze, checklist,
  implement, converge, taskstoissues.

## Note on this setup

This project was scaffolded directly from the cloned Spec Kit source (no `specify` CLI run),
so the layout matches `specify init --ai claude --script sh`. If you later want to use the CLI
to update it, run from a terminal on your Mac:

```
cd "Project/NotebookLLM-custom"
uvx --from git+https://github.com/github/spec-kit.git specify init --here --ai claude
```
