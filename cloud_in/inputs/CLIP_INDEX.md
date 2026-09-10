# Packed audio (no gold)

| path | duration | human focus (no labels) |
|---|---|---|
| `clips/clip01_embeddings_men.wav` | 60 s | ≥2 men dialogue (embeddings topic) |
| `clips/clip02_vadim_q.wav` | 60 s | ≥2 men Q/A (must not be one speaker) |
| `clips/clip03_woman_men.wav` | 60 s | woman + man(s); keep woman separate |
| `regression/test_apartments.wav` | ~85 s | soft: expect ~3 speakers |
| `regression/test_ninth.wav` | ~85 s | soft: expect ~3 speakers |

Do **not** invent gold. Report cluster stats + turn timelines for local human eval.
