# D5.TTFT-diar — WeSpeaker windows + cluster tuner

Research-only run on packed 60–85 s clips. No production pipeline/UI changes, no ASR, no LLM, no `eval/` gold.

**Verdict:** keep embed windows at baseline `1.5 / 0.75`. Do not ship coarser presets A/B. Default `cluster_distance_threshold=0.85` **undersplits** the motivating male-dialogue clip. Best pack combo: **baseline windows + 0.80 + iterative crumb merge (≤2.5 s → nearest large centroid)**. Window coarsening is **not** a reliable TTFT lever on this CPU: `n_windows` drops, per-window ONNX cost rises, wall stays flat. Cluster time is milliseconds. 15-minute audio was not packed — S2 file-split remains the TTFT path.

## Soft bar (judgement, not gold)

Healthy = 2–4 ids with speech ≥3 s. 1 fat id = undersplit. ≥10 / crumb storm = oversplit. Crumbs ≤2.5 s do not count toward the band. Roles (men/woman) were **not** labelled here; timelines are for local gold.

| clip | soft expect |
|---|---|
| clip01, clip02 | 2–4 ids; ≥2 substantial male clusters |
| clip03 | 2–4 ids; a second cluster not swallowed into one pool |
| test_apartments, test_ninth | ~3 speakers inside 2–4 |

## S1 — window presets at threshold 0.85 (current default)

| clip | preset | window/step | n_windows | embed_s | cluster_s | n_id | n_sub | crumbs≤2.5s | top1 share | soft |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| clip01_embeddings_men | baseline | 1.5/0.75 | 72 | 1.657 | 0.0010 | 3 | 1 | 2 | 0.960 | undersplit |
| clip01_embeddings_men | A | 2.0/1.00 | 55 | 2.105 | 0.0010 | 1 | 1 | 0 | 1.000 | undersplit |
| clip01_embeddings_men | B | 3.0/1.50 | 34 | 1.266 | 0.0000 | 1 | 1 | 0 | 1.000 | undersplit |
| clip02_vadim_q | baseline | 1.5/0.75 | 52 | 1.301 | 0.0010 | 3 | 3 | 0 | 0.511 | healthy |
| clip02_vadim_q | A | 2.0/1.00 | 42 | 0.950 | 0.0000 | 2 | 2 | 0 | 0.919 | healthy |
| clip02_vadim_q | B | 3.0/1.50 | 28 | 0.835 | 0.0000 | 1 | 1 | 0 | 1.000 | undersplit |
| clip03_woman_men | baseline | 1.5/0.75 | 76 | 1.677 | 0.0010 | 2 | 2 | 0 | 0.550 | healthy |
| clip03_woman_men | A | 2.0/1.00 | 56 | 1.546 | 0.0010 | 2 | 2 | 0 | 0.563 | healthy |
| clip03_woman_men | B | 3.0/1.50 | 37 | 1.303 | 0.0000 | 2 | 2 | 0 | 0.588 | healthy |
| test_apartments | baseline | 1.5/0.75 | 83 | 2.413 | 0.0010 | 5 | 3 | 2 | 0.556 | healthy |
| test_apartments | A | 2.0/1.00 | 62 | 1.728 | 0.0010 | 3 | 3 | 0 | 0.777 | healthy |
| test_apartments | B | 3.0/1.50 | 39 | 2.197 | 0.0010 | 2 | 2 | 0 | 0.799 | healthy |
| test_ninth | baseline | 1.5/0.75 | 89 | 2.699 | 0.0010 | 3 | 3 | 0 | 0.537 | healthy |
| test_ninth | A | 2.0/1.00 | 64 | 2.534 | 0.0010 | 2 | 2 | 0 | 0.544 | healthy |
| test_ninth | B | 3.0/1.50 | 44 | 1.557 | 0.0000 | 2 | 2 | 0 | 0.533 | healthy |

Window counts vs baseline (mean across clips): A ≈ 0.75×, B ≈ 0.49×, matching `1/step_sec`. Embed wall does **not** follow that ratio on this host.

