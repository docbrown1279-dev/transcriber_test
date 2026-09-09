#!/usr/bin/env bash
# Run on the deploy host from the repo root (after git pull).
# Secrets: host .env next to compose.yaml (scp once; not managed by this script).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f compose.yaml ]]; then
  echo "compose.yaml not found in ${ROOT}" >&2
  exit 1
fi

echo "compose up --build in ${ROOT}"
docker compose up -d --build

PORT="${TRANSCRIBER_PUBLISH_PORT:-8000}"
echo "waiting for healthz on :${PORT}"
for _ in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "healthz ok"
    docker compose ps
    exit 0
  fi
  sleep 2
done

echo "healthz failed after wait" >&2
docker compose ps >&2 || true
docker compose logs --tail=80 transcriber >&2 || true
exit 1
