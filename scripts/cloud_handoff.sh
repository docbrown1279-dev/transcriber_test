#!/usr/bin/env bash
# Commit + push cloud_in pack on the handoff branch; print Cloud Agent paste prompt.
# Does NOT open a PR (use cloud_pr.sh after ingest).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
MSG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --message) MSG="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--message 'commit msg']"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

./scripts/cloud_status.sh

HANDOFF="cloud_in/HANDOFF.md"
STAGE_ID="$(grep -Eo 'D[0-9]+' "$HANDOFF" | head -1 || echo D0)"
BRANCH="$(grep -E '^\| Branch' "$HANDOFF" | head -1 | sed -E 's/.*`([^`]+)`.*/\1/' || true)"
if [[ -z "${BRANCH}" ]]; then
  BRANCH="$(grep -Eo 'cursor/[A-Za-z0-9._-]+' "$HANDOFF" | head -1)"
fi
if [[ -z "${BRANCH}" ]]; then
  echo "FAIL: cannot parse branch from $HANDOFF"
  exit 1
fi

DATE="$(date +%Y-%m-%d)"
mkdir -p prompts cloud_out
if [[ -f cloud_in/prompt.md ]]; then
  ARCHIVE="prompts/${STAGE_ID}_${DATE}.md"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    cp -f cloud_in/prompt.md "$ARCHIVE"
    echo "archived prompt → $ARCHIVE (local, gitignored)"
  else
    echo "[dry-run] would archive prompt → $ARCHIVE"
  fi
fi

# Clear previous cloud_out contents (keep .gitkeep)
if [[ "$DRY_RUN" -eq 0 ]]; then
  find cloud_out -mindepth 1 ! -name '.gitkeep' -exec rm -f {} + 2>/dev/null || true
  touch cloud_out/.gitkeep
else
  echo "[dry-run] would clear cloud_out/ (keep .gitkeep)"
fi

if [[ -z "$MSG" ]]; then
  MSG="Handoff ${STAGE_ID}: pack cloud_in for ${BRANCH}"
fi

PASTE="$(cat <<EOF
=== WHERE TO RUN THE CLOUD AGENT ===
Branch (select this branch in Cloud Agent / open PR from it):
  ${BRANCH}

Stage:
  ${STAGE_ID}

Full stage prompt (different every stage — do NOT reuse an old one):
  cloud_in/prompt.md

=== PASTE INTO CLOUD AGENT ===
You are on branch ${BRANCH}. Read in order:
1) cloud_in/HANDOFF.md
2) cloud_in/agent/AGENTS.md
3) cloud_in/agent/rules.md
4) cloud_in/prompt.md   ← this stage's task (D0 ≠ D1 ≠ D2…)

Execute cloud_in/prompt.md unattended. Write code to src/ and config/, tests to tests/.
Write reports only to cloud_out/. Commit and push branch ${BRANCH}.
Do NOT open a pull request.
=== END ===
EOF
)"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] would checkout/create branch: $BRANCH"
  echo "[dry-run] would commit: $MSG"
  echo "[dry-run] would push -u origin HEAD"
  echo
  echo "$PASTE"
  exit 0
fi

# Branch
CURRENT="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT" != "$BRANCH" ]]; then
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
  else
    git checkout -b "$BRANCH"
  fi
fi

# Stage relevant paths (never .env / eval gold)
git add -A -- \
  cloud_in \
  cloud_out \
  agent_docs \
  manuals \
  scripts/cloud_*.sh \
  config \
  pyproject.toml \
  src \
  tests \
  .gitignore \
  README.md \
  2>/dev/null || true

# Explicitly avoid secrets if somehow staged
git reset -q -- .env 2>/dev/null || true

if git diff --cached --quiet; then
  echo "Nothing new to commit; pushing branch as-is."
else
  git commit -m "$MSG"
fi

git push -u origin HEAD

echo
echo "Pushed: origin/$BRANCH"
echo
echo "$PASTE"
echo
echo "Next: start Cloud Agent **on branch ${BRANCH}**, paste the block above."
echo "      Stage prompt file: cloud_in/prompt.md (unique per stage)."
echo "When done: ./scripts/cloud_pull.sh && ./scripts/cloud_pr.sh"