| preset | mean n_windows | mean embed_s | ms/window |
|---|---:|---:|---:|
| baseline | 74.4 | 1.949 | 26.2 |
| A | 55.8 | 1.773 | 31.8 |
| B | 36.4 | 1.432 | 39.3 |

Per-window cost grows with window length (~22 ms at 1.5 s → ~43 ms at 3.0 s on the first grid; this repeat is the same pattern). Coarser windows buy fewer ONNX calls but each call is heavier. **H2 is not a free speedup.**

Quality at 0.85:

- `clip01` (two-plus men): baseline already **undersplit** (1 substantial, top1 0.960). A and B collapse to a single id.
- `clip02` (must not be one speaker): baseline **healthy** (3 sub, top1 0.511). A stays 2 ids but top1 0.919 (almost glued). B **undersplit** 1.000.
- `clip03`: 2 substantial, top1 ~0.55–0.59 at all presets — a second cluster survives (woman identity not claimed).
- apartments / ninth: stay in the 2–4 substantial band; coarser windows reduce crumbs but also drop toward 2 ids.

**S1 recommendation:** do not change `window_sec` / `step_sec` for the demo. Coarser presets hurt the male-glue clips and do not clearly cut wall time here.

## Cluster tuner — baseline windows

| clip | thr | n_id | n_sub | crumbs≤2.5s | top1 | knee_gap | soft | speech_sec per id |
|---|---:|---:|---:|---:|---:|---:|---|---|
| clip01_embeddings_men | 0.80 | 4 | 2 | 2 | 0.741 | 0.065 | healthy | `SPEAKER_00 41.89s, SPEAKER_01 12.42s, SPEAKER_02 1.50s, SPEAKER_03 0.75s` |
| clip01_embeddings_men | 0.82 | 3 | 1 | 2 | 0.960 | 0.065 | undersplit | `SPEAKER_00 54.31s, SPEAKER_01 1.50s, SPEAKER_02 0.75s` |
| clip01_embeddings_men | 0.85 | 3 | 1 | 2 | 0.960 | 0.065 | undersplit | `SPEAKER_00 54.31s, SPEAKER_01 1.50s, SPEAKER_02 0.75s` |
| clip01_embeddings_men | 0.88 | 2 | 1 | 1 | 0.973 | 0.065 | undersplit | `SPEAKER_00 55.06s, SPEAKER_01 1.50s` |
| clip02_vadim_q | 0.80 | 3 | 3 | 0 | 0.511 | 0.117 | healthy | `SPEAKER_00 18.77s, SPEAKER_01 5.25s, SPEAKER_02 25.14s` |
| clip02_vadim_q | 0.82 | 3 | 3 | 0 | 0.511 | 0.117 | healthy | `SPEAKER_00 18.77s, SPEAKER_01 5.25s, SPEAKER_02 25.14s` |
| clip02_vadim_q | 0.85 | 3 | 3 | 0 | 0.511 | 0.117 | healthy | `SPEAKER_00 18.77s, SPEAKER_01 5.25s, SPEAKER_02 25.14s` |
| clip02_vadim_q | 0.88 | 2 | 2 | 0 | 0.893 | 0.117 | healthy | `SPEAKER_00 43.91s, SPEAKER_01 5.25s` |
| clip03_woman_men | 0.80 | 3 | 3 | 0 | 0.550 | 0.132 | healthy | `SPEAKER_00 32.25s, SPEAKER_01 4.50s, SPEAKER_02 21.91s` |
| clip03_woman_men | 0.82 | 2 | 2 | 0 | 0.550 | 0.132 | healthy | `SPEAKER_00 32.25s, SPEAKER_01 26.41s` |
| clip03_woman_men | 0.85 | 2 | 2 | 0 | 0.550 | 0.132 | healthy | `SPEAKER_00 32.25s, SPEAKER_01 26.41s` |
| clip03_woman_men | 0.88 | 2 | 2 | 0 | 0.550 | 0.132 | healthy | `SPEAKER_00 32.25s, SPEAKER_01 26.41s` |
| test_apartments | 0.80 | 7 | 3 | 4 | 0.523 | 0.052 | healthy | `SPEAKER_00 35.23s, SPEAKER_01 14.08s, SPEAKER_02 1.50s, SPEAKER_03 2.25s, SPEAKER_04 12.81s, SPEAKER_05 0.75s, SPEAKER_06 0.75s` |
| test_apartments | 0.82 | 6 | 3 | 3 | 0.523 | 0.052 | healthy | `SPEAKER_00 35.23s, SPEAKER_01 14.83s, SPEAKER_02 1.50s, SPEAKER_03 2.25s, SPEAKER_04 12.81s, SPEAKER_05 0.75s` |
| test_apartments | 0.85 | 5 | 3 | 2 | 0.556 | 0.052 | healthy | `SPEAKER_00 37.48s, SPEAKER_01 14.83s, SPEAKER_02 1.50s, SPEAKER_03 12.81s, SPEAKER_04 0.75s` |
| test_apartments | 0.88 | 4 | 2 | 2 | 0.776 | 0.052 | healthy | `SPEAKER_00 52.30s, SPEAKER_01 1.50s, SPEAKER_02 12.81s, SPEAKER_03 0.75s` |
| test_ninth | 0.80 | 4 | 3 | 0 | 0.497 | 0.042 | healthy | `SPEAKER_00 36.05s, SPEAKER_01 29.75s, SPEAKER_02 3.82s, SPEAKER_03 2.89s` |
| test_ninth | 0.82 | 3 | 3 | 0 | 0.537 | 0.042 | healthy | `SPEAKER_00 38.95s, SPEAKER_01 29.75s, SPEAKER_02 3.82s` |
| test_ninth | 0.85 | 3 | 3 | 0 | 0.537 | 0.042 | healthy | `SPEAKER_00 38.95s, SPEAKER_01 29.75s, SPEAKER_02 3.82s` |
| test_ninth | 0.88 | 2 | 2 | 0 | 0.537 | 0.042 | healthy | `SPEAKER_00 38.95s, SPEAKER_01 33.57s` |

