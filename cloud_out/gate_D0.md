# Gate D0 — application skeleton, ports and stubs

## Verdict: PASS

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| G0.0 | Preflight: role files, prompt, packed inputs | all present | all present | PASS |
| G0.1 | `uv run pytest tests/ -v` | 27 passed | exit 0 | PASS |
| G0.2 | `ruff` / `mypy` / `bandit` | all exit 0 | exit 0 each | PASS |
| G0.3 | Registry contains every contract key | 21/21 registered | all present | PASS |
| G0.4 | Prod-only keys raise `ComponentUnavailableError` under `demo` | verified | all | PASS |
| G0.5 | `transcriber plan` resolves stage graph | 9 stages in contract order | exit 0 | PASS |
| G0.6 | `transcriber validate` accepts converted fixtures and rejects corrupt copy | verified | exit 0 | PASS |
| G0.7 | `GET /healthz` reports startup self-check, ffprobe on `test_voice.m4a` (83.0 s) | 200 OK (duration 83.0 s) | 200 OK | PASS |

## Agent judgement

The stage D0 goal was to build a clean, robust, and fully-specified application skeleton without implementing any heavy model-backed stages (ASR, VAD, diarization, LLM). All requirements have been implemented and verified:
- Pydantic models for all 10 artifacts are defined with strict bounds and time monotonicity checks (`end > start`, non-negative timestamps, non-empty source references).
- The legacy converter successfully parses research transcripts (`baseline_transformers.json` and `baseline_ninth.json`) into canonical `TranscriptArtifact` instances without altering source files.
- The registry explicitly accounts for all 21 swappable components across 8 areas. Prod-only components properly raise `ComponentUnavailableError` with actionable hints, and demo components slated for later stages raise `StageNotImplementedError`.
- The CLI provides `plan`, `validate`, `convert-legacy`, `probe-audio`, and `healthcheck` utilities.
- The FastAPI `/healthz` endpoint correctly inspects config validity, component registry, storage root permissions, system utilities (`ffmpeg`, `ffprobe`), required environment variables (`JOB_IP_SALT`), and runs smoke ffprobe on the packed audio sample.

## Environment

- Host: Linux 6.12.94+ (4 vCPUs, 15 GiB RAM, 254 GiB disk)
- Python: 3.12.3
- uv: 0.12.10
- ffmpeg / ffprobe: 6.1.1-3ubuntu5
- Key packages: fastapi 0.141.1, pydantic 2.13.5, typer 0.27.2, pyyaml 6.0.3, pytest 9.1.1, ruff 0.16.6, mypy 2.3.1, bandit 1.9.4
- LLM calls: 0 (stage D0 is model-free)
- Wall time: ~10 minutes
- Peak RSS: < 150 MiB

## Deviations and blockers

None. All preflight inputs, contract specifications, and quality gate checks passed without deviations.
