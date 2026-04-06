#!/usr/bin/env bash
#
# find-matrix-repos.sh — Find GitHub repos with Matrix presence in their READMEs
#
# Uses GitHub code search API to find repos with matrix.to links or Matrix badges.
# Results are ranked by popularity (stars, forks, recent activity) by default.
#
# Requires: curl, jq, gh (for authenticated API access — much higher rate limits)
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
TOPIC=""
QUERY_EXTRA=""
CREATED_AFTER=""
PUSHED_AFTER=""
FORMAT="json"          # json | csv | table

usage() {
  cat <<'EOF'
Usage: find-matrix-repos.sh [OPTIONS]

Find GitHub repos with Matrix presence (matrix.to links, badges) in their READMEs.
Results default to most popular/active repos first.

Sorting & filtering:
  --sort KEY         Sort by: stars (default), forks, activity, updated, name
  --min-stars N      Minimum star count (default: 0)
  --min-forks N      Minimum fork count (default: 0)
  --language LANG    Filter by primary language (e.g. Python, Rust, Go)
  --topic TOPIC      Filter by GitHub topic (e.g. matrix, chat, encryption)
  --created-after DATE  Only repos created after DATE (YYYY-MM-DD)
  --pushed-after DATE   Only repos pushed to after DATE (YYYY-MM-DD)

Output:
  --limit N          Max results (default: 100)
  --output FILE      Write to FILE (default: stdout)
  --format FMT       Output format: json (default), csv, table
  --query EXTRA      Append extra terms to the GitHub search query

General:
  -h, --help         Show this help

Examples:
  # Top 50 most-starred repos with Matrix rooms
  ./find-matrix-repos.sh --limit 50 --sort stars

  # Active Rust projects with Matrix presence
  ./find-matrix-repos.sh --language Rust --min-stars 100 --sort activity

  # Recently created projects
  ./find-matrix-repos.sh --created-after 2025-01-01 --sort stars

  # Projects pushed to in the last 6 months
  ./find-matrix-repos.sh --pushed-after 2025-10-01 --sort updated
EOF
  exit 0
}

# ── Parse arguments ─────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sort)           SORT="$2"; shift 2 ;;
    --min-stars)      MIN_STARS="$2"; shift 2 ;;
    --min-forks)      MIN_FORKS="$2"; shift 2 ;;
    --language)       LANGUAGE="$2"; shift 2 ;;
    --topic)          TOPIC="$2"; shift 2 ;;
    --created-after)  CREATED_AFTER="$2"; shift 2 ;;
    --pushed-after)   PUSHED_AFTER="$2"; shift 2 ;;
    --limit)          LIMIT="$2"; shift 2 ;;
    --output)         OUTPUT="$2"; shift 2 ;;
    --format)         FORMAT="$2"; shift 2 ;;
    --query)          QUERY_EXTRA="$2"; shift 2 ;;
    -h|--help)        usage ;;
    *)                echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

for cmd in curl jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not found." >&2
    exit 1
  fi
done

# Prefer gh auth token if available, fall back to GITHUB_TOKEN
TOKEN=""
if command -v gh &>/dev/null; then
  TOKEN=$(gh auth token 2>/dev/null || echo "")
fi
TOKEN="${TOKEN:-${GITHUB_TOKEN:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "Warning: No GitHub token found. Rate limit: 10 searches/min." >&2
  echo "  Run 'gh auth login' or set GITHUB_TOKEN for 30 searches/min." >&2
  AUTH_HEADER=""
else
  AUTH_HEADER="Authorization: token $TOKEN"
fi

# ── Build search queries ────────────────────────────────────────
# GitHub code search: find repos with matrix.to in README files
# We search for multiple patterns to maximize coverage

build_qualifiers() {
  local q=""
  [[ -n "$LANGUAGE" ]] && q+=" language:$LANGUAGE"
  [[ -n "$TOPIC" ]] && q+=" topic:$TOPIC"
  [[ "$MIN_STARS" -gt 0 ]] && q+=" stars:>=$MIN_STARS"
  [[ "$MIN_FORKS" -gt 0 ]] && q+=" forks:>=$MIN_FORKS"
  [[ -n "$CREATED_AFTER" ]] && q+=" created:>$CREATED_AFTER"
  [[ -n "$PUSHED_AFTER" ]] && q+=" pushed:>$PUSHED_AFTER"
  [[ -n "$QUERY_EXTRA" ]] && q+=" $QUERY_EXTRA"
  echo "$q"
}

QUALIFIERS=$(build_qualifiers)

