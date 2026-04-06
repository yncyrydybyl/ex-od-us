#!/usr/bin/env bash
#
# scan-readmes.sh — Scan tracked projects' READMEs for Matrix presence
#
# Reads repo URLs from open GitHub issues, fetches each README,
# scores Matrix presence, and updates data/readme-cache.json.
#
# Requires: curl, jq, gh (authenticated)
# Usage: ./scripts/scan-readmes.sh [--dry-run]
#
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-yncyrydybyl/ex-od-us}"
CACHE_FILE="data/readme-cache.json"
REPORT_FILE="data/scan-report.json"
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# ── Ensure cache file exists ─────────────────────────────────────
if [[ ! -f "$CACHE_FILE" ]]; then
  echo '{}' > "$CACHE_FILE"
fi

CACHE=$(cat "$CACHE_FILE")

# ── Extract repo URLs from open issues ───────────────────────────
echo "Fetching tracked projects from issues..." >&2

ISSUES=$(gh issue list --repo "$REPO" --label project --state open --limit 200 \
  --json number,title,body)

# Parse repo URLs from issue bodies (Source Repository field)
REPOS=$(echo "$ISSUES" | jq -r '
  .[] |
  .body as $body | .number as $num | .title as $title |
  # Extract "### Source Repository\n\n<url>" from issue form body
  ($body // "" | capture("### Source Repository\n\n(?<url>[^\n]+)") | .url // empty) as $url |
  select($url != null and $url != "_No response_" and ($url | length > 0)) |
  # Normalize GitHub URLs to owner/repo
  ($url | capture("github\\.com[/:](?<slug>[^/]+/[^/\\s#?]+)") | .slug | rtrimstr(".git")) as $slug |
  select($slug != null) |
  {number: $num, title: $title, url: $url, slug: $slug}
' 2>/dev/null || echo "")

if [[ -z "$REPOS" || "$REPOS" == "null" ]]; then
  echo "No tracked repos found in issues." >&2
  exit 0
fi

COUNT=$(echo "$REPOS" | jq -s 'length')
echo "Found $COUNT tracked repos." >&2

# ── Scan each README ─────────────────────────────────────────────
CHANGES=0
RESULTS="[]"

while IFS= read -r entry; do
  SLUG=$(echo "$entry" | jq -r '.slug')
  ISSUE_NUM=$(echo "$entry" | jq -r '.number')
  ISSUE_TITLE=$(echo "$entry" | jq -r '.title')

  echo "  Scanning $SLUG (issue #$ISSUE_NUM)..." >&2

  # Get cached SHA
  CACHED_SHA=$(echo "$CACHE" | jq -r --arg s "$SLUG" '.[$s].sha // ""')
  CACHED_ETAG=$(echo "$CACHE" | jq -r --arg s "$SLUG" '.[$s].etag // ""')

  # Fetch README via GitHub API
  HEADERS_FILE=$(mktemp)
  trap "rm -f $HEADERS_FILE" EXIT

  API_ARGS=(-H "Accept: application/vnd.github.v3+json")
  if [[ -n "$CACHED_ETAG" ]]; then
    API_ARGS+=(-H "If-None-Match: $CACHED_ETAG")
  fi

  RESPONSE=$(curl -sS -w "\n%{http_code}" \
    -D "$HEADERS_FILE" \
    "${API_ARGS[@]}" \
    -H "Authorization: token ${GITHUB_TOKEN:-}" \
    "https://api.github.com/repos/$SLUG/readme" 2>/dev/null) || true

  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  # Extract ETag from response headers
  NEW_ETAG=$(grep -i '^etag:' "$HEADERS_FILE" 2>/dev/null | tr -d '\r' | awk '{print $2}' || echo "")
  rm -f "$HEADERS_FILE"

  if [[ "$HTTP_CODE" == "304" ]]; then
    echo "    Unchanged (304)." >&2
    # Carry forward existing data
    EXISTING=$(echo "$CACHE" | jq --arg s "$SLUG" '.[$s]')
    RESULTS=$(echo "$RESULTS" | jq --argjson e "$EXISTING" --arg s "$SLUG" --arg n "$ISSUE_NUM" \
      '. + [$e + {slug: $s, issue: ($n | tonumber), changed: false}]')
    continue
  fi

  if [[ "$HTTP_CODE" != "200" ]]; then
    echo "    Failed (HTTP $HTTP_CODE), skipping." >&2
    continue
  fi

  # Decode README content (base64)
  NEW_SHA=$(echo "$BODY" | jq -r '.sha // ""')
  README_CONTENT=$(echo "$BODY" | jq -r '.content // ""' | base64 -d 2>/dev/null || echo "")
  README_NAME=$(echo "$BODY" | jq -r '.name // "README.md"')

  if [[ -z "$README_CONTENT" ]]; then
    echo "    Empty README, skipping." >&2
    continue
  fi

  CHANGED=false
  if [[ "$NEW_SHA" != "$CACHED_SHA" ]]; then
    CHANGED=true
    CHANGES=$((CHANGES + 1))
    echo "    README changed! (was: ${CACHED_SHA:0:7}, now: ${NEW_SHA:0:7})" >&2
  else
    echo "    Unchanged (same SHA)." >&2
  fi

  # ── Score Matrix presence in README ──────────────────────────
  SCORE=0
  SIGNALS="[]"

  # Matrix room links (matrix.to)
  MATRIX_ROOMS=$(echo "$README_CONTENT" | grep -oP 'matrix\.to/#/[#!+][a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+' | sort -u || true)
  MATRIX_ROOM_COUNT=$(echo "$MATRIX_ROOMS" | grep -c . || echo 0)
  if [[ "$MATRIX_ROOM_COUNT" -gt 0 ]]; then
    SCORE=$((SCORE + 2))
    SIGNALS=$(echo "$SIGNALS" | jq --arg c "$MATRIX_ROOM_COUNT" '. + ["matrix.to links: " + $c]')
  fi

  # Matrix badge (shields.io/matrix or matrix-badge)
  if echo "$README_CONTENT" | grep -qiP '(shields\.io/matrix|matrix-badge|badge.*matrix)'; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Matrix badge found"]')
  fi

  # Matrix mentioned as official/primary channel
  if echo "$README_CONTENT" | grep -qiP '(join\s+(us\s+)?(on|in)\s+matrix|our\s+matrix|matrix\s+room|matrix\s+channel|matrix\s+space)'; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Matrix mentioned as channel"]')
  fi

  # Own homeserver (not matrix.org)
  if echo "$MATRIX_ROOMS" | grep -qvP '(matrix\.org|gitter\.im)' 2>/dev/null && [[ "$MATRIX_ROOM_COUNT" -gt 0 ]]; then
    CUSTOM_HS=$(echo "$MATRIX_ROOMS" | grep -oP '(?<=:)[^/\s]+' | grep -vP '(matrix\.org|gitter\.im)' | sort -u | head -1 || echo "")
    if [[ -n "$CUSTOM_HS" ]]; then
      SCORE=$((SCORE + 2))
      SIGNALS=$(echo "$SIGNALS" | jq --arg h "$CUSTOM_HS" '. + ["Custom homeserver: " + $h]')
    fi
  fi

  # Multiple Matrix rooms
  if [[ "$MATRIX_ROOM_COUNT" -gt 2 ]]; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Multiple Matrix rooms (3+)"]')
  fi

  # Check matrixrooms.info listing
  LISTED_ON_MATRIXROOMS=false
  if [[ "$MATRIX_ROOM_COUNT" -gt 0 ]]; then
    while IFS= read -r room_link; do
      [[ -z "$room_link" ]] && continue
      # Extract room alias or ID (e.g. #room:server.org)
      ROOM_ID=$(echo "$room_link" | grep -oP '#[^/\s"]+' | head -1 || echo "")
      if [[ -n "$ROOM_ID" ]]; then
        # URL-encode the room ID for matrixrooms.info lookup
        ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$ROOM_ID', safe=''))" 2>/dev/null || echo "")
        if [[ -n "$ENCODED" ]]; then
          MR_STATUS=$(curl -sS -o /dev/null -w "%{http_code}" \
            "https://matrixrooms.info/room/$ENCODED" 2>/dev/null || echo "000")
          if [[ "$MR_STATUS" == "200" ]]; then
            LISTED_ON_MATRIXROOMS=true
            break
          fi
        fi
      fi
    done <<< "$MATRIX_ROOMS"
  fi

  if [[ "$LISTED_ON_MATRIXROOMS" == "true" ]]; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Listed on matrixrooms.info"]')
  fi

  # Discord presence
  if echo "$README_CONTENT" | grep -qiP '(discord\.(gg|com)/|join.*discord|discord\s+server)'; then
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Discord present"]')
  fi

  # Telegram presence
  if echo "$README_CONTENT" | grep -qiP '(t\.me/|telegram\.me/|join.*telegram)'; then
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Telegram present"]')
  fi

  # Slack presence
  if echo "$README_CONTENT" | grep -qiP '(slack\.(com|gg)|join.*slack)'; then
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Slack present"]')
  fi

  # IRC presence
  if echo "$README_CONTENT" | grep -qiP '(libera\.chat|freenode|oftc\.net|irc\.(freenode|oftc|libera)|#\w+\s+on\s+\w+)'; then
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["IRC present"]')
  fi

  # Matrix is listed FIRST or most prominently
  # Check if Matrix appears before Discord/Slack/Telegram in the README
  MATRIX_POS=$(echo "$README_CONTENT" | grep -niP 'matrix' | head -1 | cut -d: -f1 || echo 9999)
  DISCORD_POS=$(echo "$README_CONTENT" | grep -niP 'discord' | head -1 | cut -d: -f1 || echo 9999)
  TELEGRAM_POS=$(echo "$README_CONTENT" | grep -niP 'telegram' | head -1 | cut -d: -f1 || echo 9999)
  SLACK_POS=$(echo "$README_CONTENT" | grep -niP 'slack' | head -1 | cut -d: -f1 || echo 9999)

  if [[ "$MATRIX_POS" -lt "$DISCORD_POS" && "$MATRIX_POS" -lt "$TELEGRAM_POS" && "$MATRIX_POS" -lt "$SLACK_POS" && "$MATRIX_POS" -lt 9999 ]]; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Matrix listed before other platforms"]')
  fi

  # Bridge mentions
  if echo "$README_CONTENT" | grep -qiP '(bridge|bridged|bridging).{0,30}(matrix|element|mautrix)'; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Bridge mentioned"]')
  fi

  # Element mentioned
  if echo "$README_CONTENT" | grep -qiP '(element\.(io|im)|app\.element)'; then
    SCORE=$((SCORE + 1))
    SIGNALS=$(echo "$SIGNALS" | jq '. + ["Element client mentioned"]')
  fi

  # Cap score at 10
  [[ "$SCORE" -gt 10 ]] && SCORE=10

  # Extract Matrix room list
  ROOMS_JSON=$(echo "$MATRIX_ROOMS" | jq -R -s 'split("\n") | map(select(length > 0))')

  # Build result entry
  ENTRY=$(jq -n \
    --arg slug "$SLUG" \
    --arg sha "$NEW_SHA" \
    --arg etag "$NEW_ETAG" \
    --argjson issue "$ISSUE_NUM" \
    --argjson score "$SCORE" \
    --argjson signals "$SIGNALS" \
    --argjson rooms "$ROOMS_JSON" \
    --argjson changed "$CHANGED" \
    --argjson matrixrooms "$LISTED_ON_MATRIXROOMS" \
    --arg scanned "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      slug: $slug,
      sha: $sha,
      etag: $etag,
      issue: $issue,
      score: $score,
      signals: $signals,
      matrix_rooms: $rooms,
      listed_on_matrixrooms: $matrixrooms,
      changed: $changed,
      scanned: $scanned
    }')

  RESULTS=$(echo "$RESULTS" | jq --argjson e "$ENTRY" '. + [$e]')

  # Update cache
  CACHE=$(echo "$CACHE" | jq --argjson e "$ENTRY" --arg s "$SLUG" '.[$s] = ($e | del(.changed))')

  # Rate limiting: small delay between requests
  sleep 0.5

done < <(echo "$REPOS" | jq -c '.')

# ── Write results ────────────────────────────────────────────────
echo "$CACHE" | jq '.' > "$CACHE_FILE"

REPORT=$(jq -n \
  --argjson results "$RESULTS" \
  --argjson total "$COUNT" \
  --argjson changes "$CHANGES" \
  --arg scanned "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    scanned: $scanned,
    total_repos: $total,
    changed: $changes,
    results: $results
  }')
echo "$REPORT" | jq '.' > "$REPORT_FILE"

echo "" >&2
echo "Scan complete: $COUNT repos, $CHANGES changed." >&2

if [[ "$CHANGES" -gt 0 ]]; then
  echo "" >&2
  echo "Changed repos:" >&2
  echo "$RESULTS" | jq -r '.[] | select(.changed) | "  \(.slug) (issue #\(.issue)) — score: \(.score)/10"'  >&2
fi

# Output changed repos for downstream steps
echo "$RESULTS" | jq '[.[] | select(.changed)]'
