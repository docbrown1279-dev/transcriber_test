# Frozen demo stack (distilled for cloud)

Source: research closed stages. Cloud agents must not reopen bakeoffs or browse
`docs/research_results/`. If this file and a contract disagree, contracts win for
schemas; this file wins for which engine to implement.

| Layer | Use in demo | Do not use |
|---|---|---|
| Loudness | 16 kHz mono WAV; linear `volume=` only if RMS < −30 dBFS | denoise / afftdn / DeepFilterNet / RNNoise |
| VAD | Silero ONNX; TEN only as optional hole fill, **off by default** | FSMN as primary |
| Diarization | WeSpeaker ResNet34-LM ONNX + cluster; merge gap ≤0.3 s, absorb <1.0 s | pyannote 3.1, sherpa-full |
| ASR | GigaAM `v3_rnnt` (CPU torch runtime); split segments on time to ≤25 s | Whisper family, Podlodka |
| Terms | suggestions only; never rewrite transcript | silent auto-replace |
| Chunking | packing C + `rubert-tiny2` threshold 0.70; speaker packing gap ≤2 s | late chunking Jina (D), hybrid C→D |
| Titles | prompt `title_p1_v1`, ≤10 words, no stamp phrases | prompt P2 |
| Insights / report | extract per chapter, then one report call after merge | inventing timestamps |
| LLM (cloud / demo) | Gemini 2.5 Flash, text only | local LLM in cloud, audio to API |
| LLM (local / prod path) | Qwen3-8B Q5 via llama.cpp | — |
| Timecodes | copy from ASR segment bounds only | LLM-generated times |

Chapter density target: 0.4–0.8 chapters/min; prefer 45–180 s chapters (warnings, not hard law).

Provenance note: full-meeting ASR text from research is a working hypothesis, not gold.
Cloud gates never use `eval/`.
