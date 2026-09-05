# Coder instructions — stage D1 (voice → transcript)

Status precondition: `agent_docs/progress/stage_D1.md` contains `INSTRUCTIONS_READY`.
Contracts: [`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md),
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md),
[`../contracts/config_profiles.md`](../contracts/config_profiles.md),
[`../contracts/quality_gates.md`](../contracts/quality_gates.md) (gate G1).
Plan: [`../plans/draft_D1_scope.md`](../plans/draft_D1_scope.md).

Goal: implement the speech chain for profile `demo` and produce a **full-meeting transcript**
from the packed `voice_002.m4a` (~24.5 min). Do not invent behaviour outside the contracts.
Ambiguity → `cloud_out/BLOCKED.md` and stop.

D0 skeleton already exists on this branch base (`main`). Extend it — do not rewrite the
skeleton from scratch.

## Scope

Write / modify only these paths (create files that do not exist yet):

```
pyproject.toml                          # fill optional groups asr + diarize; add approved deps
uv.lock                                 # via uv add / uv sync only
config/demo.yaml                        # only if a missing key is required by contracts (prefer no change)
src/transcriber/audio/normalize.py
src/transcriber/audio/gain.py
src/transcriber/vad/silero.py
src/transcriber/vad/disabled.py         # pass-through single region (dev key; optional for D1)
src/transcriber/diarization/wespeaker.py
src/transcriber/diarization/merge.py    # same-speaker gap + absorb short turns
src/transcriber/asr/gigaam.py
src/transcriber/asr/splitter.py         # time-only split ≤ max_segment_seconds
src/transcriber/asr/holes.py            # record holes ≥ min_hole_sec
src/transcriber/asr/subprocess_runner.py  # ASR in child process when asr.subprocess=true
src/transcriber/correction/dictionary_suggest.py
src/transcriber/quality/ru_ratio.py     # extend if needed
src/transcriber/quality/checks.py       # G1 check helpers → QualityArtifact
src/transcriber/quality/__main__.py     # `python -m transcriber.quality check-transcript …`
src/transcriber/pipeline/steps.py       # wire real run() for normalize…correction_suggest
src/transcriber/pipeline/orchestrator.py  # run_job / run_stage through real steps
src/transcriber/registry.py             # real factories for D1 engines; keep later-stage stubs
src/transcriber/cli.py                  # add `run` and `quality` (or quality via -m)
src/transcriber/web/health.py           # report model/onnx readiness when weights present (no ASR)
```

Do not create `tests/` (owned by @Tester). Do not touch `docs/`, `agent_docs/contracts/`,
`eval/`, `data/`, `.env`, `.cursor/`. Do not implement chunking, LLM titles/insights, or the
upload UI.

## Approved dependencies (user-approved for D1)

Add via `uv add` / optional groups only (tooling.mdc). Exact pins may float to latest compatible;
record versions in `cloud_out/run_meta.json`.

| Package | Group / note |
|---|---|
| `onnxruntime` | diarize / core ONNX |
| `soundfile` | wav I/O |
| `scikit-learn` | WeSpeaker clustering |
| `torch` (CPU wheel) | ASR runtime only |
| `torchaudio` (CPU) | GigaAM dependency |
| `gigaam` | install from git: `git+https://github.com/salute-developers/GigaAM.git` (research: PyPI lacks 0.2) |
| `speakeronnx` | WeSpeaker ResNet34-LM wrapper (research used `speakeronnx` + `wespeaker-resnet34`) |

Do **not** add: `pyannote`, Whisper packages, `transformers` for ASR, `llama-cpp-python`,
`ten-vad` (fallback stays stub / unused under `demo` with `vad.fallback: disabled`).

Model weights go under `models/` (gitignored). Download with `HF_TOKEN` when required. Prefer
HuggingFace ids used in research: Silero VAD ONNX, `Wespeaker/wespeaker-voxceleb-resnet34-LM`
(or the `speakeronnx` default), GigaAM `v3_rnnt` via `gigaam.load_model`.

## Steps

1. **Preflight.** Confirm every input listed in `cloud_in/prompt.md`. Missing →
   `cloud_out/BLOCKED.md`, stop. Record host inventory into `run_meta.json` early.

2. **Dependencies.** `uv add` the approved set into the appropriate optional groups
   (`asr`, `diarize`) and/or main deps as needed so `uv sync --extra asr --extra diarize`
   (or equivalent documented in the gate) installs a runnable environment. Prefer isolating
   torch so the web process does not need it at import time.

3. **Normalize + gain (`audio/`).** ffmpeg → 16 kHz mono WAV. Measure RMS/peak (e.g. `astats`).
   Apply linear `volume=` **only** when `rms_dbfs < gain_rms_threshold_dbfs`;
   `gain_db = min(target - rms, max_gain)` and clamp so `peak + gain <= gain_peak_ceiling_dbfs`.
   No denoise, no dynamic filters. Write `audio.json` + `normalized.wav` in the job dir.

4. **VAD (`vad/silero.py`).** Silero ONNX. Emit `speech.json` with `regions`, `speech_sec`,
   `detector=silero`, `fallback_used=false`. Read thresholds from config (`min_speech_ms`).
   Do not enable TEN under profile `demo`.

5. **Diarization + merge.** WeSpeaker ONNX embeddings + clustering on speech regions.
   Merge order fixed (contract / research): join same-speaker gaps
   `<= merge_same_speaker_gap_sec`, then absorb turns `< absorb_turn_shorter_than_sec`.
   Record holes `>= min_hole_sec` in `turns.json`. Speakers labelled `SPEAKER_00`, …

6. **ASR (`asr/`).** GigaAM `v3_rnnt`, CPU, `fp16_encoder=False`. When
   `asr.subprocess=true`, run recognition in a **child process** and release memory after.
   Split turns longer than `max_segment_seconds` on the **time axis only**, re-extract audio
   per slice. Map each segment to `id=s0001…`, `turn_id`, `speaker`, `text`, `empty`, `gain_db`.
   Copy holes into `transcript.json`. Never invent text for holes.

7. **Correction.** `dictionary_suggest` with an **empty** base dictionary: write
   `suggestions.json` with `dictionaries=[]`, `suggestions=[]`, `applied=false`. Never rewrite
   `transcript.json`.

8. **Pipeline wiring.** Replace D0 `StageNotImplementedError` stubs for
   `normalize`, `vad`, `diarize`, `asr`, `correction_suggest` with real `run()` implementations
   that build components via the registry (except normalize, which has no registry key — call
   the normalizer directly). Later stages stay `StageNotImplementedError`.
   Add `run_job(job_dir, until="correction_suggest")` that skips stages whose `produces` already
   validates (resumable).

9. **Registry.** Replace stub factories for `silero`, `wespeaker_onnx`, `gigaam_v3_rnnt`,
   `dictionary_suggest` with real constructors. Keep all other keys as stubs /
   `ComponentUnavailableError` per profile table. Unknown keys still raise `UnknownComponentError`.

10. **Quality library + CLI.** Extend checks to build `QualityArtifact` for G1.1–G1.6 from a
    transcript (+ audio duration). Expose:
    - `python -m transcriber.quality check-transcript <transcript.json> [--audio-duration SEC] [--out quality.json]`
    - `transcriber run --job <dir> --audio <path> [--until correction_suggest]`
    Existing `plan` / `validate` / `probe-audio` / `healthcheck` / `convert-legacy` must keep working.

11. **Full-meeting run (required deliverable).** Create a job dir (e.g. under `var/jobs/voice_002/`
    during the run), execute the chain on
    `cloud_in/inputs/audio/voice_002.m4a`, then **copy** the resulting artifacts to
    `cloud_out/artifacts/voice_002/` at least:
    `audio.json`, `speech.json`, `turns.json`, `transcript.json`, `quality.json`,
    `suggestions.json` (and the normalized wav only if size stays reasonable; otherwise omit wav
    from `cloud_out` and note the job path in the gate). Record wall time and peak RSS per stage
    in `run_meta.json` / gate.

12. **Short clip (optional within ASR budget).** May run `test_voice.m4a` for a fast smoke; total
    ASR runs ≤ 3 including the required full meeting (budget in `AGENTS.md`).

13. **Verify:**

    ```
    uv sync --extra asr --extra diarize   # or the install line you document
    uv run ruff check src/
    uv run mypy src/
    uv run bandit -r src/ -ll
    uv run pytest tests/ -v
    uv run transcriber run --job var/jobs/voice_002 --audio cloud_in/inputs/audio/voice_002.m4a
    uv run python -m transcriber.quality check-transcript \
        cloud_out/artifacts/voice_002/transcript.json --out cloud_out/artifacts/voice_002/quality.json
    ```

14. **Gate report.** Write `cloud_out/gate_D1.md` (G1.0–G1.7) and finish `run_meta.json`.
    G1.7: quote 3–5 short Russian fragments from the full transcript and judge coherence.
    Append to `agent_docs/progress/stage_D1.md`:

    ```
    ## YYYY-MM-DD — Coder
    - STATUS: READY_FOR_TEST
    - Files: <paths>
    - Verified: <commands and exit codes>
    - Full meeting artifacts: cloud_out/artifacts/voice_002/
    ```

    After @Tester passes: commit and **push** branch `cursor/demo-d1-speech`. Do **not** open a PR.

## Acceptance criteria

- Full packed meeting yields valid `transcript.json` with Russian speech; G1.1–G1.6 pass (or honest FAIL).
- Latin characters in segment text == 0 (G1.2).
- `suggestions.json` exists with `applied=false`; transcript unchanged by correction.
- ASR torch lives only in a subprocess when `asr.subprocess=true`.
- All thresholds from config; no magic numbers in `src/`.
- `ruff` / `mypy` / `bandit` exit 0; D0 tests still pass; new D1 unit tests (from @Tester) pass without network when marked appropriately.
- Chunk/LLM/web-upload stages remain unimplemented.

## Notes

Docstrings on public APIs in Russian; comments and commit messages in English; user summary in
Russian. Never read `eval/` or `.env`. Never send audio to an API.
