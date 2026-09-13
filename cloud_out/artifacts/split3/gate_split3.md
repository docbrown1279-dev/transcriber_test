# Gate D5.TTFT-split3 — cross-part continuity

## Verdict: PASS

## Timing (part × stage wall_sec from overall job start)

ttft_first_chapter_sec (part01 chunk done) = **31.834**
ttft_after_sleep_sec (part01 chunk + 2.0s) = **33.834**
wall_total_sec (all 3 parts + sleeps) = **105.713**

| stage | part01 | part02 | part03 |
|---|---:|---:|---:|
| normalize | 0.788s | 0.626s | 0.734s |
| vad | 0.703s | 0.761s | 0.712s |
| diarize | 13.173s | 13.687s | 13.126s |
| asr | 14.376s | 19.403s | 18.442s |
| chunk | 2.792s | 0.152s | 0.175s |
| llm_sleep_2s | 2.000s | 2.000s | 2.000s |

### Cumulative after each part

| part | cumulative_from_job_start_sec | speakers | n_turns | n_segments | n_chapters |
|---|---:|---|---:|---:|---:|
| part01 | 33.834 | 2 | 32 | 34 | 4 |
| part02 | 70.466 | 3 | 68 | 68 | 3 |
| part03 | 105.657 | 3 | 52 | 52 | 4 |

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| S0 | reuse packed splits | 3 m4a | durations ±1.0 s | PASS |
| D1 | cluster_distance_threshold | 0.85 | 0.85 | PASS |
| D2 | centroid assign | True | part2/3 nearest-centroid | PASS |
| C1 | stable speaker ids part1∩part2 | ['SPEAKER_00', 'SPEAKER_01'] | non-empty preferred | PASS |
| C2 | stable speaker ids part2∩part3 | ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02'] | non-empty preferred | PASS |
| P1 | packing tail across cuts | spanning=[{'id': 'C03', 'start': 211.916, 'end': 380.788, 'cuts': [291.392]}, {'id': 'C05', 'start': 531.084, 'end': 689.588, 'cuts': [602.048]}] | packing-C may extend | PASS |
| M1 | merged segment count | 154 == 154 | no drops | PASS |
| M2 | merged monotonic start | True | no shuffle | PASS |
| M3 | per-part blocks preserved | True | contiguous texts | PASS |
| T1 | ttft_first_chapter_sec | 31.834 | part01 chunk done | PASS (record) |
| T2 | ttft_after_sleep_sec | 33.834 | +2.0 s sleep | PASS (record) |
| L1 | LLM calls | 0 (sleep only) | no Gemini/NVIDIA/Qwen | PASS |

## Part durations vs plan

| part | plan_sec | ffprobe_sec | delta | status |
|---|---:|---:|---:|---|
| part01 | 291.392 | 291.398 | 0.006 | PASS |
| part02 | 310.656 | 310.693 | 0.037 | PASS |
| part03 | 297.952 | 297.969 | 0.017 | PASS |

## Agent judgement

Merge mode: `tail_packing_plus_centroid_speakers`. Speaker gallery from part1 AHC is reused for part2/3 windows (cosine distance ≤ 0.85 → same SPEAKER_* ; leftovers AHC'd as new ids). Packing C on part N prepends the previous part's last chapter segments on the absolute timeline so a chapter may extend across a pause cut.

Stable ids part01∩part02: ['SPEAKER_00', 'SPEAKER_01']. part02∩part03: ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02']. Chapters spanning cuts: [{'id': 'C03', 'start': 211.916, 'end': 380.788, 'cuts': [291.392]}, {'id': 'C05', 'start': 531.084, 'end': 689.588, 'cuts': [602.048]}].

No LLM titles. `llm_sleep_2s` is `time.sleep(2.0)` after chunk on every part.

## Environment

- host nproc=4 (not 2-CPU-like); onnx_threads=2; HF_HUB_OFFLINE=1
- existing part01..03.m4a reused; weights reused from local caches
- helper: cloud_out/artifacts/split3/scripts/ (no src/ or config/ edits)

## Deviations and blockers

None.
