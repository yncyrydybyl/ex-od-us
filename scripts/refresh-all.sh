#!/usr/bin/env bash
#
# refresh-all.sh — Full data refresh pipeline
#
# Runs all enrichment, build, and sync steps in order.
# Safe to re-run. Each step is idempotent.
#
# Usage:
#   ./scripts/refresh-all.sh              # normal run (uses ETag cache)
#   ./scripts/refresh-all.sh --force      # ignore cache, re-fetch everything
#   ./scripts/refresh-all.sh --dry-run    # show what would change
#
set -euo pipefail

FORCE=""
DRY_RUN=""
SKIP_MATRIXROOMS=""

for arg in "$@"; do
  case "$arg" in
    --force) FORCE="--force" ;;
    --dry-run) DRY_RUN="--dry-run" ;;
    --skip-matrixrooms) SKIP_MATRIXROOMS="--skip-matrixrooms" ;;
    --help|-h)
      echo "Usage: $0 [--force] [--dry-run] [--skip-matrixrooms]"
      echo ""
      echo "Steps:"
      echo "  1. Enrich projects (fetch READMEs, score Matrix presence, check liveness)"
      echo "  2. Build projects.json from project markdown files"
      echo "  3. Sync issues (create missing, update labels + body)"
      echo ""
      echo "Options:"
      echo "  --force             Ignore ETag cache, re-fetch all READMEs"
      echo "  --dry-run           Show what would change without writing"
      echo "  --skip-matrixrooms  Skip matrixrooms.info and Matrix room liveness checks (faster)"
      exit 0
      ;;
  esac
done

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
cd "$REPO_ROOT"

echo "╔══════════════════════════════════════════╗"
echo "║       Exodus — Full Data Refresh         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Step 1: Enrich projects ─────────────────────────────────────
echo "┌─ Step 1/3: Enrich projects"
echo "│  Fetching READMEs, scoring Matrix presence, checking liveness..."
echo "│"
python3 scripts/enrich-projects.py $FORCE $DRY_RUN $SKIP_MATRIXROOMS 2>&1 | sed 's/^/│  /'
echo "│"
echo "└─ Done."
echo ""

# ── Step 2: Build projects.json ─────────────────────────────────
echo "┌─ Step 2/3: Build projects.json"
if [[ -z "$DRY_RUN" ]]; then
  bash scripts/build-projects.sh 2>&1 | sed 's/^/│  /'
else
  echo "│  (dry run — skipped)"
fi
echo "│"
echo "└─ Done."
echo ""

# ── Step 3: Sync issues ────────────────────────────────────────
echo "┌─ Step 3/3: Sync issues (create missing, update labels + body)"
if [[ -z "$DRY_RUN" ]]; then
  if command -v gh &>/dev/null; then
    python3 scripts/sync-issues.py 2>&1 | sed 's/^/│  /'
  else
    echo "│  gh CLI not found — skipping issue sync"
  fi
else
  echo "│  (dry run — skipped)"
fi
echo "│"
echo "└─ Done."
echo ""

# ── Summary ─────────────────────────────────────────────────────
PROJECT_COUNT=$(ls projects/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "╔══════════════════════════════════════════╗"
echo "║  Refresh complete: $PROJECT_COUNT projects          ║"
echo "╚══════════════════════════════════════════╝"

if [[ -z "$DRY_RUN" ]]; then
  echo ""
  echo "To commit and push:"
  echo "  git add projects/ data/"
  echo "  git commit -m 'chore: full data refresh'"
  echo "  git push"
fi
