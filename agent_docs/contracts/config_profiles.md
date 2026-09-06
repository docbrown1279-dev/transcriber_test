# Contract: configuration and profiles

Draft updated for layered configs (`base.yaml` + `profiles/{demo,dev,prod}.yaml`).
Profile is `config/base.yaml` → `app.profile` (`demo` | `dev` | `prod`); default is `demo`.
Optional process override: CLI `--profile` or env `APP_PROFILE`. Do **not** put the profile in `.env`.

## 1. Rules

- Every threshold used by code lives here — no literals in `src/` (backend rule 3).
- Secrets never appear in yaml. Only names of environment variables may be referenced.
- Unknown keys fail validation loudly at startup (pydantic `extra="forbid"`).
- `prod`-only components are valid config values, but selecting them under `demo` raises
  `ComponentUnavailableError` at startup, not mid-job.
- Load order: `config/base.yaml` ← `config/base_llm.yaml` ← `config/profiles/{profile}.yaml`
  → `AppConfig`.
- LLM **prompts** and **schemas** are files under `src/transcriber/llm/{prompts,schemas}/`.
  Paths live in `llm.tasks`. Backends (model id, `api_key_env`, `base_url`) live in
  `llm.backends`. Unique client keys: `extra_config` path on the **backend** or `null`.
  `agent_docs/plans/draft_llm_wrapper.md` and `agent_docs/contracts/llm/base_llm.yaml`.

## 2. Layout

```text
config/
  base.yaml                      # speech + chunking + runtime
  base_llm.yaml                  # mode, backend, base_llm, backends, tasks
  llm_extra/                     # optional unique API keys (not base_url)
  profiles/
    demo.yaml                    # llm.mode: api, llm.backend: qwen; ui.summary_max_calls: 2
    dev.yaml
    prod.yaml
```

## 3. `vad` (must be configurable — no hardcoded Silero thresholds)

```yaml
vad:
  engine: silero
  threshold: 0.5
  neg_threshold: 0.35
  min_speech_ms: 200
  min_silence_ms: 200
  fallback: disabled             # disabled | ten_fallback | fsmn_fallback
```

## 4. Nested speech blocks (keep ≤15 keys per subsection)

See `config/base.yaml`: `audio.gain`, `diarization.merge`, `diarization.embed`.

## 5. Environment variables

| Variable | Used by | Required in demo | Provisioned in cloud |
|---|---|---|---|
| `APP_PROFILE` | optional process override (CLI `--profile`). Not in `.env`. Default: `config/base.yaml` `app.profile` (`demo`) | no | optional |
| `GEMINI_API_KEY` | `llm.backend: gemini` | only if that backend is selected | yes when backend is gemini |
| `NVIDIA_API_KEY` | `llm.backend: nvidia` | only if that backend is selected | optional |
| `QWEN_API_KEY` | `llm.backend: qwen` | yes (demo overlay backend) | yes when backend is qwen |
| `HF_TOKEN` | model download at environment setup | build/setup time only | yes |
| `JOB_IP_SALT` | hashing client IP for per-IP limits | yes | yes |
| `TRANSCRIBER_FIXTURES_DIR` | tests, default `cloud_in/inputs/` | no | yes |

YAML stores the **name** of the key variable (`api_key_env`), never the value. The process reads
the value from the environment or `.env`. Only the active backend’s variable is required.

On-demand UI summary (not the full extract+report job) is capped by `ui.summary_max_calls`
(demo overlay: 2). Full pipeline extract+report still uses `llm.max_calls_per_job`.

## 6. Startup self-check

On boot the app validates: config schema, registry keys available for the profile, ffmpeg present,
model files present (or downloadable), storage writable, required env vars set.
