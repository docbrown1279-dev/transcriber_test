# Stack freeze — D5.TTFT cluster rebuild

| Layer | Setting |
|---|---|
| Audio | `voice_002_15min.m4a`; `cut_plan_15min_3.json` |
| Prep | one file normalize + wav slices; **shared** VAD |
| Diar | WeSpeaker `1.5/0.75`; AHC/assign thr **0.85** |
| Variants | H1 / H2 / H3 only (see `prompt.md`) |
| ASR / LLM | out of scope |

No pyannote, no gold/`eval/`, no `src/` edits, no sticky hypothesis.