Linkage “knee” (largest gap in agglomerative merge distances) is **weak**: 0.04–0.13, and the gap location (~0.79–0.94) does not pick a unique operating point. Do not auto-set the threshold from the knee on these clips.

Substantial-count grid (n_sub / n_id, soft):

| clip | preset | 0.80 | 0.82 | 0.85 | 0.88 |
|---|---|---|---|---|---|
| clip01_embeddings_men | baseline | 2/4 healthy | 1/3 undersplit | 1/3 undersplit | 1/2 undersplit |
| clip01_embeddings_men | A | 2/3 healthy | 2/2 healthy | 1/1 undersplit | 1/1 undersplit |
| clip01_embeddings_men | B | 2/2 healthy | 2/2 healthy | 1/1 undersplit | 1/1 undersplit |
| clip02_vadim_q | baseline | 3/3 healthy | 3/3 healthy | 3/3 healthy | 2/2 healthy |
| clip02_vadim_q | A | 3/3 healthy | 3/3 healthy | 2/2 healthy | 1/1 undersplit |
| clip02_vadim_q | B | 2/2 healthy | 2/2 healthy | 1/1 undersplit | 1/1 undersplit |
| clip03_woman_men | baseline | 3/3 healthy | 2/2 healthy | 2/2 healthy | 2/2 healthy |
| clip03_woman_men | A | 2/2 healthy | 2/2 healthy | 2/2 healthy | 2/2 healthy |
| clip03_woman_men | B | 2/2 healthy | 2/2 healthy | 2/2 healthy | 2/2 healthy |
| test_apartments | baseline | 3/7 healthy | 3/6 healthy | 3/5 healthy | 2/4 healthy |
| test_apartments | A | 4/5 healthy | 4/5 healthy | 3/3 healthy | 3/3 healthy |
| test_apartments | B | 3/3 healthy | 2/2 healthy | 2/2 healthy | 2/2 healthy |
| test_ninth | baseline | 3/4 healthy | 3/3 healthy | 3/3 healthy | 2/2 healthy |
| test_ninth | A | 3/3 healthy | 3/3 healthy | 2/2 healthy | 2/2 healthy |
| test_ninth | B | 2/2 healthy | 2/2 healthy | 2/2 healthy | 2/2 healthy |

