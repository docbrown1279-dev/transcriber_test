---
name: asr-research
description: Runs Stage 1b research for coherent Russian meeting text with diarization (WhisperX/large-v3, loudnorm, Qwen3-8B meaning check, optional neural denoise). Use when continuing ASR research, WhisperX, pyannote, or Stage 1b reports.
---

# ASR Research — Stage 1b

## Goal

Coherent diarized transcript on CPU. No chunking, no summary.

## Resume

Inspect `results/` and branch `cursor/stage1-asr-research-dc41`. Keep 1a artifacts. Do **not** rerun ffmpeg afftdn. Do **not** stop after medium `rw_ratio`.

## HF access gate (hard stop)

Before pip/WhisperX:

1. `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` must exist. Do not print it.
2. GET with the token: `pyannote/speaker-diarization-3.1` `config.yaml`, `pyannote/segmentation-3.0` `config.yaml`, and `pyannote/speaker-diarization-community-1`. Also GET public `Systran/faster-whisper-large-v3` `config.json`.
3. Write `results/asr/hf_access_preflight.json` (HTTP codes, redirect hosts, `token_present`). Never store the token.
4. On missing token or pyannote **401/403**: stop the run. Partial report + `notes.md` (`failure_kind: auth`), commit/push. Do not continue. Human will fix licenses/token.

## Checklist

```
Stage 1b:
- [ ] 0. Inventory + HF access preflight (stop on 401/403)
- [ ] 0b. .venv only if HF gate passed
- [ ] 1. loudnorm (no compressor) → data/processed/
- [ ] 2. WhisperX large-v3 + diarization
- [ ] 2b. If WhisperX fails: faster-whisper large-v3 + pyannote
- [ ] 2c. If large cannot run: whisper.cpp large + pyannote
- [ ] 3. Qwen3-8B meaning check (2–3 random; per speaker if diarized)
- [ ] 4. If meaning bad: DeepFilterNet and/or RNNoise (≤2 libs, ≤3 presets each)
- [ ] 4b. Optional: denoise/re-ASR worst speaker only
- [ ] 5. Report + push
```

## Audio preprocess

One command family, once:

```bash
ffmpeg -y -i data/fixtures/meeting_sample.m4a \
  -af loudnorm=I=-16:TP=-1.5:LRA=11 \
  data/processed/meeting_sample_loudnorm.wav
```

No `acompressor`, `compand`, or ffmpeg denoise here.

## ASR + diarization

All local. No cloud ASR.

1. **WhisperX** `large-v3` on loudnorm WAV; align + diarize (`pyannote` via WhisperX). `HF_TOKEN` required.
2. If install/runtime fail after ≤2 retries: **faster-whisper** `large-v3` on the same WAV, then **pyannote** `speaker-diarization-3.1` (or current 3.x) separately; merge by timestamps.
3. If OOM / ~90 min with no transcript: **whisper.cpp** quantized large + pyannote.

Output under `results/asr/`: json (segments: start, end, text, speaker), txt, diarization sidecar.

## Meaning check (Qwen3-8B)

Not a full summary. Sample fragments only.

- Prompt: the fragment + «Связный текст совещания на русском или бессмыслица из правдоподобных слов? Ответь: ok/bad и одно предложение почему.»
- Save `results/asr/meaning_check_*.json`.
- If diarization exists, sample **2–3 clips per speaker**, not only globally.
- Block `success` iff most sampled clips are `ok`.

If Qwen3-8B cannot run: one optional Gemini **text-only** meaning check on the same clips (≤1 call). Never upload audio.

## Neural denoise (only if meaning is bad)

Skip ffmpeg. At most **DeepFilterNet** and **RNNoise**.

Per library:

1. Default preset → ASR (same stack that produced the text) → meaning check on the **same clip timestamps**.
2. At most two parameter changes. Log what changed (clarity vs robotic vs dropped speech).
3. Stop that library if meaning becomes ok, speech coverage drops a lot, or 3 presets used.

If one speaker is clearly worse: extract that speaker’s intervals, denoise/re-ASR **only those**, merge back. **One** such pass.

## Report

- `results/reports/research_report.json` — schema; put 1b runs in `asr_results` / `denoise_results`.
- `chunking_results` / `llm_summary_results`: `skipped`, notes «1b: text+diarization only».
- `notes.md` in Russian: stacks tried, meaning verdicts per speaker, denoise presets.

## Stop

Budget exhausted → write report with what exists. Do not invent a fourth ASR stack or a third denoise library.
