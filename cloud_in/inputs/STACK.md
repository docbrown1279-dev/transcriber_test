# Stack freeze for D5.TTFT-split part1 spike

Do **not** reopen bakeoffs. Use existing demo engines.

| Layer | Setting |
|---|---|
| Audio | packed `voice_002_15min.m4a` (~900 s); cut plan JSON is authoritative |
| VAD | Silero T2 defaults (`config/base.yaml`) |
| Diarization | WeSpeaker ONNX; `cluster_distance_threshold=0.85`; windows `1.5/0.75` |
| Short clusters | **keep all** speaker ids — no crumb drop / no cluster speech filter |
| ASR | GigaAM `v3_rnnt` |
| Chunking | packing C + `rubert-tiny2` 0.70; **no LLM titles** this stage |
| TOC mode | force `pipeline.toc_mode=a` for `--until chunk` (see `scripts/run_ttft_part1.py`) |
| LLM | **none** (budget +2.0 s only in the timing report) |
| Hardware note | Prefer measuring under 2 CPU threads (`onnx_threads=2`); record `nproc` / RSS |

Out of scope: pyannote, Whisper, Jina D, backend/`src/` edits, gold/`eval/` reads.
