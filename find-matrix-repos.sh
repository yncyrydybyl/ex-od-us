#!/usr/bin/env bash
#
# find-matrix-repos.sh — Find GitHub repos with Matrix presence
#
# Discovery via Sourcegraph (bulk, no GitHub rate limits).
# Enrichment via GitHub API (per-repo, authenticated, ETag-cached).
#
# Requires: curl, jq, gh (for authenticated enrichment)
# Output:   JSON array sorted by popularity
#
# Usage: ./find-matrix-repos.sh [OPTIONS]
#
set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────
LIMIT=100
OUTPUT=""
SORT="stars"
MIN_STARS=0
FORMAT="json"
SGRAPH="https://sourcegraph.com/.api/graphql"
SG_LIMIT=2000

usage() {
  cat <<'EOF'
Usage: find-matrix-repos.sh [OPTIONS]

Find GitHub repos with Matrix presence in their READMEs.
Uses Sourcegraph for discovery (no GitHub rate limits).
Uses GitHub API only for per-repo enrichment.

Sorting & filtering:
  --sort KEY         Sort by: stars (default), forks, activity, updated, name
  --min-stars N      Minimum star count (default: 0)
  --sg-limit N       Max Sourcegraph results to fetch (default: 2000)

Output:
  --limit N          Max results to return after filtering (default: 100)
  --output FILE      Write to FILE (default: stdout)
  --format FMT       Output format: json (default), csv, table

General:
  -h, --help         Show this help

Examples:
  ./find-matrix-repos.sh --limit 200 --sort stars --format table
  ./find-matrix-repos.sh --min-stars 50 --limit 50 --output data/found.json
  ./find-matrix-repos.sh --sg-limit 3000 --limit 500  # cast a wider net
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sort)       SORT="$2"; shift 2 ;;
    --min-stars)  MIN_STARS="$2"; shift 2 ;;
    --sg-limit)   SG_LIMIT="$2"; shift 2 ;;
    --limit)      LIMIT="$2"; shift 2 ;;
    --output)     OUTPUT="$2"; shift 2 ;;
    --format)     FORMAT="$2"; shift 2 ;;
    -h|--help)    usage ;;
    *)            echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

for cmd in curl jq; do
  command -v "$cmd" &>/dev/null || { echo "Error: $cmd required." >&2; exit 1; }
done

# ── Phase 1: Sourcegraph discovery (bulk, no GitHub API calls) ──
echo "Phase 1: Discovering repos via Sourcegraph..." >&2

search_sourcegraph() {
  local query="$1"
  local count="$2"
  echo "  Query: $query (limit: $count)" >&2

  local gql
  gql=$(jq -n --arg q "query { search(query: \"$query count:$count\", version: V3, patternType: literal) { results { matchCount results { ... on FileMatch { repository { name } } } } } }" '{query: $q}')

  local result
  result=$(curl -sf "$SGRAPH" -H 'Content-Type: application/json' -d "$gql" 2>/dev/null) || {
    echo "  Sourcegraph request failed" >&2
    echo "[]"
    return
  }

  local match_count
  match_count=$(echo "$result" | jq '.data.search.results.matchCount // 0')
  echo "  → $match_count matches" >&2

  # Extract unique GitHub repo slugs
  echo "$result" | jq -r '
    [.data.search.results.results[]? | .repository.name]
    | map(select(startswith("github.com/")))
    | map(ltrimstr("github.com/"))
    | unique | .[]
  ' 2>/dev/null || echo ""
}

ALL_SLUGS=""

# Multiple search patterns for broader coverage
QUERIES=(
  "matrix.to file:README"
  "img.shields.io/matrix file:README"
  "element.io file:README"
)

for q in "${QUERIES[@]}"; do
  RESULTS=$(search_sourcegraph "$q" "$SG_LIMIT")
  ALL_SLUGS+="$RESULTS"$'\n'
  sleep 1
done

# Also search for Matrix topic repos via Sourcegraph
RESULTS=$(search_sourcegraph "matrix.to file:README.rst" "500")
ALL_SLUGS+="$RESULTS"$'\n'

# Deduplicate
UNIQUE_SLUGS=$(echo "$ALL_SLUGS" | sort -u | grep -v '^$' || true)
UNIQUE_COUNT=$(echo "$UNIQUE_SLUGS" | grep -c . || echo 0)

echo "" >&2
echo "Found $UNIQUE_COUNT unique GitHub repos." >&2

# ── Phase 2: GitHub API enrichment (per-repo, authenticated) ────
echo "Phase 2: Enriching with GitHub metadata..." >&2
echo "  (authenticated via gh — 5000 req/hr)" >&2

ENRICHED="[]"
FETCHED=0
INCLUDED=0