**Tuner recommendation:** `0.85` fails the pack’s motivating clip (`clip01`). `0.80` is the only baseline threshold that yields two substantial clusters there. `0.88` glues `clip02` (top1 0.893) and apartments (top1 0.776). Prefer **0.80**, not 0.85, if local gold agrees the `clip01` 43 s / 14 s split is two men.

## Crumb merge prototype (≤2.5 s → nearest large centroid, iterative)

Compared with nearest-large-neighbor-by-time; both behave similarly on this pack. Tables below are **centroid**.

### Default 0.85 + crumb (harmful when already undersplit)

| clip | before n_id/n_sub/soft/top1 | after n_id/n_sub/soft/top1 |
|---|---|---|
| clip01_embeddings_men | 3/1/undersplit/0.960 | 1/1/undersplit/1.000 |
| clip02_vadim_q | 3/3/healthy/0.511 | 3/3/healthy/0.511 |
| clip03_woman_men | 2/2/healthy/0.550 | 2/2/healthy/0.550 |
| test_apartments | 5/3/healthy/0.556 | 3/3/healthy/0.567 |
| test_ninth | 3/3/healthy/0.537 | 3/3/healthy/0.537 |

`clip01` crumbs are leftover male pieces: merging them into the fat cluster makes undersplit **worse** (3 ids → 1).

### Recommended 0.80 + crumb

| clip | before | after centroid | residual crumbs | speech after |
|---|---|---|---|---|
| clip01_embeddings_men | 4/2/healthy/0.741 | 2/2/healthy/0.754 | 0 | `SPEAKER_00 42.64s, SPEAKER_01 13.92s` |
| clip02_vadim_q | 3/3/healthy/0.511 | 3/3/healthy/0.511 | 0 | `SPEAKER_00 18.77s, SPEAKER_01 5.25s, SPEAKER_02 25.14s` |
| clip03_woman_men | 3/3/healthy/0.550 | 3/3/healthy/0.550 | 0 | `SPEAKER_00 32.25s, SPEAKER_01 4.50s, SPEAKER_02 21.91s` |
| test_apartments | 7/3/healthy/0.523 | 3/3/healthy/0.579 | 0 | `SPEAKER_00 38.98s, SPEAKER_01 15.58s, SPEAKER_02 12.81s` |
| test_ninth | 4/3/healthy/0.497 | 4/3/healthy/0.497 | 0 | `SPEAKER_00 36.05s, SPEAKER_01 29.75s, SPEAKER_02 3.82s, SPEAKER_03 2.89s` |

All five clips land in the 2–4 substantial band. apartments 7→3 (crumbs gone after 2 passes). `test_ninth` keeps a 2.894 s id (above the 2.5 s crumb cut, below the 3 s substantial cut) — leave it or raise the crumb cut to 3 s locally.

**S3 recommendation:** ship as a **post-cluster** rule on long files, but only when substantial_count is already ≥2. Do not use crumbs to “clean” an undersplit 0.85 result. Offline prototype only (`cloud_out/scratch/`); no `src/` merge.py change in this run.

## Agent judgement

