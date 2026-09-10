# Docker runtime contract (stage D5)

English. Source brief: [`../plans/draft_D5_scope.md`](../plans/draft_D5_scope.md).
Gate ids: G5.* in [`quality_gates.md`](quality_gates.md).

## Images / targets

| Docker target | Purpose | Default command |
|---|---|---|
| `runtime` | Demo web + pipeline | `transcriber serve --host 0.0.0.0 --port 8000` |
| `test` | In-container pytest (unit + soft regression) | `uv run pytest …` (see tester_D5) |

Both share the same frozen deps from `uv.lock`. No GPU. Python 3.12.

## Build context (must be present on build host)

Included:

- `pyproject.toml`, `uv.lock`
- `src/`, `config/`, `tests/`
- `models/` (at least tracked/local Silero ONNX used by demo)
- `data/test_voice.m4a` only (≈724 KiB) for regression
- bench script(s) under `scripts/` needed for G5 (`bench_d4_1.py` and/or `bench_d5.py`)

Excluded via `.dockerignore`: `.git`, `.venv`, `var/`, rest of `data/`, `eval/`, `results/`, `agent_docs/`, `docs/`, `cloud_*`, `.cursor/`, caches, secret files.

Note: root `.gitignore` currently ignores `data/` and `/models/`. Local D5 builds use files on disk. Shipping those two paths in git is **D5.1 / backlog**, not a D5 blocker.

## Secrets

- Never `COPY` secret files into image layers.
- Preferred volume: mount a dotenv file read-only, e.g.  
  `-v /host/path/to/secrets.env:/run/secrets/transcriber.env:ro`  
  App must load it (extend dotenv search via `TRANSCRIBER_DOTENV=/run/secrets/transcriber.env`, and/or mount as `/app/.env:ro`).
- Also allowed: `docker run --env-file /host/path/to/secrets.env` (injects process env; file stays on host).
- Required names (values never logged): `JOB_IP_SALT`; for LLM titles/insights in demo: backend key from config (demo → `QWEN_API_KEY`). Optional: `HF_TOKEN` for Hub downloads.
- Example template only: repo `*.example` secrets template (no real values).

## Volumes (runtime)

| Mount | Role |
|---|---|
| secrets file → `/run/secrets/transcriber.env` or `/app/.env` | API keys / salt |
| model/HF cache (e.g. `/home/app/.cache`) | avoid re-download |
| `storage_root` (e.g. `/var/transcriber`) | jobs / uploads |
| host `agent_docs/reports/d5` or `/out` | write G5 / regression reports out of container |
| host 15‑min audio for G5 | input only |

## Resource gate (G5)

```text
docker run --rm --cpus=2 --memory=8g …
```

- Audio: 15‑minute slice (host path, not baked into image except `test_voice`).
- Pipeline default: `toc_mode=b`.
- Pass: no OOM; per-stage wall + peak RSS report; peak RSS web+ASR `< 7 GiB` (G5.4).
- If wall unacceptable: recommend lowering `audio.max_minutes` to 10.

## Health

- `GET /healthz` → 200 when self-check passes.
- `HEALTHCHECK` in image should hit `/healthz`.
- Serve must bind `0.0.0.0` inside the container (CLI default `127.0.0.1` is wrong for Docker).

## Compose (optional, preferred for local/server run)

Root [`compose.yaml`](../../compose.yaml): build `runtime`, publish `${TRANSCRIBER_PUBLISH_PORT:-8000}:8000`, `cpus: 2` / `mem_limit: 8g`, named volumes for storage + HF cache, `env_file` from host (default `.env`). Secrets never in image layers.

**Rebuild required after `git pull`:** `src/` and `config/` are `COPY`'d into the image, not bind-mounted. `docker compose up -d` / `restart` alone leave the old image. Use `docker compose up -d --build` (or `scripts/deploy_remote.sh`). See [`manuals/docker.md`](../../manuals/docker.md).

## Out of scope here

GPU images. Actions workflow exists (`workflow_dispatch` only); push does not auto-deploy.
