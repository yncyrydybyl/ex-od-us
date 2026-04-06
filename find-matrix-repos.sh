#!/usr/bin/env bash
#
# find-matrix-repos.sh — Find GitHub repos with Matrix presence in their READMEs
#
# Uses 'gh search code' to find repos with matrix.to links or Matrix badges,
# then enriches with repo metadata and sorts by popularity/activity.
#
# Requires: gh (authenticated), jq
# Output:   JSON array sorted by rank
#
# Usage: ./find-matrix-repos.sh [OPTIONS]
#
set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────
LIMIT=100
OUTPUT=""
SORT="stars"           # stars | forks | activity | updated | name
MIN_STARS=0
MIN_FORKS=0
LANGUAGE=""
QUERY_EXTRA=""
FORMAT="json"          # json | csv | table

usage() {
  cat <<'EOF'
Usage: find-matrix-repos.sh [OPTIONS]

Find GitHub repos with Matrix presence (matrix.to links, badges) in their READMEs.
Results default to most popular repos first.

Sorting & filtering:
  --sort KEY         Sort by: stars (default), forks, activity, updated, name
  --min-stars N      Minimum star count (default: 0)
  --min-forks N      Minimum fork count (default: 0)
  --language LANG    Filter by primary language (e.g. Python, Rust, Go)

Output:
  --limit N          Max results to return (default: 100)
  --output FILE      Write to FILE (default: stdout)
  --format FMT       Output format: json (default), csv, table
  --query EXTRA      Append extra terms to the search query

General:
  -h, --help         Show this help

Examples:
  # Top 50 most-starred repos with Matrix rooms
  ./find-matrix-repos.sh --limit 50 --sort stars

  # Active Rust projects with Matrix presence
  ./find-matrix-repos.sh --language Rust --min-stars 100 --sort activity

  # Table output for quick scanning
  ./find-matrix-repos.sh --limit 20 --format table

  # Find repos with Matrix + Telegram mentions
  ./find-matrix-repos.sh --query "telegram" --sort stars
EOF
  exit 0
}

# ── Parse arguments ─────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sort)       SORT="$2"; shift 2 ;;
    --min-stars)  MIN_STARS="$2"; shift 2 ;;
    --min-forks)  MIN_FORKS="$2"; shift 2 ;;
    --language)   LANGUAGE="$2"; shift 2 ;;
    --limit)      LIMIT="$2"; shift 2 ;;
    --output)     OUTPUT="$2"; shift 2 ;;
    --format)     FORMAT="$2"; shift 2 ;;
    --query)      QUERY_EXTRA="$2"; shift 2 ;;
    -h|--help)    usage ;;
    *)            echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

for cmd in gh jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not found." >&2
    exit 1
  fi
done

# ── Search for repos ────────────────────────────────────────────
# gh search code returns up to 100 results per call, paginates well,
# and uses the newer code search that actually works reliably.

SEARCH_LIMIT=$((LIMIT * 3))  # oversample since we'll dedupe and filter
[[ $SEARCH_LIMIT -gt 1000 ]] && SEARCH_LIMIT=1000

QUERIES=(
  "matrix.to filename:README"
  "img.shields.io/matrix filename:README"
)

echo "Searching GitHub for repos with Matrix presence..." >&2
echo "  Sort: $SORT | Limit: $LIMIT | Min stars: $MIN_STARS" >&2
[[ -n "$LANGUAGE" ]] && echo "  Language: $LANGUAGE" >&2

ALL_SLUGS=""

for query in "${QUERIES[@]}"; do
  FULL_QUERY="$query"
  [[ -n "$LANGUAGE" ]] && FULL_QUERY+=" language:$LANGUAGE"
  [[ -n "$QUERY_EXTRA" ]] && FULL_QUERY+=" $QUERY_EXTRA"

  echo "  Query: $FULL_QUERY" >&2

  RESULTS=$(gh search code "$FULL_QUERY" \
    --limit "$SEARCH_LIMIT" \
    --json repository \
    --jq '.[].repository.nameWithOwner' 2>/dev/null || echo "")

  COUNT=$(echo "$RESULTS" | grep -c . || echo 0)
  echo "  → $COUNT matches" >&2

  ALL_SLUGS+="$RESULTS"$'\n'
