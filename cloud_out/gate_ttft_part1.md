# Gate D5.TTFT-split — part1 pause-cut + early chapters (no LLM)

## Verdict: PASS_WITH_WARNINGS

Numeric TTFT+2 budget is met (37.396 s ≤ 360 s). Warning: this host has `nproc=4` and
Torch defaulted to 4 intra/interop threads, so the 2-CPU-like PASS hint is **not**
demonstrated. ONNX stages used `onnx_threads=2` as requested. Do not treat these
walls as a 2-vCPU forecast.

## Timing (same pipeline, until chunk, no LLM)

| job | audio | wall_sec | notes |
|---|---|---:|---|
| part01 (TTFT) | 291.398 s slice | **35.396** | first untitled chapters from pause-cut part1 |
| part01 + LLM budget | same | **37.396** | TTFT + 2.0 s (titles not actually called) |
| **full 15 min file** | **900.015 s** packed `voice_002_15min.m4a` | **89.757** | unsplit file, same `until=chunk` / toc_mode a |

Full-file stage marks (seconds from job start): normalize 1.955, vad 4.040,
diarize 45.215, asr 86.947, correction_suggest 86.950, chunk **89.757**.

Part01 stage marks: normalize 1.088, vad 1.839, diarize 16.097, asr 32.628,
correction_suggest 32.630, chunk **35.396**.

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| P0 | preflight packed inputs + runner | audio 14M m4a, cut_plan JSON, `scripts/run_ttft_part1.py` | all present | PASS |
| P1 | part01 duration vs plan | 291.398 s (Δ +0.006 s) | ±1.0 s vs 291.392 | PASS |
| P2 | part02 duration vs plan | 310.693 s (Δ +0.037 s) | ±1.0 s vs 310.656 | PASS |
| P3 | part03 duration vs plan | 297.969 s (Δ +0.017 s) | ±1.0 s vs 297.952 | PASS |
| D1 | `cluster_distance_threshold` | 0.85 | 0.85 (base/demo) | PASS |
| D2 | short clusters / speaker ids | SPEAKER_00, SPEAKER_01 kept; merge absorb 1.0 s from config | no extra crumb drop | PASS |
| A1 | ASR engine / emptiness (part01) | gigaam_v3_rnnt; 34 segments, 0 empty, 3137 chars RU | real text, no LLM | PASS |
| C1 | chunker / titles (part01) | packing_c + rubert_tiny2 0.70; all titles `""` | toc_mode a, until chunk, no LLM | PASS |
| T1 | `speaker_count` (part01) | 2 | recorded (no gold) | PASS (record) |
| T2 | `n_turns` (part01) | 32 | recorded (no gold) | PASS (record) |
| T3 | `n_chapters` (part01) | 4 | recorded (no gold) | PASS (record) |
| T4 | `ttft_first_chapter_sec` | 35.396 | first `chapters.json` after part01 job start | PASS (record) |
| T5 | `ttft_plus_llm_budget_sec` | 37.396 (= 35.396 + 2.0) | ≤ 360 s **on 2-CPU-like host** | WARN (nproc=4) |
| T6 | `wall_full_15min_sec` | **89.757** (900.015 s file; 5 speakers, 141 turns, 9 chapters) | measured unsplit, same until=chunk | PASS (record) |
| L1 | LLM calls | 0 | none this stage | PASS |

## Agent judgement

Part1 is a usable untitled chapter pack, not a titled report. Four packing-C chapters
cover 0.876–290.708 s of the 291.4 s slice; titles are empty as required (no Gemini /
NVIDIA / Qwen). Transcript text is ordinary meeting Russian (example first segment:
«давайте по протоколу у нас есть»), with timecodes copied from diarized turns.

Speaker inventory on part01 is 2 ids after AHC at distance 0.85. Both ids appear in
turns and chapters. Merge settings match config (`same_speaker_gap_sec=0.3`,
`absorb_shorter_than_sec=1.0`); no extra post-filter of short clusters was applied.

On the **unsplit 15-minute file** the same stack finished chapters in **89.757 s**
(5 speaker ids, 141 turns, 9 untitled chapters, 143 ASR segments / 2 empty). That is
the full-file wall, not TTFT: first chapters appear only when the whole 15′ job
reaches `chunk`. Pause-cut part01 still reaches first chapters at 35.396 s — about
2.5× earlier than waiting for the full file on this host.

TTFT and the 15′ wall are both far under a 360 s hint **on this 4-CPU VM**. ASR used
Torch’s default 4 threads. A 2-vCPU box would be slower, especially in GigaAM.

## Environment

- host `nproc`: **4** (not 2-CPU-like; onnx_threads=2; torch num_threads=4)
- memory: 15 GiB; part01 peak process-tree RSS **1970.2 MiB**; full-15′ peak **2030.6 MiB**
- disk: 254 G, ~245 G free after run
- ffmpeg: 6.1.1-3ubuntu5
- python: 3.12.3
- uv: 0.12.13 (installed this run; was missing on the VM)
- git_rev_start: `82c1d26412a979c24cf9334ffb4f6b02da2aa8c2` (branch `cursor/d5-ttft-split`)
- packages: torch 2.14.0+cpu, torchaudio 2.11.0+cpu, onnxruntime 1.23.2, gigaam 0.2.0,
  speakeronnx 0.0.1, scikit-learn 1.9.0, sentence-transformers 6.0.1
- wall part01 (HF_HUB_OFFLINE=1): 35.396 s
- wall full 15 min file (HF_HUB_OFFLINE=1): **89.757 s** (monitor wrapper 91.201 s)
- LLM calls: none (provider + purpose: n/a)
- prefetch (excluded from both walls): ~21 s; Silero GitHub ONNX, WeSpeaker HF,
  GigaAM `~/.cache/gigaam/v3_rnnt.ckpt` (426 M), rubert-tiny2 HF

## Deviations and blockers

- Prompt assumed weights already local + `HF_HUB_OFFLINE=1`. Caches were empty on this
  VM. Bounded choice: prefetch once, then run measured jobs with `HF_HUB_OFFLINE=1`.
  Prefetch is **not** included in TTFT or the 15′ wall.
- `uv` was not on PATH. Installed official uv 0.12.13, then `uv sync --frozen --extra asr
  --extra diarize --extra embed` (lockfile only; no `uv add`).
- ffmpeg `-c copy` used as allowed; all part durations within ±1.0 s (no re-encode).
- Did not edit `src/`, `config/`, `tests/`, `docs/`, `eval/`, `.env`. Did not open a PR.
- Did not run pytest/ruff/mypy/bandit: this stage is a research spike with reports only
  under `cloud_out/` (prompt override vs product AGENTS.md).
- Job working copies (`normalized.wav`, `vad_input.wav`) remain under
  `cloud_out/artifacts/part01_job/` and `cloud_out/artifacts/full15_job/` and are not
  git deliverables.
- Gold / `eval/` not read. Part02/part03 were not run through ASR.
- Original pack said part01-only; a follow-up asked for the full 15-minute file wall.
  That was measured on the packed unsplit `voice_002_15min.m4a` with the same runner
  (`until=chunk`, no LLM).
