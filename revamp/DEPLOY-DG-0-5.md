# Deploying DG-0..DG-5 to the VPS

Companion to [`PLAN-DECK-GENERATION-REVAMP.md`](./PLAN-DECK-GENERATION-REVAMP.md) and
[`reports/DG-0-5-REPORT.md`](./reports/DG-0-5-REPORT.md). Pushed to `origin/revamp/phase-1`
as four commits: `9a8cc07` (deploy), `736e288` (backend), `7786cd4` (frontend), `7bce57d`
(docs).

Run every command below **on the VPS**, in order. Nothing here has been executed against
the live stack — everything is verified locally (260 backend tests, 96 frontend tests,
`docker compose config` resolution) but not against a running Presenton/Traefik.

---

## 0. Before you touch anything: back up

Four new Alembic migrations run automatically on deploy (`0009`–`0012`, all additive —
new nullable columns, one narrowed enum). Low risk, but this is exactly the moment prior
sessions on this VPS have taken a Postgres snapshot first, per `TECH-DEBT.md` TD-03/TD-25.

```bash
cd /var/www/notebookfinal
# $POSTGRES_USER/$POSTGRES_DB must resolve INSIDE the container (that's where
# compose injected them from .env.lite) -- sh -c '...' with single quotes, not
# the host shell, does that expansion.
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > ~/noteai-backups/pg-$(date +%Y%m%dT%H%M%S).sql.gz
ls -la ~/noteai-backups/
```

(Reuses the `~/noteai-backups/` directory already on this host from the Phase 0 recovery
script.)

---

## 1. Pull the code

You're already on `revamp/phase-1` (confirmed 2026-08-05), so this is a plain pull, not
the branch-checkout dance TD-01's recovery note describes for `main`.

```bash
cd /var/www/notebookfinal
git status                      # confirm nothing uncommitted is sitting here
git fetch origin
git log --oneline -5 origin/revamp/phase-1   # sanity check before merging it in
git pull origin revamp/phase-1
git log --oneline -5            # should show 7bce57d at HEAD
```

If `git status` shows anything dirty, stop and figure out what it is before pulling —
don't discard it blind.

---

## 2. Add the one new required variable — **mandatory, not optional**

DG-0's entire point is a Traefik header carrying your Presenton Basic Auth credentials.
Without this variable, `docker compose` silently substitutes an **empty string**, Traefik
sends `Authorization: Basic ` (empty), and `/editor` keeps 401ing — the exact problem this
deploy is meant to fix, just with a more confusing symptom.

```bash
cd /var/www/notebookfinal
grep -E '^PRESENTON_AUTH_(USERNAME|PASSWORD)=' deploy/.env.lite
```

Take those two values and compute the base64 pair **from your real credentials**, not the
example ones:

```bash
echo -n "$(grep '^PRESENTON_AUTH_USERNAME=' deploy/.env.lite | cut -d= -f2):$(grep '^PRESENTON_AUTH_PASSWORD=' deploy/.env.lite | cut -d= -f2)" | base64
```

Append the result to `deploy/.env.lite` (edit the file directly — it's not committed and
this repo's convention keeps secrets out of git):

```bash
echo "PRESENTON_BASIC_AUTH_B64=<paste the output above>" >> deploy/.env.lite
grep PRESENTON_BASIC_AUTH_B64 deploy/.env.lite   # confirm it landed
```

---

## 3. Rebuild only what changed

`orchestrator`, `worker`, `init`, and `frontend` have new source (the `init` container is
what actually runs the migrations, via `alembic upgrade head`). `presenton`'s own source is
untouched this round — only its Traefik **labels** changed, and `docker compose up -d`
recreates a container on a label diff without needing a rebuild. Scoping the build avoids
an unnecessary Presenton image rebuild:

```bash
cd /var/www/notebookfinal
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite \
  build orchestrator worker init frontend
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite \
  up -d
```

The second command recreates **every** service whose resolved config changed — including
`presenton` (new labels) and `traefik` (nothing changed there, but it's harmless either
way) — without rebuilding their images.

---

## 4. Verify the migrations actually ran

```bash
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite logs init --tail 50
```

Look for `alembic upgrade head` completing with no errors, and confirm the DB agrees:

```bash
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version;"'
```

Expect `0012_generation_studio_opened`.

---

## 5. Verify DG-0 — the one thing that couldn't be checked before this deploy

```bash
curl -sD - -o /dev/null https://notellm.umarsyukri.com/editor
```

**Expected: `200`, not `401`.** If it's still `401`:
- Re-check step 2 — is `PRESENTON_BASIC_AUTH_B64` actually in the `.env.lite` that compose
  is reading, and did the `presenton` container actually recreate (`docker compose ps
  presenton` — check the `CREATED` timestamp is recent)?
- `docker compose ... config | grep -A2 presenton-auth` — confirm the header value isn't
  blank.

If it's still `404`: routing itself regressed — unrelated to this deploy, worth its own
investigation (was `TD-05`, previously confirmed fixed on this VPS on 2026-08-05).

---

## 6. Smoke-test the new flow

No UI click-through has been done against a live stack yet — this is the first time. In
the app: open a project with at least one `ready` source, use the `/generate` command or
the ＋ button in chat. You should see:

1. A setup card (template picker if you have any registered templates, an "Advanced"
   disclosure for tone/density/language/model/export/web-search) — **not** the old form.
2. "Buat kerangka" / "Build outline" → a review card listing sections, editable inline,
   with a "Regenerate" option.
3. "Hasilkan dek" / "Generate deck" → a real `Generation`, same as before.
4. In Studio's deck list, click "🎨 Editor" on a ready deck, then check that its PPTX/PDF
   download buttons disappear (no reload needed) and that a direct download attempt now
   returns a 422 with `code: "edited_in_studio"`.

If step 1 doesn't render as described, check the browser console and
`docker compose logs frontend` — this is the one path this session's tests couldn't
exercise end-to-end (no browser, no live engine).

---

## 7. If something's wrong: rollback

Every migration in this batch is additive (new nullable columns, one narrowed enum with no
existing rows in the removed states) — there is no destructive step on `upgrade`. To roll
back the code without touching data:

```bash
cd /var/www/notebookfinal
git log --oneline -6                      # find the commit before 9a8cc07
git checkout <previous-sha>
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite \
  build orchestrator worker init frontend
docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d
```

This leaves the four new migrations applied (harmless — the old code just doesn't know
about the new columns) rather than running `alembic downgrade`, which is the destructive
direction (0010's downgrade deletes any freeform outline rows created since upgrade).
Only downgrade the schema if you're certain no freeform outlines/generations have been
created yet.

If only DG-0 is the problem (auth still broken, everything else fine), you don't need a
full rollback — just remove the `presenton-auth` middleware lines from
`deploy/docker-compose.lite.yml` locally, or leave `PRESENTON_BASIC_AUTH_B64` unset and
accept `/editor` staying 401'd until it's revisited; nothing else in this deploy depends on
it working.

---

## 8. What this deploy does *not* touch

- Presenton's own source (`presenton-custom/`) — unchanged, still the same
  `noteai/deployed` branch confirmed on 2026-08-05.
- `brand_tokens` reaching the renderer (`TD-07`) — still open, unrelated.
- The governed profile/outline path (`OutlinePanel.tsx`, `OutlineService.build`) — untouched
  on purpose; §5.4 (governed vs. freeform) stays parked.
- Off-host backups (`TD-03`) — still only on this host. Worth doing while you're already in
  here for step 0.
