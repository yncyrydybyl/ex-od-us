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
