# AGENTS.md — Speech Recognition Research

## Mission

Stage **1b** (current): produce **coherent Russian meeting text with speaker labels** on CPU.  
Do **not** run semantic chunking or meeting summary in this stage. Stage 2 tests remain deferred.

## Role

You are the **Researcher** agent. Read and follow:

1. [`docs/research_plan.md`](docs/research_plan.md) — Stage 1b search tree and quality criterion
2. [`.cursor/skills/asr-research/SKILL.md`](.cursor/skills/asr-research/SKILL.md) — workflow
3. [`docs/schemas/research_report.schema.json`](docs/schemas/research_report.schema.json) — report schema

## Current stage (1b)

| In scope | Out of scope |
|---|---|
| `large-v3` + loudnorm (no compressor) | ffmpeg afftdn/highpass (already rejected) |
| Diarization: WhisperX, else Whisper + pyannote | Chunking / embeddings |
| Meaning check with local **Qwen3-8B** | Full meeting summary |
| Neural denoise (DeepFilterNet, RNNoise) only if meaning fails | Cloud ASR; NeMo |
| Speaker-targeted reprocess if one speaker is clearly worse | Infinite param sweeps |

## Fixtures

| Path | Description |
|---|---|
| `data/fixtures/meeting_sample.m4a` | Example meeting |
| `docs/Голос 002.m4a` | Same file |

Reuse existing Stage 1 artifacts as **baseline only**. Do not treat `faster-whisper medium` as the 1b success path. Do not repeat the completed ffmpeg denoise A/B.

## Credentials

| Secret | Use |
|---|---|
| `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` | **Required** for pyannote / WhisperX. Probe gated files **before** ASR; **401/403 → stop the run** |
| Gemini / NVIDIA | Do not use in 1b unless Qwen3-8B cannot run at all (then ≤1 short text-only meaning check) |

Never print or commit secrets.

## Success criterion

A run is `success` only if **Qwen3-8B meaning check** says the sampled fragments are coherent meeting speech.  
`rw_ratio ≥ 0.9` is optional telemetry, **not** a pass.

Do not close a block as `success` with unusable text. Do not close as `fail` while a listed variant or error-retry remains.

## Hard budgets

Error (crash, OOM, empty/truncated output): retry **same** config up to **2** extra times.  
Quality fail: move to the **next listed** variant. No extra variants.

| Block | Cap |
|---|---|
| ASR + diarization stacks | **3**: WhisperX large-v3 + loudnorm → faster-whisper large-v3 + pyannote → whisper.cpp large + pyannote |
| Loudnorm | **1** ffmpeg `loudnorm` (no `acompressor` / `compand`) |
| Meaning checker | **1** local model: Qwen3-8B. 2–3 random fragments; if diarized, 2–3 **per speaker** |
| Neural denoise libraries | **≤ 2** (DeepFilterNet, RNNoise). ffmpeg skip. |
| Presets per denoise library | default + **≤ 2** tweaks (3 total), then stop that library |
| Speaker-only reprocess | **1** extra pass on the worst speaker if diarization exists and that speaker is clearly worse |
| Package install | **≤ 2** attempts per tool family |
| Agent loops | No full-pipeline restart. No medium-quality victory lap. |

Time wall: if `large-v3` has no usable transcript after **~90 min** or OOM, that stack failed on resources → next stack (whisper.cpp).

## Provenance

- Local Whisper/WhisperX only. No API ASR. No audio to Gemini/NVIDIA.
- Each ASR row: `execution_mode: local`, provider, model, input artifact, diarization method, `meaning_check`, `failure_kind`.
- Resume: inspect `results/` first; do not repeat completed 1a medium/ffmpeg experiments.

## Unattended

Install from `docs/environment.md` without waiting. Commit/push the **working branch** (prefer continuing `cursor/stage1-asr-research-dc41`). No force-push to `main`. Reports in Russian.

## Launch checklist

```
- [ ] Read docs/research_plan.md + this file + skill
- [ ] Resume artifacts; skip completed ffmpeg/medium-as-goal
- [ ] HF gated preflight; **stop** on 401/403
- [ ] loudnorm WAV
- [ ] WhisperX large-v3 + diarization (else fw+pyannote, else whisper.cpp)
- [ ] Qwen3-8B meaning check (per speaker if labels exist)
- [ ] If meaning bad: ≤2 neural denoisers, ≤3 presets each; optional worst-speaker pass
- [ ] `results/reports/1a|1b|1c/` research_report.json + notes.md; chunking/summary skipped
- [ ] Commit/push branch
```
