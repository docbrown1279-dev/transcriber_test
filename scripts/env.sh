#!/usr/bin/env bash
# Activate venv and map HF token from Cursor secret alias without printing values.
ROOT="/workspace"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
if [[ -z "${HF_TOKEN:-}" && -n "${hugging_face:-}" ]]; then
  export HF_TOKEN="$hugging_face"
fi
if [[ -z "${HUGGING_FACE_HUB_TOKEN:-}" && -n "${HF_TOKEN:-}" ]]; then
  export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
fi
