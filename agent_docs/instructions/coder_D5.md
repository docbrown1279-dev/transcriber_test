# Coder instructions — stage D5 (Docker image + test target)

Status precondition: user ✅ on D5 plan rev2.  
Plan: [`../plans/draft_D5_scope.md`](../plans/draft_D5_scope.md).  
Contract: [`../contracts/docker_runtime.md`](../contracts/docker_runtime.md).  
Tester: [`tester_D5.md`](tester_D5.md).

Write scope: repo root `Dockerfile`, `.dockerignore`, minimal `src/` / `scripts/` glue for Docker secrets path + report path, optional `scripts/bench_d5.py` (thin wrapper over D4.1 bench).  
Do **not** edit `tests/` (Tester), `docs/`, Planner progress.  
Do **not** add GitHub Actions (D5.1). Do **not** add Compose unless user asks.  
Do **not** install new packages without approval. No secrets in layers or logs.

## Goal

1. Multi-stage **Dockerfile**: `builder` → `runtime` (serve) and `test` (pytest in container).
2. **`.dockerignore`**: lean context; keep `data/test_voice.m4a`; ignore rest of `data/`.
3. Secrets only via volume / host env-file (see contract).
4. Document build/run commands for Tester (README snippet OK; primary doc is `manuals/docker.md` if Planner already added it — else add short section there).

## Explicit non-goals

- GitHub Actions / CI workflow files (D5.1).
- Full 24‑min meeting as required gate input.
- GPU, k8s, required Compose.
- Changing ASR/diarization/UI behaviour beyond Docker host bind (`0.0.0.0`).

## Dockerfile requirements

- Base: Python **3.12** slim (or uv-provided image); install **ffmpeg**.
- Use **uv** with `uv.lock` (`uv sync --frozen`); extras needed for demo: `asr`, `diarize`, `embed`, `llm`; for `test` target also `dependency-groups.dev`.
- WORKDIR `/app`; copy only allowed context paths.
- **runtime** CMD/ENTRYPOINT:  
  `transcriber serve --host 0.0.0.0 --port 8000`  
  (CLI defaults to `127.0.0.1` — override explicitly).
- `HEALTHCHECK` → `GET http://127.0.0.1:8000/healthz` (curl/wget or python one-liner).
- Non-root user; writable dirs for `storage_root` and caches (chown or `/tmp`-style volumes).
- **test** target: includes `tests/`, `data/test_voice.m4a`, `tests/fixtures/…`; default CMD runs pytest (see Tester for exact args). Keep image usable as:

```bash
docker build --target test -t transcriber:test .
docker build --target runtime -t transcriber:runtime .
```

## `.dockerignore` (required patterns)

Ignore: `.git`, `.venv`, `var/`, `eval/`, `results/`, `agent_docs/`, `docs/`, `cloud_in/`, `cloud_out/`, `.cursor/`, `.trash/`, `prompts/`, `manuals/`, caches, secret files.

Allow exception:

```dockerignore
data/**
!data/test_voice.m4a
```

Do not ignore: `pyproject.toml`, `uv.lock`, `src/`, `config/`, `models/`, `tests/`, needed `scripts/`.

## Secrets loading (small src change OK)

Current loader looks for dotenv in cwd / repo root only. Extend so a volume works:

1. If env `TRANSCRIBER_DOTENV` is set → load that path first (read-only mount expected: `/run/secrets/transcriber.env`).
2. Keep existing cwd / repo-root dotenv behaviour.
3. Never log secret **values**; only paths and env **names**.

Document both:

- `-v HOST_SECRETS:/run/secrets/transcriber.env:ro -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env`
- and `docker run --env-file HOST_SECRETS` (no code path required).

## Regression report path

`tests/regression/…` writes `agent_docs/reports/regression_test_voice.md` by default — that tree is **not** in the image. Options (pick one, smallest diff):

- Support env `REGRESSION_REPORT_PATH` (Tester mounts `/out` and sets it), **or**
- Write under `/tmp` when `agent_docs/` missing, **or**
- Document mandatory `-v "$PWD/agent_docs/reports:/app/agent_docs/reports"` for test runs.

Prefer env override so Tester can `docker cp` / bind-mount `/out`. If the path lives only in `tests/`, ask Tester to add the env read — do not silently weaken assertions.

## Bench / G5 helper

Reuse `scripts/bench_d4_1.py` or add `scripts/bench_d5.py` that:

- accepts `--audio`, `--mode b|a`, `--out JSON`;
- runs under cgroup limits when Tester wraps with `docker run --cpus=2 --memory=8g`;
- records stages wall + peak RSS (same shape as D4.1).

No need to re-implement pipeline.

## Config note

`app.storage_root` should be overridable for containers (env or existing yaml). Default inside image: e.g. `/var/transcriber` with volume mount. Prefer config/env already used by the app — avoid hardcoding paths in many places.

## Acceptance (Coder → READY_FOR_TEST)

- [ ] `docker build --target runtime` succeeds on a clean context (no secrets in history of layers — spot-check: no secret filenames in `docker history` / build context list).
- [ ] `docker build --target test` succeeds; image contains `data/test_voice.m4a`.
- [ ] `docker run --rm -p 8000:8000 … transcriber:runtime` serves; `/healthz` works with secrets mounted or `--env-file`.
- [ ] Serve binds `0.0.0.0` (reachable from host port map).
- [ ] `.dockerignore` excludes bulky/secret paths; includes `test_voice`.
- [ ] Dotenv volume path via `TRANSCRIBER_DOTENV` works (unit-level or manual smoke).
- [ ] `uv run ruff check src/` / `mypy src/` / `bandit -r src/ -ll` clean for touched Python.
- [ ] Append `READY_FOR_TEST` to `agent_docs/progress/stage_D5.md` with exact build/run commands.

## Handoff

@Tester follows [`tester_D5.md`](tester_D5.md): in-container pytest, then G5 15′ under `--cpus=2 --memory=8g`.
