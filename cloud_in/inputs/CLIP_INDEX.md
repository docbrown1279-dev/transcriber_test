# Packed audio (no gold)

| path | duration | role |
|---|---|---|
| `clips/clip01.wav` | 60 s | quality — look for short solo greeting ~42–45 s |
| `clips/clip02.wav` | 60 s | quality — two-man Q/A |
| `clips/clip03.wav` | 60 s | quality — woman + man |
| `clips/concat_01_02_03.wav` | 180 s | concat of 01\|02\|03 (offsets 0 / 60 / 120) |
| `clips/timing_5min.wav` | 300 s | contiguous job slice @ source 500–800 s — **wall only** |
| `regression/test_apartments.wav` | ~85 s | old clip; watch short/secondary speakers |
| `regression/test_ninth.wav` | ~85 s | old clip; historically loses a short speaker under coarse settings |

Soft notes (not gold, not a K prior): do **not** force 2–4 speakers. Meetings may have many.
Do **not** apply duration crumb filters. Log crumb counts only.
Quality judgement on clip01–03 + apartments/ninth only; timing_5min = timings.
