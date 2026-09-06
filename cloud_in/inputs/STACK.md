# Frozen demo stack (distilled for cloud)

Source: research closed stages. Cloud agents must not reopen bakeoffs or browse
`docs/research_results/`. If this file and a contract disagree, contracts win for
schemas; this file wins for which engine to implement.

| Layer | Use in demo | Do not use |
|---|---|---|
| Loudness | 16 kHz mono → `normalized.wav` (+ linear gain if RMS < −30 dBFS); VAD path = raw `vad_input.wav` (no dynaudnorm) | denoise / afftdn / DeepFilterNet / RNNoise; file-level dynaudnorm C3 |
| VAD | Silero ONNX (snakers4 + context); thr 0.45 / neg 0.30; `min_speech_ms=200`; `min_silence_ms=350`; TEN hole-fill **off** | FSMN as primary; deepghs ONNX fork |
| Diarization | WeSpeaker on `normalized.wav`; premerge ≤0.5 s; same-speaker gap ≤0.3 s; absorb <1.0 s | pyannote 3.1, sherpa-full; merge agg 0.8/2.5 |
| ASR | GigaAM `v3_rnnt` (CPU torch); ≤25 s splits; per-turn linear gain on slices | Whisper family, Podlodka |
| Terms | suggestions only; never rewrite transcript | silent auto-replace |
| Chunking | packing C + `rubert-tiny2` threshold 0.70; speaker packing gap ≤2 s; pack target ~40–80 words; merge cap 180 s; absorb chapters &lt;5 s into neighbour | late chunking Jina (D), hybrid C→D, pairwise LLM (B) |
| Titles | `llm.tasks.chapter_titles` (`prompts/chapter_titles/v1.md`), ≤10 words, no stamp phrases | prompt P2 |
| Insights / report | `meeting_insights.extract` per chapter, then `meeting_insights.report` once | inventing timestamps; 3c “no insights” bakeoff |
| LLM (cloud / demo) | `llm.mode: api`, `llm.backend: gemini`; NVIDIA/Qwen are config backends | local GGUF / llama.cpp in cloud; audio to API |
| Timecodes | copy from ASR segment bounds only | LLM-generated times |

Chapter density target: 0.4–0.8 chapters/min; prefer 45–180 s chapters (warnings, not hard law).

## Stage D3 pack note

Primary input is **text**: packed `transcript.json` + `chapters.json` (D2 HUMAN_GATE PASS).
Do **not** re-run ASR or chunking. Do not expect packed audio or GGUF.

Provenance note: full-meeting ASR text is a working hypothesis, not gold.
Cloud gates never use `eval/`.
