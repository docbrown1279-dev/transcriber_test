
# Contract: configuration and profiles

Draft, Phase A. Structure follows `docs/dev_specs.md` §6–§9 without renaming keys; values below
add only what the research froze (thresholds, merge rules, component keys). Profile is selected
with `APP_PROFILE` (`dev | demo | prod`); the demo build ships `config/demo.yaml` as default.

## 1. Rules

- Every threshold used by code lives here — no literals in `src/` (backend rule 3).
- Secrets never appear in yaml. Only names of environment variables may be referenced.
- Unknown keys fail validation loudly at startup (pydantic `extra="forbid"`), so a typo cannot
  silently disable a limit.
- `prod`-only components are valid config values, but selecting them under `demo` raises
  `ComponentUnavailableError` at startup, not mid-job.

## 2. `config/demo.yaml` (target of stages D0–D5)

```yaml
app:
  profile: demo
  storage_root: ./var            # jobs, uploads, artifacts
  log_level: INFO

audio:
  max_minutes: 15
  max_file_size_mb: 250
  sample_rate: 16000
  channels: 1
  gain_rms_threshold_dbfs: -30.0   # 1e: gain only below this RMS
  gain_target_dbfs: -23.0
  gain_max_db: 18.0
  gain_peak_ceiling_dbfs: -1.0

vad:
  engine: silero                   # registry key
  min_speech_ms: 200
  fallback: disabled               # ten_fallback | disabled (licence, off by default)

diarization:
  engine: wespeaker_onnx
  device: cpu
  onnx_threads: 2                  # demo host is 2-3 vCPU
  merge_same_speaker_gap_sec: 0.3
  absorb_turn_shorter_than_sec: 1.0
  min_hole_sec: 0.5
  vad_premerge_gap_sec: 0.3        # 1f2: glue Silero crumbs before embed windows
  min_embed_sec: 0.4               # 1f2: drop chunks shorter than 0.4 s
  embed_window_sec: 1.5
  embed_step_sec: 0.75
  cluster_distance_threshold: 0.80 # full-meeting; 0.5 oversplits on long audio (see eval/d1/2)

asr:
  engine: gigaam_v3_rnnt
  device: cpu
  max_segment_seconds: 25
  subprocess: true                 # release torch memory after the stage

correction:
  enabled: true
  mode: suggest_only               # demo never rewrites transcript.json
  base_ru_dictionary: true
  domain_dictionary: false
  levenshtein_auto_replace: false
  manual_review: false
  min_confidence: 0.6

chunking:
  default_mode: speaker_similarity     # spec name for research variant C
  chunker: packing_c
  embedding_model: rubert_tiny2
  similarity_threshold: 0.70
  packing_max_gap_sec: 2.0
  target_chapter_sec: [45, 180]
  target_chapters_per_minute: [0.4, 0.8]
  late_chunking:
    enabled: false
    provider: disabled

llm:
  mode: api
  provider: gemini                 # demo and cloud gates use gemini only
  model: gemini-2.5-flash
  api_key_env: GEMINI_API_KEY
  timeout_sec: 60
  max_calls_per_job: 20
  temperature: 0.2
  debug_reasoning: false
  prompts:
    title: title_p1_v1
    extract: extract_v1
    report: report_v1

limits:
  requests_per_ip_per_day: 1
  max_concurrent_jobs: 1
  result_ttl_hours: 24
  queue_max_size: 4

ui:
  type: jinja
  show_progress: true
  progress_transport: polling      # polling | sse
  allow_editing: false
  allow_player: false
  draft_warning: true
```

## 3. `config/dev.yaml` — deltas only

No audio limits (`max_minutes: null`, `max_file_size_mb: null`), `vad.fallback: ten_fallback`
allowed, `diarization.engine` may be `pyannote31`, `chunking.default_mode: both`,
`correction.manual_review: true`, `ui.type: api_only`, `limits.*: null`,
`app.log_level: DEBUG`, artifacts retained.

LLM in `dev` is the local model (human gate on the operator's machine, no API key):

```yaml
llm:
  mode: local
  provider: local_llama
  model_path: ./models/Qwen3-8B-Q5_K_M.gguf
  n_ctx: 8192
  threads: 4
  max_calls_per_job: null
  prompts: {title: title_p1_v1, extract: extract_v1, report: report_v1}
```

Same `prompt_id` values as `demo`, so a local run is directly comparable with the cloud gate.

## 4. `config/prod.yaml` — deltas only

`audio.max_minutes: 120`, `max_file_size_mb: 2000`, `diarization.engine: local_stable`
(→ `pyannote31` or `wespeaker_onnx` per hardware), `correction.domain_dictionary: true` and
`manual_review: true`, `chunking.late_chunking.enabled: optional` with `jina_local`,
`llm.mode: local` with `local_llama`, `limits.max_concurrent_jobs: 2`,
`limits.result_ttl_hours: null`, `ui.type: interactive` with `allow_editing`/`allow_player: true`.
All of these resolve to stubs until a prod stage is planned — the config is the declaration, the
registry decides availability.

## 5. Environment variables

| Variable | Used by | Required in demo | Provisioned in cloud |
|---|---|---|---|
| `APP_PROFILE` | config loader | yes (default `demo`) | yes |
| `GEMINI_API_KEY` | `llm.provider: gemini` | yes | yes |
| `HF_TOKEN` | model download at environment setup | build/setup time only | yes |
| `JOB_IP_SALT` | hashing client IP for per-IP limits | yes | yes |
| `TRANSCRIBER_FIXTURES_DIR` | tests, default `cloud_in/inputs/` | no | yes |
| `QWEN_API_KEY` / `OPENAI_API_KEY` | `llm.provider: openai_compat` | no | **no — stays local** |

Missing a required secret must fail at startup with the variable name — never with a stack trace
containing values, and never by falling back to another provider.

## 6. Startup self-check

On boot the app validates: config schema, registry keys available for the profile, ffmpeg present,
model files present (or downloadable), storage writable, required env vars set. The result is what
`GET /healthz` reports per component; a failed self-check makes `/healthz` return a non-200 status
so the demo host can restart the container.
