#!/usr/bin/env bash
# Idempotent bootstrap for the offline transcriber.
# Installs system audio/build tooling and Python dependencies.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Installing system packages (ffmpeg, espeak-ng, build tools)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends \
  python3-venv python3-dev \
  build-essential cmake bison flex \
  ffmpeg espeak-ng

echo "==> Creating Python virtual environment (.venv)"
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

echo "==> Installing Python dependencies"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "==> Verifying transcription stack"
.venv/bin/python - <<'PY'
from pocketsphinx import get_model_path
print("pocketsphinx model:", get_model_path())
PY

echo "==> Install complete"
