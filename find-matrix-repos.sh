#!/usr/bin/env bash
#
# find-matrix-repos.sh — Find GitHub repos with matrix.to links in their READMEs
#
# Uses Sourcegraph code search (no auth required for public repos).
# Single GraphQL query, no per-repo API calls.
#
# Requires: curl, jq
# Output:   JSON array ready for static site generation
#
# Usage: ./find-matrix-repos.sh [--limit N] [--output FILE]
#
set -euo pipefail

LIMIT=500
OUTPUT=""
SGRAPH="https://sourcegraph.com/.api/graphql"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Search Sourcegraph for GitHub repos with matrix.to badges in their README.

Options:
  --limit N      Max results (default: 500)
  --output FILE  Write JSON to FILE (default: stdout)
  -h, --help     Show this help
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit)  LIMIT="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

for cmd in curl jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not found." >&2
    exit 1
  fi
done

# ── Sourcegraph GraphQL query ────────────────────────────────────────────────
# Returns repo name + matching lines so we can extract room IDs and badge type
# without a second round-trip.

search_sourcegraph() {
  local query="$1"
  echo "  Query: $query" >&2

  local gql='query { search(query: "'"$query"' count:'"$LIMIT"'", version: V3, patternType: literal) { results { matchCount results { ... on FileMatch { repository { name } file { name } lineMatches { preview } } } } } }'
  local body
  body=$(jq -n --arg q "$gql" '{query: $q}')

  curl -sf "$SGRAPH" \
    -H 'Content-Type: application/json' \
    -d "$body" 2>/dev/null
}

# ── Run searches ─────────────────────────────────────────────────────────────
# Two queries cover the space: one broad matrix.to match, one for shields badges
# that may use the API endpoint without a matrix.to link.

QUERIES=(
  "matrix.to file:README"
  "img.shields.io/matrix file:README"
)

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

i=0
for q in "${QUERIES[@]}"; do
  result=$(search_sourcegraph "$q")
  echo "$result" > "$tmpdir/result_$i.json"
  count=$(echo "$result" | jq '.data.search.results.matchCount // 0')
  echo "  → $count matches" >&2
  (( i++ )) || true
done

# ── Merge & deduplicate ─────────────────────────────────────────────────────
# Combine all FileMatch results, dedup by repo, extract metadata from the
# matching lines themselves (no extra API calls needed).

jq -s '
  # Flatten all FileMatch results from all queries
  [ .[].data.search.results.results[]?
    | select(.repository != null)
  ]
  # Group by repo to dedup
  | group_by(.repository.name)
  | map(
      # Merge all line previews for the repo
      (.[0].repository.name) as $raw_name
      | ($raw_name | ltrimstr("github.com/")) as $repo
      | ([.[] | .lineMatches[]?.preview] | join("\n")) as $lines

      # Classify badge type from matched lines
      | (if ($lines | test("matrix-badge\\.svg")) then "official-badge"
         elif ($lines | test("img\\.shields\\.io/matrix")) then "shields-badge"
         elif ($lines | test("(?i)\\[.*badge.*\\].*matrix\\.to|!\\[.*matrix.*\\].*matrix\\.to")) then "custom-badge"
         else "text-link"
         end) as $badge_type

      # Extract matrix room from matrix.to URL
      | ([$lines | scan("matrix\\.to/#/([^\\s)\\]\"'\''>]+)") | .[0]] | first // null) as $room

      # Extract shields.io room if no matrix.to room found
      | (if $room == null
         then [$lines | scan("img\\.shields\\.io/matrix/([^?\\s)\\]\"]+)") | .[0]] | first // null
         else null end) as $shields_room

      | ($room // $shields_room // null) as $final_room

      # Build output object
      | {
          repo: $repo,
          url: ("https://github.com/" + $repo),
          badge_type: $badge_type,
          matrix_room: (if $final_room then
                          (if ($final_room | startswith("#") or startswith("!") or startswith("+"))
                           then $final_room
                           else "#" + $final_room end)
                        else null end),
          matrix_url: (if $final_room then
                         "https://matrix.to/#/" + $final_room
                       else null end)
        }
  )
  | sort_by(.repo)

  # Wrap in a top-level object with metadata
  | {
      generated: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
      count: length,
      repos: .
    }
' "$tmpdir"/result_*.json > "$tmpdir/merged.json"

count=$(jq '.count' "$tmpdir/merged.json")
echo "" >&2
echo "Found $count unique repos." >&2

# ── Output ───────────────────────────────────────────────────────────────────
if [[ -n "$OUTPUT" ]]; then
  mv "$tmpdir/merged.json" "$OUTPUT"
  echo "Written to $OUTPUT" >&2
else
  cat "$tmpdir/merged.json"
fi
