#!/usr/bin/env bash
# Open a draft PR for the current handoff branch. Cloud agent does not open PRs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE="main"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--base main]"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "FAIL: GitHub CLI (gh) not found. Install/auth: https://cli.github.com/"
  echo "Or open a draft PR manually from the handoff branch."
  exit 1
fi

HANDOFF="cloud_in/HANDOFF.md"
STAGE_ID="$(grep -Eo 'D[0-9]+' "$HANDOFF" 2>/dev/null | head -1 || echo D0)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
EXPECTED="$(grep -E '^\| Branch' "$HANDOFF" 2>/dev/null | head -1 | sed -E 's/.*`([^`]+)`.*/\1/' || true)"
if [[ -n "$EXPECTED" && "$BRANCH" != "$EXPECTED" ]]; then
  echo "WARN: on branch '$BRANCH', HANDOFF expects '$EXPECTED'"
  echo "      checkout the handoff branch or continue carefully."
fi

# Ensure remote is up to date
git push -u origin HEAD

EXISTING="$(gh pr list --head "$BRANCH" --json url,number --jq '.[0].url' 2>/dev/null || true)"
if [[ -n "$EXISTING" ]]; then
  echo "PR already exists: $EXISTING"
  exit 0
fi

REPORT="agent_docs/reports/${STAGE_ID}/gate_${STAGE_ID}.md"
# gate file may be gate_D0.md
if [[ ! -f "$REPORT" ]]; then
  REPORT="$(ls agent_docs/reports/"${STAGE_ID}"/gate_*.md 2>/dev/null | head -1 || true)"
fi

TITLE="${STAGE_ID}: cloud stage result (${BRANCH})"
BODY="$(cat <<EOF
## Summary
- Cloud stage \`${STAGE_ID}\` on \`${BRANCH}\`
- Agent wrote code under \`src/\` / \`tests/\` and reports under \`cloud_out/\` (ingested to \`agent_docs/reports/${STAGE_ID}/\`)
- PR opened locally via \`scripts/cloud_pr.sh\` (cloud agent does not open PRs)

## Gate report
$(if [[ -n "$REPORT" && -f "$REPORT" ]]; then echo "See \`${REPORT}\`"; else echo "_Gate report not found yet — run ./scripts/cloud_ingest.sh first_"; fi)

## Human checklist
- [ ] Read gate verdict (PASS / FAIL / BLOCKED)
- [ ] Spot-check diff
- [ ] Run human gate for this stage (see roadmap / test strategy)
- [ ] Merge when ready

## Test plan
- [ ] \`uv run pytest tests/ -v\` (if project exists)
- [ ] Stage-specific gate ids from \`agent_docs/contracts/quality_gates.md\`
EOF
)"

URL="$(gh pr create --draft --base "$BASE" --head "$BRANCH" --title "$TITLE" --body "$BODY")"
echo "Draft PR: $URL"
