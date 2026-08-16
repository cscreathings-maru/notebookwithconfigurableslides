#!/usr/bin/env bash
#
# RM-0 baseline — run this ON THE VPS.
#
# Executes PLAN-MONOLITH-RENDERER.md's RM-0: back up presenton_data + Postgres
# off-host before anything is deleted, and capture the current failure mode as
# observed fact before touching any code.
#
# SAFETY
#   - Read-and-copy only. Nothing is deleted, no container is stopped or
#     restarted, no service is interrupted.
#   - Backups run FIRST.
#   - Nothing is committed. Review what lands in revamp/reports/ and commit
#     yourself.
#
# USAGE
#   cd /var/www/notebookfinal
#   bash revamp/scripts/rm-0-baseline.sh
#
# Re-runnable. Existing backups are kept (timestamped).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/noteai-backups}"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.lite.yml"
ENV_FILE="$REPO_ROOT/deploy/.env.lite"
STAMP="$(date +%Y-%m-%dT%H%M%S)"
REPORT="$REPO_ROOT/revamp/reports/RM-0-BASELINE.md"

COMPOSE=(docker compose -f "$COMPOSE_FILE")
[[ -f "$ENV_FILE" ]] && COMPOSE+=(--env-file "$ENV_FILE")

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[0;32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[0;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

step "Preflight"
command -v docker >/dev/null || die "docker not found"
docker info >/dev/null 2>&1 || die "docker daemon unreachable"
[[ -d "$REPO_ROOT/.git" ]] || die "not a git repo: $REPO_ROOT"
mkdir -p "$BACKUP_DIR" "$REPO_ROOT/revamp/reports"
ok "repo: $REPO_ROOT"
ok "backups: $BACKUP_DIR"

# ---------------------------------------------------- backups run FIRST ----

step "Backing up live runtime data (before anything is deleted)"

PG_USER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo orch)"
PG_DB="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo orchestrator)"

if "${COMPOSE[@]}" ps postgres --status running -q 2>/dev/null | grep -q .; then
  "${COMPOSE[@]}" exec -T postgres pg_dump -U "$PG_USER" "$PG_DB" \
    | gzip > "$BACKUP_DIR/orchestrator-$STAMP.sql.gz"
  ok "postgres → orchestrator-$STAMP.sql.gz ($(du -h "$BACKUP_DIR/orchestrator-$STAMP.sql.gz" | cut -f1))"
else
  warn "postgres not running — SKIPPED. Re-run once it's up."
fi

for vol in presenton_data minio_data; do
  full="notebookllm-lite_$vol"
  if docker volume inspect "$full" >/dev/null 2>&1; then
    docker run --rm -v "$full":/data -v "$BACKUP_DIR":/backup alpine \
      tar czf "/backup/$vol-$STAMP.tar.gz" -C /data . 2>/dev/null
    ok "$vol → $vol-$STAMP.tar.gz ($(du -h "$BACKUP_DIR/$vol-$STAMP.tar.gz" | cut -f1))"
  else
    warn "volume $full not found — skipped"
  fi
done

step "Backup checksums (record these in the report below)"
( cd "$BACKUP_DIR" && sha256sum ./*"$STAMP"* 2>/dev/null | tee "checksums-$STAMP.txt" ) || warn "no backups produced"

cat <<EOF

    ⚠  These archives contain TENANT DATA and live credentials.
       Copy them OFF this host now, and do NOT commit them:
         scp '$BACKUP_DIR'/*$STAMP* you@your-machine:~/noteai-backups/
EOF

# ------------------------------------------------------------- baseline ----

step "Current template registration state"
TEMPLATE_DUMP="$BACKUP_DIR/templates-$STAMP.txt"
if "${COMPOSE[@]}" exec -T postgres sh -c \
  "psql -U \"$PG_USER\" -d \"$PG_DB\" -c \"SELECT name, version, status, registration_status, left(coalesce(registration_error,''),160) AS err FROM template ORDER BY created_at;\"" \
  > "$TEMPLATE_DUMP" 2>&1; then
  ok "template rows → $TEMPLATE_DUMP"
  cat "$TEMPLATE_DUMP"
else
  warn "template dump failed — see $TEMPLATE_DUMP"
fi

step "Orchestrator + worker logs (last 300 lines each)"
LOG_DUMP="$BACKUP_DIR/app-logs-$STAMP.txt"
"${COMPOSE[@]}" logs --tail 300 orchestrator worker > "$LOG_DUMP" 2>&1 || true
if [[ -s "$LOG_DUMP" ]]; then
  ok "logs → $LOG_DUMP ($(wc -l < "$LOG_DUMP") lines)"
else
  warn "log dump is empty — orchestrator/worker may not be running under this compose project. Cross-check with: docker ps -a"
fi

step "Which branch is actually deployed"
BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
ok "branch=$BRANCH commit=$COMMIT"

# ------------------------------------------------------------- report ------

step "Writing revamp/reports/RM-0-BASELINE.md"
{
  echo "# RM-0 Baseline"
  echo
  echo "Captured $STAMP on branch \`$BRANCH\` @ \`$COMMIT\`."
  echo
  echo "## Backups"
  echo
  echo '```'
  cat "$BACKUP_DIR/checksums-$STAMP.txt" 2>/dev/null || echo "(no backups produced — see script output above)"
  echo '```'
  echo
  echo "**Not yet copied off-host.** Run the \`scp\` printed above before RM-13 deletes anything."
  echo
  echo "## Template registration state"
  echo
  echo '```'
  cat "$TEMPLATE_DUMP" 2>/dev/null
  echo '```'
  echo
  echo "## Orchestrator + worker logs (last 300 lines)"
  echo
  echo '```'
  tail -n 300 "$LOG_DUMP" 2>/dev/null
  echo '```'
  echo
  echo "## RM-1 spike — template layout inventory"
  echo
  echo "Run separately (needs the orchestrator container up):"
  echo
  echo '```bash'
  echo "${COMPOSE[*]} exec -T orchestrator python -m scripts.rm1_inspect_templates"
  echo '```'
  echo
  echo "Paste the output and the branch decision (\`ASSESSMENT-ARCHITECTURE\` §5.4 / \`PLAN\` RM-1) here."
} > "$REPORT"
ok "report → $REPORT"

cat <<EOF

$(printf '\033[1;32m')Done.$(printf '\033[0m') Next:
  1. Copy backups off-host (command above) — do this before RM-13.
  2. Run the RM-1 spike:
       ${COMPOSE[*]} exec -T orchestrator python -m scripts.rm1_inspect_templates
  3. Review and commit $REPORT yourself — nothing here was committed for you.
EOF
