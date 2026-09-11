# Gate D5.TTFT-split — part1 pause-cut + early chapters (no LLM)

## Verdict: PASS_WITH_WARNINGS

Numeric TTFT+2 budget is met (37.396 s ≤ 360 s). Warning: this host has `nproc=4` and
Torch defaulted to 4 intra/interop threads, so the 2-CPU-like PASS hint is **not**
demonstrated. ONNX stages used `onnx_threads=2` as requested. Do not treat 37 s as a
2-vCPU forecast.

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| P0 | preflight packed inputs + runner | audio 14M m4a, cut_plan JSON, `scripts/run_ttft_part1.py` | all present | PASS |
| P1 | part01 duration vs plan | 291.398 s (Δ +0.006 s) | ±1.0 s vs 291.392 | PASS |
| P2 | part02 duration vs plan | 310.693 s (Δ +0.037 s) | ±1.0 s vs 310.656 | PASS |
| P3 | part03 duration vs plan | 297.969 s (Δ +0.017 s) | ±1.0 s vs 297.952 | PASS |
| D1 | `cluster_distance_threshold` | 0.85 | 0.85 (base/demo) | PASS |
| D2 | short clusters / speaker ids | SPEAKER_00, SPEAKER_01 kept; merge absorb 1.0 s from config | no extra crumb drop | PASS |
| A1 | ASR engine / emptiness | gigaam_v3_rnnt; 34 segments, 0 empty, 3137 chars RU | real text, no LLM | PASS |
| C1 | chunker / titles | packing_c + rubert_tiny2 0.70; all titles `""` | toc_mode a, until chunk, no LLM | PASS |
| T1 | `speaker_count` | 2 | recorded (no gold) | PASS (record) |
| T2 | `n_turns` | 32 | recorded (no gold) | PASS (record) |
| T3 | `n_chapters` | 4 | recorded (no gold) | PASS (record) |
| T4 | `ttft_first_chapter_sec` | 35.396 | first `chapters.json` after job start | PASS (record) |
| T5 | `ttft_plus_llm_budget_sec` | 37.396 (= 35.396 + 2.0) | ≤ 360 s **on 2-CPU-like host** | WARN (nproc=4) |
| L1 | LLM calls | 0 | none this stage | PASS |

Stage marks (seconds from job start): normalize 1.088, vad 1.839, diarize 16.097,
asr 32.628, correction_suggest 32.630, chunk 35.396.

## Agent judgement

Part1 is a usable untitled chapter pack, not a titled report. Four packing-C chapters
cover 0.876–290.708 s of the 291.4 s slice; titles are empty as required (no Gemini /
NVIDIA / Qwen). Transcript text is ordinary meeting Russian (example first segment:
«давайте по протоколу у нас есть»), with timecodes copied from diarized turns.

Speaker inventory is 2 ids after AHC at distance 0.85. Both ids appear in turns and
chapters. Merge settings match config (`same_speaker_gap_sec=0.3`,
`absorb_shorter_than_sec=1.0`); no extra post-filter of short clusters was applied.

TTFT is far under the 360 s research hint **on this 4-CPU VM**. ASR wall (~16.5 s for
~244 s of speech) used Torch’s default 4 threads. A 2-vCPU box would be slower,
especially in GigaAM. The spike still shows that pause-cut part1 + `until=chunk`
avoids the full 15′ pipeline before first chapters exist.

## Environment

- host `nproc`: **4** (not 2-CPU-like; onnx_threads=2; torch num_threads=4)
- memory: 15 GiB; pipeline peak process-tree RSS **1970.2 MiB**
- disk: 254 G, ~245 G free after run
- ffmpeg: 6.1.1-3ubuntu5
- python: 3.12.3
- uv: 0.12.13 (installed this run; was missing on the VM)
- git_rev_start: `82c1d26412a979c24cf9334ffb4f6b02da2aa8c2` (branch `cursor/d5-ttft-split`)
- packages: torch 2.14.0+cpu, torchaudio 2.11.0+cpu, onnxruntime 1.23.2, gigaam 0.2.0,
  speakeronnx 0.0.1, scikit-learn 1.9.0, sentence-transformers 6.0.1
- wall (timed job, HF_HUB_OFFLINE=1): 35.396 s (monitor wrapper 37.077 s)
- LLM calls: none (provider + purpose: n/a)
- prefetch (excluded from TTFT): ~21 s; Silero GitHub ONNX, WeSpeaker HF,
  GigaAM `~/.cache/gigaam/v3_rnnt.ckpt` (426 M), rubert-tiny2 HF

## Deviations and blockers

- Prompt assumed weights already local + `HF_HUB_OFFLINE=1`. Caches were empty on this
  VM. Bounded choice: prefetch once, then run the measured job with `HF_HUB_OFFLINE=1`.
  Prefetch is **not** included in TTFT.
- `uv` was not on PATH. Installed official uv 0.12.13, then `uv sync --frozen --extra asr
  --extra diarize --extra embed` (lockfile only; no `uv add`).
- ffmpeg `-c copy` used as allowed; all part durations within ±1.0 s (no re-encode).
- Did not edit `src/`, `config/`, `tests/`, `docs/`, `eval/`, `.env`. Did not open a PR.
- Did not run pytest/ruff/mypy/bandit: this stage is a research spike with reports only
  under `cloud_out/` (prompt override vs product AGENTS.md).
- Job working copies (`normalized.wav`, `vad_input.wav`) remain under
  `cloud_out/artifacts/part01_job/` and are not git deliverables.
- Gold / `eval/` not read. No part02/part03 ASR.
