# Gate D5.TTFT-split3 — shared full15 VAD

## Verdict: PASS

## Timing (part × stage wall_sec from overall job start)

VAD is **skipped** on every part: `speech.json` is sliced from `cloud_out/artifacts/full15/speech.json` (intersect [plan_start, plan_end], clip, subtract plan_start).

ttft_first_chapter_sec (part01 chunk done) = **34.605**
ttft_after_sleep_sec (part01 chunk + 2.0s) = **36.605**
wall_total_sec (all 3 parts + sleeps, no per-part VAD) = **108.819**

| stage | part01 | part02 | part03 |
|---|---:|---:|---:|
| normalize | 0.841s | 0.670s | 0.767s |
| vad | 0.000s skip | 0.000s skip | 0.000s skip |
| diarize | 13.894s | 14.483s | 12.964s |
| asr | 16.746s | 19.894s | 19.087s |
| chunk | 3.122s | 0.160s | 0.174s |
| llm_sleep_2s | 2.000s | 2.000s | 2.000s |

### Cumulative after each part

| part | cumulative_from_job_start_sec | speakers | n_turns | n_segments | n_chapters |
|---|---:|---|---:|---:|---:|
| part01 | 36.606 | 2 | 32 | 34 | 4 |
| part02 | 73.818 | 3 | 67 | 68 | 4 |
| part03 | 108.814 | 3 | 54 | 54 | 3 |

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| S0 | reuse packed splits | 3 m4a | durations ±1.0 s | PASS |
| V0 | per-part Silero VAD | skipped | do not run vad stage | PASS |
| V1 | shared VAD source | /workspace/cloud_out/artifacts/full15/speech.json | full15/speech.json slice | PASS |
| D1 | cluster_distance_threshold | 0.85 | 0.85 | PASS |
| D2 | centroid assign | True | part2/3 nearest-centroid | PASS |
| C1 | stable speaker ids part1∩part2 | ['SPEAKER_00', 'SPEAKER_01'] | non-empty preferred | PASS |
| C2 | stable speaker ids part2∩part3 | ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02'] | non-empty preferred | PASS |
| P1 | packing tail across cuts | spanning=[{'id': 'C03', 'start': 211.916, 'end': 346.516, 'cuts': [291.392]}, {'id': 'C06', 'start': 568.684, 'end': 738.228, 'cuts': [602.048]}] | packing-C may extend | PASS |
| M1 | merged segment count | 156 == 156 | no drops | PASS |
| M2 | merged monotonic start | True | no shuffle | PASS |
| M3 | per-part blocks preserved | True | contiguous texts | PASS |
| T1 | ttft_first_chapter_sec | 34.605 | part01 chunk done | PASS (record) |
| T2 | ttft_after_sleep_sec | 36.605 | +2.0 s sleep | PASS (record) |
| L1 | LLM calls | 0 (sleep only) | no Gemini/NVIDIA/Qwen | PASS |
| Q1 | part02 opening recovers full15 long phrase | recovered=True in_shared=True in_old_split3=False | keep phrase after cut ~292s | PASS |

## Part durations vs plan

| part | plan_sec | ffprobe_sec | delta | status |
|---|---:|---:|---:|---|
| part01 | 291.392 | 291.398 | 0.006 | PASS |
| part02 | 310.656 | 310.693 | 0.037 | PASS |
| part03 | 297.952 | 297.969 | 0.017 | PASS |

## Cut ~292 s (full15 vs old split3 vs shared VAD)

Full15 long phrase: «давайте сейчас второй третий пункт немножко перескочим по магистральным сетям информация у вас вся есть насколько я понимаю да»

Old split3 part02 opening (per-part Silero): ['по магистральным сетям', 'да вы понимаете понимаете', 'заявку у нас все есть', 'тп вот там вопросик небольшой']

Shared-VAD part02 opening: ['давайте сейчас второй третий пункт немножко перескочим по магистральным сетям информация у вас вся есть насколько я понимаю да', 'да', 'вы понимаете понимаете воду вы наверное понимаете помещение тп заявок подавали у вас все есть связь понятно это прокладываете что еще там тепло помещение тп у вас пока а по тп вот там вопросик', 'небольшой']

Phrase present in old split3: False. Phrase present with shared VAD: True. Recovered vs split3: True.

## Agent judgement

Merge mode: `tail_packing_plus_centroid_speakers`. VAD was **not** re-run per part. Regions come from the existing full15 Silero `speech.json`, clipped to each pause-cut window. Speaker gallery from part1 AHC is reused for part2/3 windows (cosine distance ≤ 0.85). Packing C still carries the previous part's last chapter on the absolute timeline.

Stable ids part01∩part02: ['SPEAKER_00', 'SPEAKER_01']. part02∩part03: ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02']. Chapters spanning cuts: [{'id': 'C03', 'start': 211.916, 'end': 346.516, 'cuts': [291.392]}, {'id': 'C06', 'start': 568.684, 'end': 738.228, 'cuts': [602.048]}].

No LLM titles. `llm_sleep_2s` is `time.sleep(2.0)` after chunk on every part.

## Environment

- host nproc=4 (not 2-CPU-like); onnx_threads=2; HF_HUB_OFFLINE=1
- existing part01..03.m4a reused; full15 speech.json reused; weights reused
- helper: cloud_out/artifacts/split3_shared_vad/scripts/ (no src/ or config/ edits)
- previous split3/ artifacts were not overwritten

## Deviations and blockers

None.
