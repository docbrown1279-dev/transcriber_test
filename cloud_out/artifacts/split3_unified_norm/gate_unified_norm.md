# Gate D5.TTFT-split3 — unified full-file normalize (A/B loudness)

## Verdict: PASS

## Loudness A/B

Unified file-level gain_db = **1.657** (reused_full15_wav=True, rms=-33.055 dBFS, peak=-2.657 dBFS).

Old split3_shared_vad **per-part** re-gain (each part normalized on its own m4a):

| part | shared_vad gain_db | unified gain_db |
|---|---:|---:|
| part01 | 1.657 | 1.657 |
| part02 | 3.398 | 1.657 |
| part03 | 2.28 | 1.657 |

Parts are sliced from the already-normalized 15′ wav. No second file-level gain. ASR per-turn gain remains enabled.

part02 turns < 1.0 s: unified **13** vs shared_vad **14** (was 14).

## Timing (part × stage wall_sec from overall job start)

prep_sec (reuse wav + ffmpeg slice) = **0.328**
ttft_first_chapter_sec (part01 chunk done) = **32.798**
ttft_after_sleep_sec (part01 chunk + 2.0s) = **34.798**
wall_total_sec = **100.36**

Per-part `normalize` and `vad` are skipped (unified wav slice + full15 speech slice).

| stage | part01 | part02 | part03 |
|---|---:|---:|---:|
| normalize | 0.000s skip | 0.000s skip | 0.000s skip |
| vad | 0.000s skip | 0.000s skip | 0.000s skip |
| diarize | 14.411s | 15.354s | 12.471s |
| asr | 15.241s | 17.398s | 16.081s |
| chunk | 2.808s | 0.126s | 0.102s |
| llm_sleep_2s | 2.000s | 2.000s | 2.000s |

### Cumulative after each part

| part | cumulative_from_job_start_sec | speakers | n_turns | n_turns<1s | n_segments | n_chapters |
|---|---:|---|---:|---:|---:|---:|
| part01 | 34.799 | 2 | 32 | 0 | 34 | 4 |
| part02 | 69.69 | 3 | 65 | 13 | 66 | 4 |
| part03 | 100.356 | 3 | 61 | 6 | 61 | 2 |

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| N0 | one full-file normalize | gain_db=1.657 reused=True | no per-part re-gain | PASS |
| N1 | vs per-part gains | p01=1.657 p02=3.398 p03=2.28 | unified 1.657 | PASS (record) |
| V0 | per-part Silero VAD | skipped | slice full15/speech.json | PASS |
| D1 | cluster_distance_threshold | 0.85 | 0.85 | PASS |
| D2 | centroid assign | True | part2/3 nearest-centroid | PASS |
| C1 | stable speaker ids part1∩part2 | ['SPEAKER_00', 'SPEAKER_01'] | non-empty preferred | PASS |
| S1 | part02 turns < 1.0s | 13 (shared_vad 14) | record vs 14 | PASS (record) |
| M1 | merged segment count | 161 == 161 | no drops | PASS |
| M2 | merged monotonic start | True | no shuffle | PASS |
| M3 | per-part blocks preserved | True | contiguous texts | PASS |
| T1 | ttft_first_chapter_sec | 32.798 | part01 chunk done | PASS (record) |
| T2 | ttft_after_sleep_sec | 34.798 | +2.0 s sleep | PASS (record) |
| L1 | LLM calls | 0 (sleep only) | no Gemini/NVIDIA/Qwen | PASS |
| Q1 | part02 phrase after ~292s vs full15 | present=True | keep long opening | PASS |

## Sliced wav durations vs plan

| part | plan_sec | ffprobe_sec | delta | status |
|---|---:|---:|---:|---|
| part01 | 291.392 | 291.456 | 0.064 | PASS |
| part02 | 310.656 | 310.656 | 0.0 | PASS |
| part03 | 297.952 | 297.984 | 0.032 | PASS |

## Cut ~292 s (full15 vs shared_vad vs unified norm)

Full15 long phrase: «давайте сейчас второй третий пункт немножко перескочим по магистральным сетям информация у вас вся есть насколько я понимаю да»

shared_vad part02 opening: ['давайте сейчас второй третий пункт немножко перескочим по магистральным сетям информация у вас вся есть насколько я понимаю да', 'да', 'вы понимаете понимаете воду вы наверное понимаете помещение тп заявок подавали у вас все есть связь понятно это прокладываете что еще там тепло помещение тп у вас пока а по тп вот там вопросик', 'небольшой']

unified_norm part02 opening: ['давайте сейчас второй третий пункт немножко перескочим по магистральным сетям информация у вас вся есть насколько я понимаю да', 'да', 'вы понимаете понимаете воду вы наверное услышали понимаете помещение тп заявок подавали у вас все есть связь понятно прокладываете что еще там тепло помещение тп у вас а по тп вот там вопросик', 'небольшой']

Phrase in shared_vad: True. Phrase in unified_norm: True. Still OK vs full15: True.

## Agent judgement

A/B is loudness only: one gain on the 15′ file, then PCM slices. Shared VAD and centroid-assign diarization are unchanged (no cluster retune). Packing C still carries the previous chapter tail. ASR may still apply per-turn gain.

part02 crumb turns (<1s): 13 vs shared_vad 14. If unified gain (typically lower than part02-only 3.4 dB) changes WeSpeaker window SNR, short-turn count can move; this run records the delta without changing absorb/threshold.

Stable ids part01∩part02: ['SPEAKER_00', 'SPEAKER_01']. Chapters spanning cuts: [{'id': 'C03', 'start': 211.916, 'end': 346.516, 'cuts': [291.392]}, {'id': 'C06', 'start': 564.1, 'end': 738.228, 'cuts': [602.048]}].

No LLM titles. `llm_sleep_2s` is `time.sleep(2.0)` after chunk.

## Environment

- host nproc=4; onnx_threads=2; HF_HUB_OFFLINE=1
- reused full15_job/normalized.wav; sliced by cut_plan; full15/speech.json VAD
- helper: cloud_out/artifacts/split3_unified_norm/scripts/ (no src/ or config/ edits)
- did not clobber split3_shared_vad/

## Deviations and blockers

None.
