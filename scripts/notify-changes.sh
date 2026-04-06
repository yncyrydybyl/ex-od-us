#!/usr/bin/env bash
#
# notify-changes.sh — Comment on issues when tracked READMEs change
#
# Reads the output of scan-readmes.sh (changed repos JSON on stdin)
# and posts a comment on each affected issue with the new score and signals.
#
# Requires: jq, gh (authenticated)
# Usage: echo "$CHANGED_JSON" | ./scripts/notify-changes.sh
#
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-yncyrydybyl/ex-od-us}"

CHANGED=$(cat)

if [[ -z "$CHANGED" || "$CHANGED" == "[]" || "$CHANGED" == "null" ]]; then
  echo "No changes to report." >&2
  exit 0
fi

COUNT=$(echo "$CHANGED" | jq 'length')
echo "Posting comments on $COUNT issues..." >&2

echo "$CHANGED" | jq -c '.[]' | while IFS= read -r entry; do
  ISSUE=$(echo "$entry" | jq -r '.issue')
  SLUG=$(echo "$entry" | jq -r '.slug')
  SCORE=$(echo "$entry" | jq -r '.score')
  SHA=$(echo "$entry" | jq -r '.sha')
  SCANNED=$(echo "$entry" | jq -r '.scanned')
  SIGNALS=$(echo "$entry" | jq -r '.signals | map("- " + .) | join("\n")')
  ROOMS=$(echo "$entry" | jq -r '.matrix_rooms | map("- `" + . + "`") | join("\n")')

  # Score bar visualization
  FILLED=$SCORE
  EMPTY=$((10 - FILLED))
  BAR=$(printf '%0.s█' $(seq 1 $FILLED 2>/dev/null) || true)$(printf '%0.s░' $(seq 1 $EMPTY 2>/dev/null) || true)

  COMMENT="## README Scanner Update

**Repository:** [\`$SLUG\`](https://github.com/$SLUG)
**Scanned:** $SCANNED
**README SHA:** \`${SHA:0:12}\`

### Matrix Presence Score: $SCORE/10 $BAR

**Signals detected:**
$SIGNALS"

  if [[ -n "$ROOMS" ]]; then
    COMMENT="$COMMENT

**Matrix rooms found:**
$ROOMS"
  fi

  COMMENT="$COMMENT

---
*Automated scan by [ex-od-us](https://github.com/$REPO) README scanner.*"

  echo "  Commenting on issue #$ISSUE ($SLUG, score $SCORE/10)..." >&2
  gh issue comment "$ISSUE" --repo "$REPO" --body "$COMMENT"
  sleep 0.5
done

echo "Done." >&2