1. **Male glue is real on clip01 at the frozen 0.85.** One cluster holds 96% of speech; two ≤1.5 s crumbs. That matches the ticket pattern (fat `SPEAKER_00` + shards). Lowering the threshold to 0.80 splits 42.6 s vs 13.9 s after crumb merge — two substantial ids, still unequal. Local listeners must say whether that is two men or man + noise. I did not invent roles.
2. **clip02 does split at 0.85** (18.8 / 5.3 / 25.1 s). The “always one male id” story is clip-dependent. Coarser windows destroy this split.
3. **clip03 never collapsed to 1 id** in this grid. At 0.85: 32.3 s + 26.4 s. At 0.80: a third 4.5 s cluster appears. Woman-vs-men purity needs gold; the binary “not one pool” check passes.
4. **Regression clips stay in band** at 0.80–0.85. apartments over-produces raw ids (7 at 0.80) that crumb merge reduces to 3. ninth is already 3 substantial at 0.82–0.85.
5. **Not a WeSpeaker ceiling yet.** 0.85 fails clip01; 0.80 + crumb does not. Ceiling would mean even 0.80 cannot produce ≥2 substantial men on clip01 — that did not happen.
6. **TTFT:** packed clips are 60–85 s; diarize embed is 0.8–2.7 s. Extrapolating ~25 ms/window on this Xeon to ~15 min of speech is tens of seconds, far below the VPS field ~400–540 s diarize. This host is much faster than the 2 vCPU demo. Do not treat these walls as G5 numbers. If the VPS is per-call overhead bound, A/B might still help there — re-measure on that box. If it is per-sample bound, walls will stay flat as they did here. **S2 split+anchor remains the TTFT design**; this pack did not implement it.

## Recommendation (for local planner / HUMAN_GATE)

| Knob | Action |
|---|---|
| `diarization.embed.window_sec` / `step_sec` | **Keep 1.5 / 0.75** |
| `cluster_distance_threshold` | Try **0.80** (was 0.85). Confirm on private gold + a long meeting, not only these clips |
| Crumb merge ≤2.5 s → nearest large centroid | **Yes**, iterative, after clustering; skip if substantial_count < 2 |
| Coarser windows A/B | **No** for quality; speed win unproven on this CPU |
| Jina / packing D / pyannote | Not used, not recommended from this pack |
| S2 file split + centroid anchor | Still the TTFT lever; not run here |
| H0 warmup | Out of scope; `model_load_sec` ~0.2 s warm / ~2.1 s first process on this host (cached HF weights) |

## VAD (once per clip, reused)

| clip | duration_s | speech_s | regions | islands | vad_s |
|---|---:|---:|---:|---:|---:|
| clip01_embeddings_men | 60.000 | 54.708 | 9 | 6 | 0.234 |
| clip02_vadim_q | 60.000 | 46.432 | 13 | 11 | 0.138 |
| clip03_woman_men | 60.000 | 57.092 | 7 | 3 | 0.139 |
| test_apartments | 85.004 | 67.208 | 14 | 10 | 0.195 |
| test_ninth | 85.004 | 68.432 | 14 | 13 | 0.194 |

## Method

- Silero VAD + WeSpeaker ResNet34 ONNX + agglomerative cosine/average, same windowing as `src/transcriber/diarization/wespeaker.py`.
- Throwaway runner: `cloud_out/scratch/run_ttft_diar_grid.py`. No edits under `src/` or `config/`.
- Embeddings cached per (clip, preset); four thresholds clustered from the same matrix.
- Threads: `taskset -c 0,1`, `OMP_NUM_THREADS=2`, config `onnx_threads: 2`.
- Audio: only `cloud_in/inputs/{clips,regression}/*.wav` (16 kHz mono). Copied to `/tmp/d5-ttft-diar` so VAD does not write into the pack.
- Timelines: `cloud_out/timelines/*.json` for local review.

## Deviations and blockers

- 15-minute meeting **not packed** — no direct TTFT / 15′ diarize wall.
- Host is 4× Intel Xeon, 16 GiB; experiment pinned to 2 cores. Not the demo VPS.
- First process `model_load_sec=2.114` (HF weights already cached after download); this results.json is the repeat (`0.186` s load, wall 27.1 s, peak RSS 287 MiB).
- No gold, no listening pass, no invented speaker roles.
- `test_ninth` 2.894 s leftover at 0.80 is between crumb (2.5) and substantial (3.0) cuts.
- Gemini/ASR/Jina/H0/S2 production: not run (stop-list).

## Files

| path | what |
|---|---|
| `cloud_out/results.json` | full grid + crumb |
| `cloud_out/timelines/` | per-cell turns |
| `cloud_out/scratch/run_ttft_diar_grid.py` | runner |
| `cloud_out/scratch/run.log` | stdout |
| `cloud_out/run_meta.json` | host / versions |

