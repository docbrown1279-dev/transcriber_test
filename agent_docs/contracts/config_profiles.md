# Contract: configuration and profiles

Draft updated for layered configs (`base.yaml` + `profiles/{demo,dev,prod}.yaml`).
Profile is selected with `APP_PROFILE` (`dev | demo | prod`); default is `demo`.

## 1. Rules

- Every threshold used by code lives here — no literals in `src/` (backend rule 3).
- Secrets never appear in yaml. Only names of environment variables may be referenced.
- Unknown keys fail validation loudly at startup (pydantic `extra="forbid"`).
- `prod`-only components are valid config values, but selecting them under `demo` raises
  `ComponentUnavailableError` at startup, not mid-job.
- Load order: `config/base.yaml` ← deep-merge `config/profiles/{profile}.yaml` → `AppConfig`.

## 2. Layout

```text
config/
  base.yaml                      # shared speech + chunking + runtime defaults
  profiles/
    demo.yaml                    # demo deltas only
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
| `APP_PROFILE` | config loader | yes (default `demo`) | yes |
| `GEMINI_API_KEY` | `llm.provider: gemini` | yes | yes |
| `HF_TOKEN` | model download at environment setup | build/setup time only | yes |
| `JOB_IP_SALT` | hashing client IP for per-IP limits | yes | yes |
| `TRANSCRIBER_FIXTURES_DIR` | tests, default `cloud_in/inputs/` | no | yes |
| `QWEN_API_KEY` / `OPENAI_API_KEY` | `llm.provider: openai_compat` | no | **no — stays local** |

## 6. Startup self-check

On boot the app validates: config schema, registry keys available for the profile, ffmpeg present,
model files present (or downloadable), storage writable, required env vars set.
