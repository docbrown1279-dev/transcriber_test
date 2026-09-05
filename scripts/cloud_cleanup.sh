#!/usr/bin/env bash
# After merge: archive prompt and clear heavy cloud_in/inputs (keep agent/ role).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAGE_ID="$(grep -Eo 'D[0-9]+' cloud_in/HANDOFF.md 2>/dev/null | head -1 || echo D0)"
DATE="$(date +%Y-%m-%d)"
mkdir -p prompts

if [[ -f cloud_in/prompt.md ]]; then
  cp -f cloud_in/prompt.md "prompts/${STAGE_ID}_${DATE}_closed.md"
  echo "archived → prompts/${STAGE_ID}_${DATE}_closed.md"
fi

# Remove heavy inputs; keep STACK.md optional wipe
if [[ -d cloud_in/inputs/audio ]]; then
  mkdir -p .trash/cloud_in_inputs_"${DATE}"
  mv cloud_in/inputs/audio .trash/cloud_in_inputs_"${DATE}"/ 2>/dev/null || true
  echo "moved inputs/audio → .trash/"
fi
if [[ -d cloud_in/inputs/artifacts ]]; then
  mkdir -p .trash/cloud_in_inputs_"${DATE}"
  mv cloud_in/inputs/artifacts .trash/cloud_in_inputs_"${DATE}"/ 2>/dev/null || true
  echo "moved inputs/artifacts → .trash/"
fi

find cloud_out -mindepth 1 ! -name '.gitkeep' -exec rm -f {} + 2>/dev/null || true
touch cloud_out/.gitkeep

echo "Kept: cloud_in/agent/, cloud_in/HANDOFF.md, cloud_in/prompt.md, inputs/STACK.md (if present)"
echo "Ready for next stage pack (rewrite prompt.md + inputs)."
echo "Append closed line to agent_docs/progress/log.md manually or via planner."
