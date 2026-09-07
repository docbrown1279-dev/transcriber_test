# D5 Phase 1 — image build + in-container tests

Date: 2026-09-07  
Host secrets: `var/secrets/transcriber.env` (gitignored; values never logged)  
Images: `transcriber:runtime`, `transcriber:test`

## Commands and exit codes

| Step | Command | Exit |
|---|---|---|
| `[D5-BUILD-01]` | `docker build --target runtime -t transcriber:runtime .` | **0** |
| `[D5-BUILD-02]` | `docker build --target test -t transcriber:test .` | **0** |
| `[D5-CTX-01]` | `docker run --rm --entrypoint ls transcriber:test -la /app/data/test_voice.m4a` | **0** (739210 bytes) |
| `[D5-TEST-*]` first | `docker run --rm --cpus=2 --memory=8g … transcriber:test` | **1** (2 failed — see below) |
| Test image rebuild | `docker build --target test -t transcriber:test .` (after Tester test fixes) | **0** |
| `[D5-TEST-*]` final | same `docker run … transcriber:test` | **0** |
| `[D5-HEALTH-01]` | runtime `GET /healthz` on `:18000` with secrets volume | **200** |
| `[D5-SEC-01]` | docker logs + report scrub for secret **values** | no value leaks |

Exact test run (Coder handoff shape):

```bash
HOST_SECRETS="$PWD/var/secrets/transcriber.env"
docker run --rm --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/agent_docs/reports:/app/agent_docs/reports" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  transcriber:test
```

## Pytest summary (final baked image)

- **84 passed**, 3 skipped, 0 failed (~219 s)
- Soft regression `[D5-TEST-02]`: `test_reg_voice_pipeline_soft` **PASSED** (WARN path; `REGRESSION_STRICT` unset)
- Skips: packed-fixture / probe paths not present in image (expected)

Artifacts: `pytest_container.log` (first), `pytest_container_final.log` (green), `pytest_rerun_fixed.log`

## First-run failures → Tester container-path fixes

| Test | Cause | Fix (tests only) |
|---|---|---|
| `test_d0_hlt_02_healthz_broken_component_returns_503` | With `TRANSCRIBER_DOTENV` mounted, dotenv refilled `JOB_IP_SALT` after `delenv` → 200 instead of 503 | Clear `TRANSCRIBER_DOTENV` in that case (`tests/unit/test_health.py`) |
| `test_d3_cfg_05_dotenv_fills_missing_env_only` | Hardcoded host path `/work/speech_rec_test/config` missing in image | Resolve config via `Path(__file__).parents[2] / "config"` (`tests/unit/test_llm_config.py`) |

Re-run of those two with mounted/rebuilt tests: **PASS**. Full suite after rebuild: **PASS**.

## Healthz / secrets

- Dotenv load logs **key names only**: `JOB_IP_SALT`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `QWEN_API_KEY`, `HF_TOKEN`
- Scrub check against host secrets file: **no values** in docker logs or pytest logs
- Response saved (structure only): `healthz_response.json` — `status=healthy`, components ok

## Notes

- Docker must use host/`all` permissions (sandbox cannot reach `docker.sock`)
- Pytest cache warnings under `/app/.pytest_cache` (permission) — non-blocking
- Soft regression report path: `agent_docs/reports/regression_test_voice.md` (host mount)
