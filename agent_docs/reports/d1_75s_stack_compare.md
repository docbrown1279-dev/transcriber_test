# First 75s compare — gold / Stage2 / 1f Silero / current demo

## Sources

| id | stack | file |
|---|---|---|
| gold | human | `eval/d1/transcribe/test_voice.json` |
| stage2 | **pyannote 3.1 + linear gain + GigaAM** (no compressor) | `data/research_asr_stage2/` = `.trash/3b_data/full_asr.md` (Stage **2**, reused by 3b) |
| 1f | **raw m4a → Silero + WeSpeaker + GigaAM** (no dynaudnorm) | `data/research_asr_1f_vad_wespeaker/test_voice.json` |
| now | dynaudnorm VAD + Silero + WeSpeaker + merge agg + GigaAM | `data/voice_002/` |

## Coverage 0–75 s

| | speech_sec | notes |
|---|---:|---|
| gold | 67.5 | |
| stage2 | 61.8 | hole **0–10 s** (quiet start); cuts before letter ~74 s |
| 1f Silero | 65.4 | start OK; canalization **fragmented** |
| now | 55.8 | start OK but mangled; mid-word cuts; speaker glue |

## What went wrong in demo vs research

1. **Not the same stack as Stage 2.** Stage 2 = pyannote segmentation. Demo = Silero. Even 1f Silero (no compressor) already split canalization into «це от» / «надо нести» / «точки подключения».
2. **Demo added dynaudnorm on whole `vad_input`** — research Silero used **raw** clip. That was the main process deviation for VAD.
3. **Demo then cranked merge (agg)** to hide crumbs → glued «вопрос закроем» onto the next speaker’s question; still left «определено точ».
4. Stage 2 “holes” are real (no protocol opening; weak on letter after 74 s) but the **expertise/parking paragraph is intact** as two long turns 21.8–65.5. Current demo loses middle glue («заходит экспертизу… плюс минус…»).

## Suggested fix direction (for next agent)

A. Ablate VAD preprocess on the same 75 s window: `C0_raw` vs peak-limit-only vs current C3; keep merge mild; compare to 1f quotes + gold.  
B. Do **not** judge by coverage alone — require readable canalization/expertise sentence.  
C. Keep Stage 2 JSON as quality ceiling (pyannote); Silero path must approach 1f text, then beat holes with local peak limit / hole-fallback — not full-file dynaudnorm.
