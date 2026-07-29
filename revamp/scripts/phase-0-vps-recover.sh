#!/usr/bin/env bash
#
# Phase 0 recovery — run this ON THE VPS.
#
# Executes the parts of PHASE-0-PROMPT.md that require access to the running
# stack: T-0.3 (backups), T-0.2 (capture hand-mutated config), T-0.1 (vendor
# the Presenton source into version control).
#
# SAFETY
#   - Read-and-copy only. Nothing is deleted, no container is stopped or
#     restarted, no service is interrupted.
#   - Backups run FIRST, before anything else touches the host.
#   - Nothing is committed. The script stages files and stops; review the diff
#     and commit yourself.
#   - Secrets are redacted from the captured config before it lands in the repo.
#
# USAGE
#   cd /var/www/notebookfinal          # wherever the repo lives on the VPS
#   bash revamp/scripts/phase-0-vps-recover.sh
#
# Re-runnable. Existing backups are kept (timestamped); the vendored source is
# refreshed in place.

set -euo pipefail

# ---------------------------------------------------------------- config ----

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR_DIR="$REPO_ROOT/presenton"

# The compose build context is `../presenton-custom` RELATIVE TO deploy/, where the
# compose file lives — so it resolves to $REPO_ROOT/presenton-custom, not to the repo's
# parent. An earlier version of this script resolved it from $REPO_ROOT and reported the
# source missing while it sat untracked inside the repo. Probe both, repo-root first.
find_source() {
  local candidate
  for candidate in "$REPO_ROOT/presenton-custom" "$REPO_ROOT/../presenton-custom"; do
    if [[ -d "$candidate" ]]; then
      (cd "$candidate" && pwd)
      return 0
    fi
  done
  return 1
}
SOURCE_DIR="${PRESENTON_SRC:-$(find_source || true)}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/noteai-backups}"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.lite.yml"
ENV_FILE="$REPO_ROOT/deploy/.env.lite"
STAMP="$(date +%Y-%m-%dT%H%M%S)"

