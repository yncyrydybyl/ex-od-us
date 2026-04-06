#!/usr/bin/env bash
#
# refresh-all.sh — Full data refresh pipeline with auto-commit
#
# Runs all enrichment, build, and sync steps in order.
# Captures what changed and writes a detailed commit message.
# Safe to re-run. Each step is idempotent.
#
# Usage:
#   ./scripts/refresh-all.sh              # normal run (uses ETag cache)
#   ./scripts/refresh-all.sh --force      # ignore cache, re-fetch everything
#   ./scripts/refresh-all.sh --dry-run    # show what would change
#   ./scripts/refresh-all.sh --no-commit  # run but don't commit
#
set -euo pipefail

FORCE=""
DRY_RUN=""
SKIP_MATRIXROOMS=""
NO_COMMIT=""

for arg in "$@"; do
  case "$arg" in
    --force) FORCE="--force" ;;
    --dry-run) DRY_RUN="--dry-run" ;;
    --skip-matrixrooms) SKIP_MATRIXROOMS="--skip-matrixrooms" ;;
    --no-commit) NO_COMMIT="1" ;;
    --help|-h)
      echo "Usage: $0 [--force] [--dry-run] [--skip-matrixrooms] [--no-commit]"
      echo ""
      echo "  --force             Ignore ETag cache, re-fetch all READMEs"
      echo "  --dry-run           Show what would change without writing"
      echo "  --skip-matrixrooms  Skip matrixrooms.info checks (faster)"
      echo "  --no-commit         Run pipeline but don't git commit/push"
      exit 0
      ;;
  esac
done

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
cd "$REPO_ROOT"

LOG=$(mktemp)
trap "rm -f $LOG" EXIT

log() { echo "$1" | tee -a "$LOG"; }

log "╔══════════════════════════════════════════╗"
log "║       Exodus — Full Data Refresh         ║"
log "╚══════════════════════════════════════════╝"
log ""

# ── Step 1: Enrich projects ─────────────────────────────────────
log "┌─ Step 1/3: Enrich projects"
ENRICH_OUT=$(mktemp)
python3 scripts/enrich-projects.py $FORCE $DRY_RUN $SKIP_MATRIXROOMS 2>&1 | tee "$ENRICH_OUT" | sed 's/^/│  /'

# Extract stats from enricher output
ENRICH_SUMMARY=$(grep -o 'Processed: [0-9]*.*Errors: [0-9]*' "$ENRICH_OUT" || echo "no stats")
ENRICHED_PROJECTS=$(grep -oP '^\[\S+\] INFO:   (\S+)' "$ENRICH_OUT" | sed 's/.*INFO:   //' | sort -u)
ENRICHED_COUNT=$(echo "$ENRICHED_PROJECTS" | grep -c . || echo 0)
DEAD_PROJECTS=$(grep 'DEAD:' "$ENRICH_OUT" | grep -oP 'INFO:   (\S+)' | sed 's/.*INFO:   //' || true)
rm -f "$ENRICH_OUT"

log "│"
log "└─ $ENRICH_SUMMARY"
log ""

# ── Step 2: Build projects.json ─────────────────────────────────
log "┌─ Step 2/3: Build projects.json"
if [[ -z "$DRY_RUN" ]]; then
  BUILD_OUT=$(bash scripts/build-projects.sh 2>&1)
  echo "$BUILD_OUT" | sed 's/^/│  /'
  PROJECT_COUNT=$(echo "$BUILD_OUT" | grep -oP 'Built \K[0-9]+' || echo "?")
  log "│  $PROJECT_COUNT projects in projects.json"
else
  log "│  (dry run — skipped)"
  PROJECT_COUNT="?"
fi
log "└─ Done."
log ""

# ── Step 3: Sync issues ────────────────────────────────────────
SYNC_SUMMARY="skipped"
log "┌─ Step 3/3: Sync issues"
if [[ -z "$DRY_RUN" ]] && command -v gh &>/dev/null; then
  SYNC_OUT=$(mktemp)
  python3 scripts/sync-issues.py 2>&1 | tee "$SYNC_OUT" | sed 's/^/│  /'
  CREATED=$(grep -c 'CREATED' "$SYNC_OUT" || echo 0)
  UPDATED=$(grep -c 'UPDATE' "$SYNC_OUT" || echo 0)
  SYNC_SUMMARY="created: $CREATED, updated: $UPDATED"
  rm -f "$SYNC_OUT"
else
  log "│  (dry run or gh not available — skipped)"
fi
log "└─ Done."
log ""

# ── Summary ─────────────────────────────────────────────────────
log "╔══════════════════════════════════════════╗"
log "║  Refresh complete                        ║"
log "╠══════════════════════════════════════════╣"
log "║  Projects: $PROJECT_COUNT total"
log "║  Enriched: $ENRICHED_COUNT repos scanned"
log "║  Issues:   $SYNC_SUMMARY"
if [[ -n "$DEAD_PROJECTS" ]]; then
  log "║  Dead:     $(echo "$DEAD_PROJECTS" | wc -l | tr -d ' ') projects"
fi
log "╚══════════════════════════════════════════╝"

# ── Auto-commit ─────────────────────────────────────────────────
if [[ -n "$DRY_RUN" || -n "$NO_COMMIT" ]]; then
  exit 0
fi

git add projects/ data/
if git diff --staged --quiet; then
  log ""
  log "No changes to commit."
  exit 0
fi

# Build detailed commit message from what happened
CHANGED_FILES=$(git diff --staged --stat | tail -1)
CHANGED_PROJECTS=$(git diff --staged --name-only -- projects/ | sed 's|projects/||;s|\.md||' | sort)
CHANGED_PROJECT_COUNT=$(echo "$CHANGED_PROJECTS" | grep -c . || echo 0)

COMMIT_MSG="chore: data refresh — $CHANGED_PROJECT_COUNT projects updated

Pipeline: enrich → build → sync
$ENRICH_SUMMARY
Issues: $SYNC_SUMMARY
$CHANGED_FILES"

if [[ -n "$DEAD_PROJECTS" ]]; then
  COMMIT_MSG="$COMMIT_MSG

Dead projects detected:
$(echo "$DEAD_PROJECTS" | sed 's/^/  - /')"
fi

if [[ "$CHANGED_PROJECT_COUNT" -le 20 ]]; then
  COMMIT_MSG="$COMMIT_MSG

Updated projects:
$(echo "$CHANGED_PROJECTS" | sed 's/^/  - /')"
fi

git commit -m "$COMMIT_MSG"
log ""
log "Committed. Run 'git push' to deploy."