done

# Deduplicate
UNIQUE_SLUGS=$(echo "$ALL_SLUGS" | sort -u | grep -v '^$' || true)
UNIQUE_COUNT=$(echo "$UNIQUE_SLUGS" | grep -c . || echo 0)

echo "" >&2
echo "Found $UNIQUE_COUNT unique repos. Fetching metadata..." >&2

# ── Enrich with repo metadata ───────────────────────────────────
# Fetch stars, forks, language, topics, push date for each repo.
# Use gh api for authenticated, high-rate-limit access.

ENRICHED="[]"
FETCHED=0
INCLUDED=0

while IFS= read -r slug; do
  [[ -z "$slug" ]] && continue
  FETCHED=$((FETCHED + 1))

  # Stop once we have enough
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
    archived: (.archived // false),
    default_branch: (.default_branch // "main")
  }' 2>/dev/null || echo "null")

  if [[ "$REPO_DATA" == "null" || -z "$REPO_DATA" ]]; then
    echo "  Skipping $slug (not found)" >&2
    continue
  fi

  STARS=$(echo "$REPO_DATA" | jq '.stars')
  FORKS=$(echo "$REPO_DATA" | jq '.forks')

  # Apply filters
  [[ "$STARS" -lt "$MIN_STARS" ]] && continue
  [[ "$FORKS" -lt "$MIN_FORKS" ]] && continue

  PUSHED_AT=$(echo "$REPO_DATA" | jq -r '.pushed_at')
  DAYS_SINCE_PUSH=9999
  if [[ -n "$PUSHED_AT" && "$PUSHED_AT" != "null" ]]; then
    PUSHED_EPOCH=$(date -d "$PUSHED_AT" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    DAYS_SINCE_PUSH=$(( (NOW_EPOCH - PUSHED_EPOCH) / 86400 ))
  fi

  # Activity score: stars + 2*forks + recency bonus
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

  # Progress
  if [[ $((FETCHED % 20)) -eq 0 ]]; then
    echo "  Fetched $FETCHED/$UNIQUE_COUNT repos ($INCLUDED included)..." >&2
  fi

  # Be polite with rate limits (5000/hr = ~1.4/sec)
  sleep 0.3

done <<< "$UNIQUE_SLUGS"

# ── Sort ────────────────────────────────────────────────────────
case "$SORT" in
  stars)    SORT_EXPR='sort_by(-.stars)' ;;
  forks)    SORT_EXPR='sort_by(-.forks)' ;;
  activity) SORT_EXPR='sort_by(-.activity_score)' ;;
  updated)  SORT_EXPR='sort_by(.days_since_push)' ;;
  name)     SORT_EXPR='sort_by(.repo)' ;;
  *)        echo "Unknown sort: $SORT" >&2; SORT_EXPR='sort_by(-.stars)' ;;
esac

SORTED=$(echo "$ENRICHED" | jq "$SORT_EXPR | .[0:$LIMIT]")
FINAL_COUNT=$(echo "$SORTED" | jq 'length')

# ── Format output ───────────────────────────────────────────────
case "$FORMAT" in
  json)
    RESULT=$(jq -n \
      --argjson repos "$SORTED" \
      --argjson count "$FINAL_COUNT" \
      --arg sort "$SORT" \
      --arg generated "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '{
        generated: $generated,
        sort: $sort,
        count: $count,
        repos: $repos
      }')
    ;;
  csv)
    RESULT=$(echo "$SORTED" | jq -r '
      ["repo","stars","forks","days_since_push","activity_score","language","archived"],
      (.[] | [.repo, .stars, .forks, .days_since_push, .activity_score, .language, .archived]) | @csv
    ')
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
