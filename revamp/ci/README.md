# CI workflow — parked, not active

`ci.yml` is the pipeline described in the Phase 2 report (T-2.7). It is **not** at
`.github/workflows/` yet, so GitHub is not running it.

## Why it is here

Pushing a file under `.github/workflows/` requires the pushing token to carry the
`workflow` OAuth scope. The token on the machine that produced this branch does not
have it, and the push was rejected:

```
! [remote rejected] refusing to allow a Personal Access Token to create or update
  workflow `.github/workflows/ci.yml` without `workflow` scope
```

Parking the file keeps it in version control rather than dropping work to satisfy a
credential limitation.

## Activating it

Once a token with `workflow` scope is configured (GitHub → Settings → Developer
settings → Personal access tokens → enable **workflow**):

```bash
mkdir -p .github/workflows && git mv revamp/ci/ci.yml .github/workflows/ci.yml
git rm revamp/ci/README.md
git commit -m "ci: activate the pipeline parked in revamp/ci"
git push
```

## What it runs

| Job | Purpose |
|---|---|
| `backend` | `ruff` + pytest with `--cov-fail-under=87` |
| `migrations` | `upgrade → downgrade → upgrade` against **real Postgres 16** (closes TD-20) |
| `frontend` | typecheck, lint, and the Vitest coverage thresholds |
| `build` | image build from a clean checkout, `presenton` excluded (TD-01) |

The E2E smoke suite is deliberately absent: it needs a live stack including Presenton.