# Search patterns — each finds a different Matrix signal
SEARCHES=(
  "matrix.to path:README${QUALIFIERS}"
  "img.shields.io/matrix path:README${QUALIFIERS}"
)

echo "Searching GitHub for repos with Matrix presence..." >&2
echo "  Sort: $SORT | Limit: $LIMIT | Min stars: $MIN_STARS" >&2
[[ -n "$LANGUAGE" ]] && echo "  Language: $LANGUAGE" >&2
[[ -n "$TOPIC" ]] && echo "  Topic: $TOPIC" >&2

# ── Search function ───────────────────────────��─────────────────
github_code_search() {
  local query="$1"
  local page=1
  local collected=0
  local all_items="[]"

  echo "  Query: $query" >&2

  while [[ $collected -lt $LIMIT ]]; do
    local per_page=100
    [[ $((LIMIT - collected)) -lt 100 ]] && per_page=$((LIMIT - collected))

    local url="https://api.github.com/search/code?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$query'''))")&per_page=$per_page&page=$page"

    local headers=(-H "Accept: application/vnd.github.v3+json")
    [[ -n "$AUTH_HEADER" ]] && headers+=(-H "$AUTH_HEADER")

    local response
    response=$(curl -sS "${headers[@]}" "$url" 2>/dev/null)

    # Check for rate limiting
    if echo "$response" | jq -e '.message' 2>/dev/null | grep -qi "rate limit"; then
      echo "  Rate limited. Waiting 60s..." >&2
      sleep 60
      continue
    fi

    local items
    items=$(echo "$response" | jq '.items // []')
    local count
    count=$(echo "$items" | jq 'length')

    if [[ "$count" -eq 0 ]]; then
      break
    fi

    all_items=$(echo "$all_items" "$items" | jq -s '.[0] + .[1]')
    collected=$((collected + count))
    page=$((page + 1))

    # GitHub code search returns max 1000 results
    local total
    total=$(echo "$response" | jq '.total_count // 0')
    echo "  → page $((page-1)): $count results (total available: $total)" >&2

    if [[ $count -lt $per_page ]]; then
      break
    fi

    # Rate limit: code search is 10/min unauthenticated, 30/min authenticated
    sleep 2
  done

  echo "$all_items"
}

# ── Run searches and collect unique repos ───────────────────────
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

ALL_REPOS="[]"
for query in "${SEARCHES[@]}"; do
  RESULTS=$(github_code_search "$query")
  ALL_REPOS=$(echo "$ALL_REPOS" "$RESULTS" | jq -s '.[0] + .[1]')
  sleep 3  # pause between different searches
done

# Deduplicate by repo full_name and extract repo slugs
REPO_SLUGS=$(echo "$ALL_REPOS" | jq -r '[.[] | .repository.full_name] | unique | .[]')
UNIQUE_COUNT=$(echo "$REPO_SLUGS" | grep -c . || echo 0)
echo "" >&2
echo "Found $UNIQUE_COUNT unique repos. Fetching metadata..." >&2

# ── Fetch repo metadata (stars, forks, updated_at) ──────────────
ENRICHED="[]"
FETCHED=0

