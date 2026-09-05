#!/usr/bin/env bash
# Two-phase pull: (1) fetch cloud_out reports only (2) if gate PASS → full branch checkout.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH=""
FORCE_CODE=0
REPORTS_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --force-code) FORCE_CODE=1; shift ;;
    --reports-only) REPORTS_ONLY=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--branch NAME] [--reports-only] [--force-code]"
      echo "  1) fetch origin/<branch> and copy cloud_out → agent_docs/reports/<stage>/"
      echo "  2) if gate Verdict is PASS (or PASS_WITH_WARNINGS), checkout full branch with code"
      echo "  --reports-only  stop after step 1"
      echo "  --force-code    checkout full branch even if gate is FAIL/BLOCKED"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

HANDOFF="cloud_in/HANDOFF.md"
STAGE_ID="$(grep -Eo 'D[0-9]+' "$HANDOFF" 2>/dev/null | head -1 || echo D0)"
if [[ -z "$BRANCH" ]]; then
  BRANCH="$(grep -E '^\| Branch' "$HANDOFF" 2>/dev/null | head -1 | sed -E 's/.*`([^`]+)`.*/\1/' || true)"
  if [[ -z "${BRANCH}" ]]; then
    BRANCH="$(grep -Eo 'cursor/[A-Za-z0-9._-]+' "$HANDOFF" 2>/dev/null | head -1 || true)"
  fi
fi
if [[ -z "${BRANCH}" ]]; then
  echo "FAIL: pass --branch or set Branch in cloud_in/HANDOFF.md"
  exit 1
fi

echo "=== cloud_pull phase 1: reports ==="
echo "branch: origin/$BRANCH"
echo "stage:  $STAGE_ID"

git fetch origin "$BRANCH"

REPORT_DIR="agent_docs/reports/${STAGE_ID}"
mkdir -p "$REPORT_DIR" agent_docs/progress cloud_out
# Materialize remote cloud_out into working tree without switching branch yet
if git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
  git checkout "origin/$BRANCH" -- cloud_out 2>/dev/null || true
fi

COPIED=0
shopt -s nullglob
for f in cloud_out/gate_*.md cloud_out/run_meta.json cloud_out/BLOCKED.md; do
  [[ -e "$f" ]] || continue
  cp -f "$f" "$REPORT_DIR/"
  echo "copied $f → $REPORT_DIR/"
  COPIED=1
done
shopt -u nullglob

COMMIT="$(git rev-parse "origin/$BRANCH")"
SHORT="$(git rev-parse --short "origin/$BRANCH")"
PULLED_AT="$(date -Iseconds)"

cat > "$REPORT_DIR/manifest.json" <<EOF
{
  "stage": "${STAGE_ID}",
  "branch": "${BRANCH}",
  "commit": "${COMMIT}",
  "pulled_at": "${PULLED_AT}",
  "phase": "reports"
}
EOF

LOG="agent_docs/progress/log.md"
if [[ ! -f "$LOG" ]]; then
  printf '# Progress log (append-only)\n\n' > "$LOG"
fi
echo "- ${PULLED_AT} pull-reports ${STAGE_ID} ${BRANCH} ${SHORT}" >> "$LOG"

if [[ "$COPIED" -eq 0 ]]; then
  echo
  echo "RESULT: NO_REPORTS"
  echo "  origin/$BRANCH has no cloud_out/gate_*.md yet."
  echo "  Wait for the cloud agent to finish, then re-run."
  exit 2
fi

GATE_FILE="$(ls "$REPORT_DIR"/gate_*.md 2>/dev/null | head -1 || true)"
VERDICT="UNKNOWN"
if [[ -n "$GATE_FILE" ]]; then
  # Prefer explicit "## Verdict: X" then any Verdict line
  LINE="$(grep -Ei 'Verdict' "$GATE_FILE" | head -1 || true)"
  if echo "$LINE" | grep -Eiq 'PASS_WITH_WARNINGS'; then
    VERDICT="PASS_WITH_WARNINGS"
  elif echo "$LINE" | grep -Eiq '\bPASS\b'; then
    VERDICT="PASS"
  elif echo "$LINE" | grep -Eiq '\bFAIL\b'; then
    VERDICT="FAIL"
  elif echo "$LINE" | grep -Eiq 'BLOCKED'; then
    VERDICT="BLOCKED"
  fi
fi

echo
echo "gate file: ${GATE_FILE:-none}"
echo "verdict:   $VERDICT"

if [[ "$REPORTS_ONLY" -eq 1 ]]; then
  echo
  echo "RESULT: REPORTS_ONLY (code not fetched)"
  echo "  Review: $REPORT_DIR/"
  exit 0
fi

echo
echo "=== cloud_pull phase 2: code ==="

ALLOW_CODE=0
if [[ "$FORCE_CODE" -eq 1 ]]; then
  ALLOW_CODE=1
  echo "forced: checking out full branch despite verdict=$VERDICT"
elif [[ "$VERDICT" == "PASS" || "$VERDICT" == "PASS_WITH_WARNINGS" ]]; then
  ALLOW_CODE=1
elif [[ -f "$REPORT_DIR/BLOCKED.md" ]] || [[ "$VERDICT" == "BLOCKED" ]]; then
  echo "RESULT: BLOCKED — code NOT checked out"
  echo "  Read: $REPORT_DIR/BLOCKED.md (or gate)"
  exit 3
elif [[ "$VERDICT" == "FAIL" ]]; then
  echo "RESULT: FAIL — code NOT checked out"
  echo "  Review gate, fix via new cloud run, or re-run with --force-code"
  exit 4
else
  echo "RESULT: UNKNOWN verdict — code NOT checked out"
  echo "  Open $GATE_FILE and check ## Verdict, or use --force-code"
  exit 5
fi

if [[ "$ALLOW_CODE" -eq 1 ]]; then
  CURRENT="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$CURRENT" != "$BRANCH" ]]; then
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git checkout "$BRANCH"
    else
      git checkout -b "$BRANCH" "origin/$BRANCH"
    fi
  fi
  git pull --ff-only origin "$BRANCH"

  # Re-copy reports after full checkout (source of truth)
  shopt -s nullglob
  for f in cloud_out/gate_*.md cloud_out/run_meta.json cloud_out/BLOCKED.md; do
    [[ -e "$f" ]] || continue
    cp -f "$f" "$REPORT_DIR/"
  done
  shopt -u nullglob

  python3 - <<PY
import json, pathlib
p = pathlib.Path("$REPORT_DIR/manifest.json")
data = json.loads(p.read_text())
data["phase"] = "code"
data["verdict"] = "$VERDICT"
p.write_text(json.dumps(data, indent=2) + "\n")
PY

  echo "- ${PULLED_AT} pull-code ${STAGE_ID} ${BRANCH} ${SHORT} ${VERDICT}" >> "$LOG"

  echo
  echo "RESULT: OK (reports + code)"
  echo "  Branch:  $BRANCH @ $SHORT"
  echo "  Reports: $REPORT_DIR/"
  echo "  Next:    ./scripts/cloud_pr.sh   # draft PR"
  echo "           then human gate / merge"
fi
