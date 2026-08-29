---
name: asr-research
description: Stage 2 — GigaAM v3_rnnt + pyannote + linear gain on the full meeting, one rubert-tiny2 adjacent chunk pass, Qwen3-8B titles if 5–30 chunks. Use when continuing ASR, chunking, meeting chapters, or Stage 2 reports.
---

# ASR Research — Stage 2

## Goal

Full-meeting diarized transcript (GigaAM v3), then adjacent chunks (≤3 size/threshold tries), then short titles if some try is 5–30. No denoise. No ASR fallback. No fourth chunk recipe.

## Resume

Inspect `results/` and branch `cursor/stage1e-four-asr-be20`. 1e is the ASR choice. Do **not** rerun afftdn, WhisperX, or the four-model bakeoff.

## HF access gate (hard stop)

Before pyannote: token present; GET `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` `config.yaml`. Missing token or **401/403** → stop, `results/reports/2/`, `failure_kind: auth`.

## Checklist

```
Stage 2:
- [ ] 0. Inventory + HF preflight (stop on 401/403)
- [ ] 1. Full-file pyannote → table merge → linear gain extracts
- [ ] 2. GigaAM v3_rnnt only (≤25 s time splits); save json+txt
- [ ] 3. Whole speaker turns (~20–50 words); adjacent cosine 0.80; ≤3 size/threshold tries
- [ ] 4. If some try is 5–30 chunks: Qwen3-8B titles ≤10 words; else stop
- [ ] 5. Log embed/LLM seconds; results/reports/2/; commit/push
```

## ASR

1e cut rules. Empty GigaAM stays empty. No Whisper/Podlodka.

## Chunking

- `cointegrated/rubert-tiny2` only.
- Do not split a speaker turn unless it is &gt;~80 words.
- Adjacent merge only. New chunk if gap &gt; 90 s.
- Cosine start **0.80**, unit start **20–50** words. Up to 3 tries: only unit size and threshold. After 3 still outside 5–30 → stop, no Qwen, no fourth recipe.

## Titles

Qwen3-8B GGUF, text-only, only if some chunking try landed in 5–30.

## Stop

Crash/OOM: retry same config ≤2 times. Do not add a second ASR or a second chunk recipe in this run.