while IFS= read -r slug; do
  [[ -z "$slug" ]] && continue
  FETCHED=$((FETCHED + 1))

  if [[ $FETCHED -gt $LIMIT ]]; then
    break
  fi

  local_headers=(-H "Accept: application/vnd.github.v3+json")
  [[ -n "$AUTH_HEADER" ]] && local_headers+=(-H "$AUTH_HEADER")

  REPO_DATA=$(curl -sS "${local_headers[@]}" \
    "https://api.github.com/repos/$slug" 2>/dev/null)

  # Skip if repo not found or error
  if echo "$REPO_DATA" | jq -e '.message' &>/dev/null; then
    echo "  Skipping $slug ($(echo "$REPO_DATA" | jq -r '.message'))" >&2
    continue
  fi

  # Extract matching lines from the code search results for this repo
  MATCH_LINES=$(echo "$ALL_REPOS" | jq -r \
    --arg s "$slug" '[.[] | select(.repository.full_name == $s) | .text_matches[]?.fragment // empty] | join("\n")' 2>/dev/null || echo "")

  # Extract Matrix room from matched content
  MATRIX_ROOM=$(echo "$MATCH_LINES" | grep -oP 'matrix\.to/#/[^\s)"\]'"'"']+' | head -1 || echo "")

  # Detect badge type
  BADGE_TYPE="text-link"
  if echo "$MATCH_LINES" | grep -qiP 'shields\.io/matrix'; then
    BADGE_TYPE="shields-badge"
  elif echo "$MATCH_LINES" | grep -qiP 'matrix-badge'; then
    BADGE_TYPE="official-badge"
  fi

  # Calculate activity score (recent pushes, issues, etc.)
  STARS=$(echo "$REPO_DATA" | jq '.stargazers_count // 0')
  FORKS=$(echo "$REPO_DATA" | jq '.forks_count // 0')
  OPEN_ISSUES=$(echo "$REPO_DATA" | jq '.open_issues_count // 0')
  PUSHED_AT=$(echo "$REPO_DATA" | jq -r '.pushed_at // ""')
  CREATED_AT=$(echo "$REPO_DATA" | jq -r '.created_at // ""')
  UPDATED_AT=$(echo "$REPO_DATA" | jq -r '.updated_at // ""')
  DESCRIPTION=$(echo "$REPO_DATA" | jq -r '.description // ""')
  LANG=$(echo "$REPO_DATA" | jq -r '.language // ""')
  TOPICS=$(echo "$REPO_DATA" | jq '.topics // []')
  ARCHIVED=$(echo "$REPO_DATA" | jq '.archived // false')
  DEFAULT_BRANCH=$(echo "$REPO_DATA" | jq -r '.default_branch // "main"')

  # Days since last push (for activity ranking)
  if [[ -n "$PUSHED_AT" && "$PUSHED_AT" != "null" ]]; then
    PUSHED_EPOCH=$(date -d "$PUSHED_AT" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    DAYS_SINCE_PUSH=$(( (NOW_EPOCH - PUSHED_EPOCH) / 86400 ))
  else
    DAYS_SINCE_PUSH=9999
  fi

  # Activity score: combines stars, forks, recency
  # Higher is better
  ACTIVITY_SCORE=$(echo "$STARS $FORKS $DAYS_SINCE_PUSH" | awk '{
    recency = ($3 < 1) ? 100 : (1000 / $3);
    print int($1 + $2 * 2 + recency)
  }')

  ENTRY=$(jq -n \
    --arg slug "$slug" \
    --arg url "https://github.com/$slug" \
    --arg desc "$DESCRIPTION" \
    --arg lang "$LANG" \
    --argjson topics "$TOPICS" \
    --argjson stars "$STARS" \
    --argjson forks "$FORKS" \
    --argjson open_issues "$OPEN_ISSUES" \
    --arg pushed_at "$PUSHED_AT" \
    --arg created_at "$CREATED_AT" \
    --argjson archived "$ARCHIVED" \
    --argjson days_since_push "$DAYS_SINCE_PUSH" \
    --argjson activity_score "$ACTIVITY_SCORE" \
    --arg badge_type "$BADGE_TYPE" \
    --arg matrix_room "$MATRIX_ROOM" \
    --arg matrix_url "$([ -n "$MATRIX_ROOM" ] && echo "https://$MATRIX_ROOM" || echo "")" \
    '{
      repo: $slug,
      url: $url,
      description: $desc,
      language: $lang,
      topics: $topics,
      stars: $stars,
      forks: $forks,
      open_issues: $open_issues,
      pushed_at: $pushed_at,
      created_at: $created_at,
      archived: $archived,
      days_since_push: $days_since_push,
      activity_score: $activity_score,
      badge_type: $badge_type,
      matrix_room: (if $matrix_room == "" then null else $matrix_room end),
      matrix_url: (if $matrix_url == "" then null else $matrix_url end)
    }')

  ENRICHED=$(echo "$ENRICHED" | jq --argjson e "$ENTRY" '. + [$e]')

  # Progress
  if [[ $((FETCHED % 10)) -eq 0 ]]; then
    echo "  Fetched $FETCHED/$UNIQUE_COUNT repos..." >&2
  fi

  # Rate limit: 5000/hr authenticated, be polite
  sleep 0.3

done <<< "$REPO_SLUGS"

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
      ["repo","stars","forks","days_since_push","activity_score","language","badge_type","matrix_room","archived"],
      (.[] | [.repo, .stars, .forks, .days_since_push, .activity_score, .language, .badge_type, (.matrix_room // ""), .archived]) | @csv
    ')
    ;;
  table)
    RESULT=$(echo "$SORTED" | jq -r '
      "REPO\tSTARS\tFORKS\tDAYS\tSCORE\tLANG\tMATRIX",
      (.[] | "\(.repo)\t\(.stars)\t\(.forks)\t\(.days_since_push)\t\(.activity_score)\t\(.language)\t\(.badge_type)")
    ' | column -t -s$'\t')
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
