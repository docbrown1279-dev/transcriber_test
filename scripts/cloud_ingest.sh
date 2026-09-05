#!/usr/bin/env bash
# Pull handoff branch and copy cloud_out reports into agent_docs/reports/{stage}/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH=""
KEEP_OUT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --keep-out) KEEP_OUT=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--branch NAME] [--keep-out]"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

HANDOFF="cloud_in/HANDOFF.md"
STAGE_ID="$(grep -Eo 'D[0-9]+' "$HANDOFF" 2>/dev/null | head -1 || echo D0)"
if [[ -z "$BRANCH" ]]; then
  BRANCH="$(grep -E '^\| Branch' "$HANDOFF" | head -1 | sed -E 's/.*`([^`]+)`.*/\1/' || true)"
  if [[ -z "${BRANCH}" ]]; then
    BRANCH="$(grep -Eo 'cursor/[A-Za-z0-9._-]+' "$HANDOFF" | head -1)"
  fi
fi
if [[ -z "${BRANCH}" ]]; then
  echo "FAIL: pass --branch or set Branch in cloud_in/HANDOFF.md"
  exit 1
fi

echo "Fetching origin/$BRANCH …"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

COMMIT="$(git rev-parse HEAD)"
SHORT="$(git rev-parse --short HEAD)"
PULLED_AT="$(date -Iseconds)"

REPORT_DIR="agent_docs/reports/${STAGE_ID}"
mkdir -p "$REPORT_DIR" agent_docs/progress

COPIED=0
for pattern in cloud_out/gate_*.md cloud_out/run_meta.json cloud_out/BLOCKED.md; do
  for f in $pattern; do
    [[ -e "$f" ]] || continue
    cp -f "$f" "$REPORT_DIR/"
    echo "copied $f → $REPORT_DIR/"
    COPIED=1
  done
done

if [[ "$COPIED" -eq 0 ]]; then
  echo "WARN: no gate_*.md / run_meta.json / BLOCKED.md in cloud_out/"
  echo "      Has the cloud agent finished and pushed?"
  ls -la cloud_out/ || true
fi

cat > "$REPORT_DIR/manifest.json" <<EOF
{
  "stage": "${STAGE_ID}",
  "branch": "${BRANCH}",
  "commit": "${COMMIT}",
  "pulled_at": "${PULLED_AT}",
  "source": "cloud_out"
}
EOF
echo "wrote $REPORT_DIR/manifest.json"

mkdir -p agent_docs/progress
LOG="agent_docs/progress/log.md"
if [[ ! -f "$LOG" ]]; then
  printf '# Progress log (append-only)\n\n' > "$LOG"
fi
echo "- ${PULLED_AT} pull ${STAGE_ID} ${BRANCH} ${SHORT}" >> "$LOG"

if [[ "$KEEP_OUT" -eq 0 ]]; then
  find cloud_out -mindepth 1 ! -name '.gitkeep' -exec rm -f {} + 2>/dev/null || true
  touch cloud_out/.gitkeep
  echo "cleared cloud_out/ (use --keep-out to retain)"
fi

echo
echo "Ingest done."
echo "  Report: $REPORT_DIR/"
echo "  Next:   ./scripts/cloud_pr.sh"
echo "  Then:   review gate + PR; run human gate; merge when ready."
