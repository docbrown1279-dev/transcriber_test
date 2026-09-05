# Full meeting dual-path — results/d1_dual

Branch `cursor/d1-silero-tune`. Source: `cloud_in/inputs/audio/voice_002.m4a`.

## Pipeline

- `normalized.wav` — 16 kHz mono, no compressor (ASR + WeSpeaker)
- `vad_input.wav` — `dynaudnorm=f=150:g=7:p=0.9` (Silero only)
- ASR — GigaAM v3 + **per-turn linear gain** on slices

## vs attempt 3 (`results/d1`)

| metric | attempt 3 | dual-path |
|---|---:|---:|
| speech_sec (Silero) | 138 | **826** |
| ASR segments | 48 | **347** |
| nonempty segments | 48 | **339** |
| text chars (approx) | 3153 | **11587** |

Former hole windows now have content (канализация/паркинг; мегаватт; габариты трансформаторов).

## Window smoke (earlier)

[`d1_window_pipeline.md`](d1_window_pipeline.md): rescue **5/5** with readable hyp; regression **5/5**.

## Note

Higher `holes` count is expected with denser VAD crumbs (more inter-region gaps), not a regression of speech coverage.
