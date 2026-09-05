#!/usr/bin/env bash
# Print cloud pack status; exit 1 if required files missing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HANDOFF="cloud_in/HANDOFF.md"
if [[ ! -f "$HANDOFF" ]]; then
  echo "FAIL: missing $HANDOFF"
  exit 1
fi

STAGE="$(grep -E 'CURRENT stage' "$HANDOFF" | head -1 | sed -E 's/.*\*\*([^*]+)\*\*.*/\1/' | xargs || true)"
BRANCH="$(grep -E '^\| Branch' "$HANDOFF" | head -1 | sed -E 's/.*`([^`]+)`.*/\1/' || true)"
if [[ -z "${BRANCH}" ]]; then
  BRANCH="$(grep -Eo 'cursor/[A-Za-z0-9._-]+' "$HANDOFF" | head -1 || true)"
fi

echo "=== cloud pack status ==="
echo "stage:  ${STAGE:-unknown}"
echo "branch: ${BRANCH:-unknown}"
echo "git:    $(git rev-parse --abbrev-ref HEAD 2>/dev/null) @ $(git rev-parse --short HEAD 2>/dev/null)"
echo

REQUIRED=(
  cloud_in/HANDOFF.md
  cloud_in/prompt.md
  cloud_in/agent/AGENTS.md
  cloud_in/agent/rules.md
  cloud_in/inputs/STACK.md
)

MISSING=0
echo "required:"
for f in "${REQUIRED[@]}"; do
  if [[ -f "$f" ]]; then
    printf "  OK   %s\n" "$f"
  else
    printf "  MISS %s\n" "$f"
    MISSING=1
  fi
done

# Inputs listed in prompt.md as cloud_in/inputs/...
echo
echo "inputs mentioned in prompt.md:"
if [[ -f cloud_in/prompt.md ]]; then
  mapfile -t INPUTS < <(grep -Eo 'cloud_in/inputs/[^|` ]+' cloud_in/prompt.md | sed 's/[|`].*//' | sort -u || true)
  if [[ ${#INPUTS[@]} -eq 0 ]]; then
    echo "  (none parsed)"
  else
    for f in "${INPUTS[@]}"; do
      if [[ -e "$f" ]]; then
        printf "  OK   %s (%s)\n" "$f" "$(du -h "$f" | cut -f1)"
      else
        printf "  MISS %s\n" "$f"
        MISSING=1
      fi
    done
  fi
fi

echo
echo "cloud_out:"
if compgen -G "cloud_out/gate_*.md" >/dev/null || compgen -G "cloud_out/BLOCKED.md" >/dev/null; then
  ls -la cloud_out/ | sed 's/^/  /'
else
  echo "  (empty — waiting for cloud agent)"
fi

echo
if [[ "$MISSING" -ne 0 ]]; then
  echo "RESULT: FAIL (pack incomplete)"
  exit 1
fi
echo "RESULT: OK"
exit 0