COMPOSE=(docker compose -f "$COMPOSE_FILE")
[[ -f "$ENV_FILE" ]] && COMPOSE+=(--env-file "$ENV_FILE")

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[0;32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[0;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------ preflight ----

step "Preflight"

command -v docker >/dev/null || die "docker not found"
docker info >/dev/null 2>&1 || die "docker daemon unreachable — are you root / in the docker group?"
[[ -d "$REPO_ROOT/.git" ]] || die "not a git repo: $REPO_ROOT"
ok "repo: $REPO_ROOT"

if [[ -z "$SOURCE_DIR" || ! -d "$SOURCE_DIR" ]]; then
  die "Presenton source not found. Looked in:
    $REPO_ROOT/presenton-custom
    $REPO_ROOT/../presenton-custom
  (override with PRESENTON_SRC=/path/to/source)

This is the component Phase 0 exists to rescue. Before going further:
  1. Check the build context actually used:
       grep -A3 'presenton:' $COMPOSE_FILE | grep context
  2. Search the host:
       find / -maxdepth 6 -type d -name 'presenton*' 2>/dev/null
  3. If it is genuinely gone, the running container image is the last copy.
     Export it NOW before anything else:
       docker commit \$(docker ps -qf name=presenton) presenton-rescue:$STAMP
       docker save presenton-rescue:$STAMP | gzip > $BACKUP_DIR/presenton-image-$STAMP.tar.gz
     Then STOP and escalate. Do not reconstruct from upstream and hope the
     deltas do not matter — the hand-mutations are the undocumented part."
fi
ok "presenton source: $SOURCE_DIR"

mkdir -p "$BACKUP_DIR"
ok "backups: $BACKUP_DIR"

# ------------------------------------------- T-0.3 — back up FIRST ---------
# Runs before anything else. If this host is lost mid-task, the data survives.

step "T-0.3 — Backing up live runtime data"

PG_USER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo orch)"
PG_DB="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo orchestrator)"

if "${COMPOSE[@]}" ps postgres --status running -q 2>/dev/null | grep -q .; then
  "${COMPOSE[@]}" exec -T postgres pg_dump -U "$PG_USER" "$PG_DB" \
    | gzip > "$BACKUP_DIR/orchestrator-$STAMP.sql.gz"
  ok "postgres  → orchestrator-$STAMP.sql.gz ($(du -h "$BACKUP_DIR/orchestrator-$STAMP.sql.gz" | cut -f1))"
else
  warn "postgres not running — SKIPPED. Re-run this script once it is up."
fi

for vol in presenton_data minio_data notebook_data; do
  full="notebookllm-lite_$vol"
  if docker volume inspect "$full" >/dev/null 2>&1; then
    docker run --rm -v "$full":/data -v "$BACKUP_DIR":/backup alpine \
      tar czf "/backup/$vol-$STAMP.tar.gz" -C /data . 2>/dev/null
    ok "$vol → $vol-$STAMP.tar.gz ($(du -h "$BACKUP_DIR/$vol-$STAMP.tar.gz" | cut -f1))"
  else
    warn "volume $full not found — skipped"
  fi
done

step "Backup checksums (record these in the Phase 0 report)"
( cd "$BACKUP_DIR" && sha256sum ./*"$STAMP"* 2>/dev/null | tee "checksums-$STAMP.txt" ) || warn "no backups produced"

cat <<EOF

    ⚠  These archives contain TENANT DATA and live credentials.
       Copy them OFF this host now, and do NOT commit them:
         scp '$BACKUP_DIR'/*$STAMP* you@your-machine:~/noteai-backups/
EOF

# --------------------------------- T-0.2 — capture mutated config ----------

step "T-0.2 — Capturing hand-mutated Presenton config"

mkdir -p "$VENDOR_DIR/config"
RAW="$BACKUP_DIR/userConfig-raw-$STAMP.json"

if "${COMPOSE[@]}" exec -T presenton cat /app_data/userConfig.json > "$RAW" 2>/dev/null && [[ -s "$RAW" ]]; then
  ok "captured raw config → $RAW (kept OUT of the repo — contains keys)"

  # Redact any value that looks like a credential. Key-name based, so it stays
  # correct even if the value format changes.
  if command -v jq >/dev/null 2>&1; then
    jq 'walk(
          if type == "object" then
            with_entries(
              if (.key | ascii_downcase | test("key|secret|token|password|credential"))
              then .value = "${REDACTED_SET_VIA_ENV}"
              else . end
            )
          else . end
        )' "$RAW" > "$VENDOR_DIR/config/userConfig.example.json" 2>/dev/null \
      && ok "redacted → presenton/config/userConfig.example.json" \
      || warn "jq redaction failed — redact $RAW BY HAND before committing"
  else
    warn "jq not installed — redact $RAW BY HAND into presenton/config/userConfig.example.json"
    warn "  apt-get install -y jq"
  fi
else
  warn "could not read /app_data/userConfig.json (container down, or file absent)"
  warn "  If the container is up and this failed, the config may live elsewhere:"
  warn "    ${COMPOSE[*]} exec presenton ls -la /app_data/"
fi

# ------------------------------------- T-0.1 — vendor the source -----------

step "T-0.1 — Vendoring Presenton source into the repo"

step "  Provenance"
{
  echo "captured:      $STAMP"
  echo "source path:   $SOURCE_DIR"
  echo -n "git history:   "
  if git -C "$SOURCE_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$SOURCE_DIR" log --oneline -5 2>/dev/null | head -5
    echo -n "upstream:      "
    git -C "$SOURCE_DIR" remote -v 2>/dev/null | head -2 || echo "(none)"
  else
    echo "NONE — unversioned fork, provenance unrecoverable"
  fi
  echo -n "package:       "
  grep -hE '"(name|version)"' "$SOURCE_DIR/package.json" 2>/dev/null | tr -d ' ' | tr '\n' ' ' || echo "(no package.json at root)"
  echo
} | tee "$VENDOR_DIR/PROVENANCE.txt"
ok "→ presenton/PROVENANCE.txt (paste this into the Phase 0 report)"

step "  Copying source (excluding build output, deps, runtime state, secrets)"
if command -v rsync >/dev/null 2>&1; then
  # `.next-build` matters: Presenton sets `distDir: ".next-build"` in
  # next.config.mjs, so the stock `.next/` exclude misses the compiled output
  # entirely. Without it the vendored tree carries ~168MB of build artifacts.
  # `readme_assets` and `electron` are not used by the Docker build either.
  rsync -a --delete \
    --exclude='.git/' --exclude='node_modules/' \
    --exclude='.next/' --exclude='.next-build/' --exclude='dist/' --exclude='build/' \
    --exclude='app_data/' --exclude='__pycache__/' --exclude='.venv/' \
    --exclude='*.db' --exclude='.env' --exclude='.env.*' \
    --exclude='readme_assets/' --exclude='electron/' \
    "$SOURCE_DIR"/ "$VENDOR_DIR"/source/
  ok "rsync → presenton/source/ ($(du -sh "$VENDOR_DIR/source" 2>/dev/null | cut -f1))"

  # A vendored tree in the hundreds of MB means an exclude was missed. Say so
  # rather than letting it reach a commit, where removing it needs history surgery.
  SRC_KB="$(du -sk "$VENDOR_DIR/source" 2>/dev/null | cut -f1)"
  if [[ -n "$SRC_KB" && "$SRC_KB" -gt 102400 ]]; then
    warn "vendored tree is $((SRC_KB / 1024))MB — larger than expected for source only."
    warn "  Inspect before committing:  du -sh $VENDOR_DIR/source/* | sort -rh | head"
  fi
else
  die "rsync not found: apt-get install -y rsync"
fi

step "  Secret scan on the vendored tree (BLOCKING)"
HITS="$(grep -rIlnE '(sk-or-[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16})' \
        "$VENDOR_DIR" 2>/dev/null | grep -v 'userConfig.example.json' || true)"
if [[ -n "$HITS" ]]; then
  die "SECRETS FOUND in the vendored tree — do NOT commit:

$HITS

Remove or redact each, then re-run. Note: 'git rm' after a commit does not
remove a secret from history — if it is ever pushed, rotate the key."
fi
ok "no secrets detected"

# ------------------------------------------------------------- report ------

step "Done — nothing committed. Review, then commit yourself."

cat <<EOF

  Next steps (T-0.1 completion):

  1. Point compose at the vendored source. In $COMPOSE_FILE,
     under the 'presenton' service:

         build:
    -      context: ../presenton-custom
    +      context: ../presenton/source

  2. Review what landed:
         git -C "$REPO_ROOT" status --short
         git -C "$REPO_ROOT" diff --stat

  3. Commit (see revamp/README.md rule 6):
         git add presenton/ deploy/docker-compose.lite.yml
         git commit -m "feat(presenton): vendor slide engine into version control (T-0.1, T-0.2)"

  4. T-0.5 — prove reproducibility from a CLEAN CLONE:
         cd \$(mktemp -d) && git clone <repo-url> noteai && cd noteai
         cp deploy/.env.lite.example deploy/.env.lite   # fill in credentials
         docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite build
         docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite up -d
         docker compose -f deploy/docker-compose.lite.yml ps

     Capture the FULL transcript — it is the evidence for gates G2 and G3.

  Expect /editor to still 404 and downloads to still fail. That is correct.
  Phase 0 fixes reproducibility, not behaviour. Do not fix them here.

EOF