while IFS= read -r slug; do
  [[ -z "$slug" ]] && continue
  FETCHED=$((FETCHED + 1))
  [[ $INCLUDED -ge $LIMIT ]] && break

  REPO_DATA=$(gh api "repos/$slug" --jq '{
    stars: .stargazers_count,
    forks: .forks_count,
    open_issues: .open_issues_count,
    language: (.language // ""),
    description: (.description // ""),
    topics: (.topics // []),
    pushed_at: (.pushed_at // ""),
    created_at: (.created_at // ""),
    archived: (.archived // false)
  }' 2>/dev/null || echo "null")

  [[ "$REPO_DATA" == "null" || -z "$REPO_DATA" ]] && continue

  STARS=$(echo "$REPO_DATA" | jq '.stars')
  [[ "$STARS" -lt "$MIN_STARS" ]] && continue

  FORKS=$(echo "$REPO_DATA" | jq '.forks')
  PUSHED_AT=$(echo "$REPO_DATA" | jq -r '.pushed_at')
  DAYS_SINCE_PUSH=9999
  if [[ -n "$PUSHED_AT" && "$PUSHED_AT" != "null" ]]; then
    PUSHED_EPOCH=$(date -d "$PUSHED_AT" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    DAYS_SINCE_PUSH=$(( (NOW_EPOCH - PUSHED_EPOCH) / 86400 ))
  fi

  ACTIVITY_SCORE=$(echo "$STARS $FORKS $DAYS_SINCE_PUSH" | awk '{
    recency = ($3 < 1) ? 100 : (1000 / $3);
    print int($1 + $2 * 2 + recency)
  }')

  ENTRY=$(echo "$REPO_DATA" | jq \
    --arg slug "$slug" \
    --arg url "https://github.com/$slug" \
    --argjson days "$DAYS_SINCE_PUSH" \
    --argjson activity "$ACTIVITY_SCORE" \
    '{
      repo: $slug,
      url: $url,
      description: .description,
      language: .language,
      topics: .topics,
      stars: .stars,
      forks: .forks,
      open_issues: .open_issues,
      pushed_at: .pushed_at,
      created_at: .created_at,
      archived: .archived,
      days_since_push: $days,
      activity_score: $activity
    }')

  ENRICHED=$(echo "$ENRICHED" | jq --argjson e "$ENTRY" '. + [$e]')
  INCLUDED=$((INCLUDED + 1))

  if [[ $((FETCHED % 25)) -eq 0 ]]; then
    echo "  Fetched $FETCHED/$UNIQUE_COUNT ($INCLUDED included)..." >&2
  fi

  sleep 0.3
done <<< "$UNIQUE_SLUGS"

# ── Sort ────────────────────────────────────────────────────────
case "$SORT" in
  stars)    SORT_EXPR='sort_by(-.stars)' ;;
  forks)    SORT_EXPR='sort_by(-.forks)' ;;
  activity) SORT_EXPR='sort_by(-.activity_score)' ;;
  updated)  SORT_EXPR='sort_by(.days_since_push)' ;;
  name)     SORT_EXPR='sort_by(.repo)' ;;
  *)        SORT_EXPR='sort_by(-.stars)' ;;
esac

SORTED=$(echo "$ENRICHED" | jq "$SORT_EXPR | .[0:$LIMIT]")
FINAL_COUNT=$(echo "$SORTED" | jq 'length')

# ── Output ──────────────────────────────────────────────────────
case "$FORMAT" in
  json)
    RESULT=$(jq -n \
      --argjson repos "$SORTED" \
      --argjson count "$FINAL_COUNT" \
      --arg sort "$SORT" \
      --arg generated "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '{generated: $generated, sort: $sort, count: $count, repos: $repos}')
    ;;
  csv)
    RESULT=$(echo "$SORTED" | jq -r '
      ["repo","stars","forks","days_since_push","activity_score","language","archived"],
      (.[] | [.repo, .stars, .forks, .days_since_push, .activity_score, .language, .archived]) | @csv')
    ;;
  table)
    RESULT=$(printf "%-45s %6s %6s %5s %7s %s\n" "REPO" "STARS" "FORKS" "DAYS" "SCORE" "LANG"
    echo "$SORTED" | jq -r '.[] | "\(.repo)\t\(.stars)\t\(.forks)\t\(.days_since_push)\t\(.activity_score)\t\(.language)"' \
      | while IFS=$'\t' read -r repo stars forks days score lang; do
          printf "%-45s %6s %6s %5s %7s %s\n" "$repo" "$stars" "$forks" "$days" "$score" "$lang"
        done)
    ;;
esac

echo "" >&2
echo "Results: $FINAL_COUNT repos (sorted by $SORT)." >&2

if [[ -n "$OUTPUT" ]]; then
  echo "$RESULT" > "$OUTPUT"
  echo "Written to $OUTPUT" >&2
else
  echo "$RESULT"
fi
