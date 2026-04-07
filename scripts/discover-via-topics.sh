#!/usr/bin/env bash
#
# discover-via-topics.sh — Find repos via GitHub topics (not code search)
#
# Sourcegraph misses repos that aren't in its index. This uses GitHub's
# official repo search API (gh search repos) which covers everything.
#
# Topic search has a separate rate limit from code search and works
# without hitting the same limits.
#
# Usage: ./scripts/discover-via-topics.sh [--limit N]
#
set -euo pipefail

LIMIT=200
[[ "${1:-}" == "--limit" ]] && LIMIT="$2"

OUT="data/discovered-via-topics.txt"
mkdir -p data

TOPICS=(
  matrix
  matrix-org
  matrix-protocol
  element-web
  matrix-client
  matrix-bot
  matrix-bridge
  matrix-server
  synapse
  dendrite
  mautrix
)

> "$OUT"
echo "Discovering via GitHub topic search..." >&2

for topic in "${TOPICS[@]}"; do
  echo "  topic:$topic" >&2
  gh search repos --topic "$topic" --sort stars --limit "$LIMIT" \
    --json fullName \
    --jq '.[] | .fullName' >> "$OUT" 2>/dev/null || true
  sleep 1
done

# Deduplicate
sort -u -o "$OUT" "$OUT"

# Strip excluded repos in-place — keeps the outfile honest so any
# downstream tool that reads it gets a clean list. Match is on the
# normalized `github.com/owner/repo` form (case-insensitive).
EXCL_FILE="data/excluded-repos.txt"
if [[ -f "$EXCL_FILE" ]]; then
  python3 - "$OUT" "$EXCL_FILE" <<'PYEOF'
import sys, os
sys.path.insert(0, 'scripts')
from exclusions import load_excluded_repos, is_excluded
out_path, excl_path = sys.argv[1], sys.argv[2]
excluded = load_excluded_repos(excl_path)
if not excluded:
    sys.exit(0)
with open(out_path) as f:
    lines = [l.rstrip() for l in f if l.strip()]
kept = [l for l in lines if not is_excluded(l, excluded)]
removed = len(lines) - len(kept)
if removed:
    with open(out_path, 'w') as f:
        f.write('\n'.join(kept) + '\n')
    print(f"Filtered {removed} excluded repos from {out_path}", file=sys.stderr)
PYEOF
fi

COUNT=$(wc -l < "$OUT")
echo "Found $COUNT unique repos via topics → $OUT" >&2

# Show how many are NEW
NEW=0
EXISTING=0
while IFS= read -r slug; do
  [[ -z "$slug" ]] && continue
  if grep -q "$slug" data/discovered-slugs.txt 2>/dev/null; then
    EXISTING=$((EXISTING + 1))
  else
    NEW=$((NEW + 1))
  fi
done < "$OUT"
echo "  New: $NEW, Already known: $EXISTING" >&2
