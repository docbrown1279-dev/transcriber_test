# D5.diar-spectral — AHC vs spectral vs hybrid (same WeSpeaker embeddings)

Research-only run on packed clips. No production `src/` / `config/` edits, no ASR, no LLM, no `eval/` gold, no crumb merge as a method, no speaker-count prior in [2, 4].

**Verdict:** global **spectral + eigengap (M1)** recovers the clip01 ~42–45 s solo cluster that frozen AHC `distance_threshold=0.85` swallows, without crumbs and without forcing K. It also keeps three substantial ids on `test_apartments`. It does **not** keep the short ~3.8 s third id on `test_ninth` that AHC 0.85 still has. **Hybrid M2** as a block re-cluster oversplits (5–31 ids). Local-neighborhood M2 is nearly a no-op on 0.85 seeds and does not unglue clip01. **Anchor→assign (M3)** collapses clip01 to one id. Threshold / algorithm changes do not move wall time; embed dominates. Recommendation for local HUMAN_GATE: try **M1 spectral** as a clustering replacement, with a listen on clip01’s 15 s second cluster and ninth’s missing short id — do not ship M2/M3 as implemented.

## Soft focus (not gold, not a K prior)

| clip | what to look at |
|---|---|
| clip01 | short solo greeting ~42–45 s: does any method keep a **non-top1** cluster on that interval? |
| test_ninth / test_apartments | does a shorter secondary id survive, or does everything glue into one pool? |

Speaker roles are **not** named here. Counts are raw `n_id` after production `merge_turns` (gap 0.3 s / absorb <1.0 s). `crumb_count_lt3s` is **log-only**; crumbs were not merged.

## Method

- Silero VAD + WeSpeaker ResNet34 ONNX windows **1.5 / 0.75**, same as `src/transcriber/diarization/wespeaker.py`.
- Embed **once per wav**; cluster M0/M1/M2/M3 on that matrix.
- M0: AHC cosine + average, `distance_threshold` ∈ {0.80, 0.85, 0.88}.
- M1: k-NN cosine affinity (`k=min(10,n−1)`), symmetric normalized Laplacian, **eigengap** K with cap 20 (K=1 allowed).
- M2: AHC 0.85 look-1, then (a) `M2_hybrid` = spectral inside change-point **blocks** + local neighborhoods; (b) `M2_local` = neighborhoods only; extra `M2_hybrid_seed0.80`.
- M3: cluster “stable” consecutive-cosine anchors with spectral; assign the rest to nearest centroid.
- Threads: `taskset -c 0,1`, `OMP_NUM_THREADS=2`, ONNX intra/inter op 2. Host `nproc=2` (cgroup) / 4 CPUs online.
- Audio: only `cloud_in/inputs/{clips,regression}/*.wav`. Work copies under `/tmp/d5-diar-spectral`.

## Timing (cold load vs embed vs cluster)

First process (cold `SpeakerEmbedder` construct, weights already on disk): `model_load_sec=2.089`. Repeat process (this `results.json`): `model_load_sec=0.184`.

`timing_5min.wav` (300 s, 277.9 s speech, **366 windows**) processed **twice in one process** after load:

| process | pass | embed_sec | n_windows | ms/window |
|---|---|---:|---:|---:|
| first (cold load 2.089 s) | 1 | 11.679 | 366 | 31.9 |
| first | 2 | 16.703 | 366 | 45.6 |
| repeat (load 0.184 s) | 1 | 11.596 | 366 | 31.7 |
| repeat | 2 | 11.567 | 366 | 31.6 |

Warm **embed is not faster** than the first embed after load. The first-process pass-2 spike (16.7 s) looks like host jitter; the repeat pair is flat. Cluster time is 5–255 ms depending on method:

| method | 5 min pass1 cluster_sec | 5 min pass2 cluster_sec | 5 min raw n_labels |
|---|---:|---:|---:|
| M0_thr0.80 | 0.044 | 0.008 | 5 |
| M0_thr0.85 | 0.005 | 0.005 | 3 |
| M0_thr0.88 | 0.005 | 0.005 | 3 |
| M1_spectral | 0.121 | 0.125 | 3 |
| M2_hybrid | 0.255 | 0.257 | 28 |
| M2_local | 0.030 | 0.032 | 6 |
| M3_anchor | 0.008 | 0.006 | 3 |

`concat_01_02_03.wav` (180 s) embed once: **201 windows**, 11.671 s this process (first process logged 6.375 s — same jitter). ~32–58 ms/window. **Changing AHC threshold does not change wall** in any meaningful way; embed is ~50–2000× cluster.

This host is a 4-core Xeon / 16 GiB pinned to 2 cores. Do not treat these walls as G5 2vCPU-VPS numbers.

## Quality — clip01 / 02 / 03 / apartments / ninth

Windows: clip01 72, clip02 52, clip03 76, apartments 83, ninth 89.

| clip | method | n_id | crumbs&lt;3s | top1 | speech_sec per id |
|---|---|---:|---:|---:|---|
| clip01 | M0_thr0.80 | 4 | 2 | 0.741 | 41.89 / 12.42 / 1.50 / 0.75 |
| clip01 | M0_thr0.85 | 3 | 2 | 0.960 | 54.31 / 1.50 / 0.75 |
| clip01 | M0_thr0.88 | 2 | 1 | 0.973 | 55.06 / 1.50 |
| clip01 | **M1_spectral** | **2** | **0** | **0.730** | **41.30 / 15.27** |
| clip01 | M2_hybrid | 5 | 2 | 0.749 | 42.38 / 1.50 / 7.93 / 0.75 / 4.00 |
| clip01 | M2_local | 3 | 2 | 0.960 | 54.31 / 1.50 / 0.75 (same as M0 0.85) |
| clip01 | M2_hybrid_seed0.80 | 10 | 5 | 0.475 | oversplit |
| clip01 | M3_anchor | 1 | 0 | 1.000 | 56.56 |
| clip02 | M0 0.80 / 0.85 | 3 | 0 | 0.511 | 18.77 / 5.25 / 25.14 |
| clip02 | M0_thr0.88 | 2 | 0 | 0.893 | 43.91 / 5.25 |
| clip02 | M1_spectral | 2 | 0 | 0.603 | 19.52 / 29.64 |
| clip02 | M2_hybrid | 8 | 2 | 0.284 | oversplit |
| clip02 | M2_local | 3 | 0 | 0.511 | same as M0 0.85 |
| clip02 | M3_anchor | 2 | 0 | 0.557 | 21.77 / 27.39 |
| clip03 | M0_thr0.80 | 3 | 0 | 0.550 | 32.25 / 4.50 / 21.91 |
| clip03 | M0 0.85 / 0.88 / M1 | 2 | 0 | 0.550 | 32.25 / 26.41 |
| clip03 | M2_hybrid | 4 | 1 | 0.447 | 26.25 / 1.50 / 6.00 / 24.91 |
| clip03 | M2_local | 2 | 0 | 0.550 | same as M0 0.85 |
| clip03 | M3_anchor | 2 | 0 | 0.706 | 41.43 / 17.23 |
| apartments | M0_thr0.80 | 7 | 4 | 0.523 | 35.23 / 14.08 / 1.50 / 2.25 / 12.81 / 0.75 / 0.75 |
| apartments | M0_thr0.85 | 5 | 2 | 0.556 | 37.48 / 14.83 / 1.50 / 12.81 / 0.75 |
| apartments | M0_thr0.88 | 4 | 2 | 0.776 | 52.30 / 1.50 / 12.81 / 0.75 |
| apartments | **M1_spectral** | **3** | **0** | **0.579** | **38.98 / 15.58 / 12.81** |
| apartments | M2_hybrid | 9 | 1 | 0.357 | oversplit |
| apartments | M2_local | 4 | 1 | 0.567 | 38.23 / 14.08 / 1.50 / 13.56 |
| apartments | M3_anchor | 2 | 0 | 0.754 | 50.80 / 16.56 |
| ninth | M0_thr0.80 | 4 | 1 | 0.497 | 36.05 / 29.75 / 3.82 / 2.89 |
| ninth | **M0_thr0.85** | **3** | **0** | **0.537** | **38.95 / 29.75 / 3.82** |
| ninth | M0_thr0.88 | 2 | 0 | 0.537 | 38.95 / 33.57 |
| ninth | M1_spectral | 2 | 0 | 0.547 | 39.70 / 32.82 |
| ninth | M2_hybrid | 12 | 6 | 0.351 | oversplit |
| ninth | M2_local | 3 | 0 | 0.537 | same as M0 0.85 |
| ninth | M3_anchor | 2 | 0 | 0.537 | 38.95 / 33.57 |

## clip01 greeting interval [42, 45] s

Overlap of merged turns with [42, 45] (2.748 s of speech in that 3 s; the rest is non-speech). `distinct` = the interval is **not** only the global top-1 id.

| method | distinct from top1? | id on [42,45] | that id’s global speech_s |
|---|---|---|---:|
| M0_thr0.80 | yes | SPEAKER_01 | 12.42 |
| M0_thr0.85 | **no** (swallowed) | SPEAKER_00 | 54.31 |
| M0_thr0.88 | **no** | SPEAKER_00 | 55.06 |
| **M1_spectral** | **yes** | SPEAKER_01 | **15.27** |
| M2_hybrid (blocks) | **no** | SPEAKER_00 | 42.38 |
| M2_local | **no** | SPEAKER_00 | 54.31 |
| M2_hybrid_seed0.80 | yes (but 10 ids) | SPEAKER_04 | 9.17 |
| M3_anchor | **no** | SPEAKER_00 | 56.56 |

Window-level cosine on clip01 drops to **0.198** between the window ending 41.62 s and the window [42.25, 43.75] — the embedding actually changes at the greeting. Frozen AHC 0.85 still labels those windows as the main cluster. M1 labels [42.25, 47.50] as the second cluster.

M1’s second cluster is **15.3 s**, not a 3 s crumb: whoever speaks at 42–45 s also has other windows in that cluster. Local gold should confirm whether that is one short greeter or a second talker with more speech.

## Concat 01|02|03 (offsets 0 / 60 / 120)

| method | n_id | crumbs | top1 | slice n_id (01 / 02 / 03) |
|---|---:|---:|---:|---|
| M0_thr0.80 | 9 | 5 | 0.369 | 4 / 5 / 5 |
| M0_thr0.85 | 6 | 2 | 0.369 | 4 / 4 / 4 |
| M0_thr0.88 | 2 | 0 | 0.789 | 2 / 2 / 2 (clip01+02 almost one id) |
| **M1_spectral** | **4** | **0** | **0.361** | **3 / 4 / 3** |
| M2_hybrid | 29 | 13 | 0.164 | 13 / 9 / 10 |
| M2_local | 7 | 3 | 0.369 | (near M0 0.85) |
| M3_anchor | 3 | 0 | 0.460 | 3 / 3 / 3 |

M1 on the concat is the only method that stays at a small id count **without** gluing clip01+02 into one fat speaker (M0 0.88 top1 0.789). Slice speech is in `results.json` / timelines.

## Eigengap (M1) — no [2, 4] prior

Largest Laplacian gap chooses K; cap 20 never bound.

| clip | K | gap at chosen K | next-smaller competing gap | lap evals head |
|---|---:|---:|---:|---|
| clip01 | 2 | 0.218 (k=2) | 0.179 (k=1) | 0.00, 0.18, 0.40, … |
| clip02 | 2 | 0.325 | 0.218 (k=3) | 0.00, 0.03, 0.35, … |
| clip03 | 2 | 0.308 | 0.158 (k=3) | 0.00, 0.01, 0.32, … |
| concat | 4 | 0.202 | 0.108 (k=3) | 0.00, 0.01, 0.02, 0.13, 0.33, … |
| apartments | 3 | 0.252 | 0.107 (k=5) | 0.00, 0.03, 0.12, 0.37, … |
| ninth | 2 | 0.363 | 0.049 (k=1) / 0.031 (k=3) | 0.00, 0.05, 0.41, … |

Ninth’s gap after two clusters is huge; the ~3.8 s AHC-third is not a spectral component. That is an algorithm disagreement, not a cap artifact.

M3 eigengap on **anchors only** chose K=1 on clip01 (20 stable windows of the main talker). Greeting windows have low neighbor cosine, so they are not anchors and get assigned to the single centroid.

## Why hybrid failed the greeting

- `M2_hybrid` (block spectral): AHC 0.85 puts the greeting **inside** the fat cluster. Splitting the timeline at AHC change points peels crumbs into short blocks; the remaining long block is more homogeneous, so local eigengap does not isolate 42–45 s. Result: still swallowed, plus extra fragments (7.9 s / 4.0 s).
- `M2_local`: 4 AHC changes on clip01; every neighborhood came back K=1 (`local_neighborhoods_applied=0`). Identical to M0 0.85.
- Seeding hybrid from 0.80 recovers a distinct greeting id but **oversplits to 10**.

Hybrid here is either a no-op or a fragmenter. Global spectral is the algorithm that helps.

## Agent judgement

1. **M1 does recover a non-top1 cluster on clip01 [42, 45]**, matching the pack’s motivating case. Frozen AHC 0.85 / 0.88 and M3 do not. AHC 0.80 also recovers it (12.4 s second id) but with two crumbs; M1 is the clean two-id version (41.3 / 15.3, 0 crumbs).
2. **Apartments:** M1 keeps **three** ids (39.0 / 15.6 / 12.8) and drops the crumb storm that AHC 0.80 produces (7 ids). M3 and AHC 0.88 glue toward two, with top1 0.75–0.78.
3. **Ninth:** the historically fragile short id (~3.8 s at AHC 0.85) **survives AHC 0.85 and M2_local, dies under M1 / M3 / AHC 0.88**. Spectral is not a free upgrade on short secondaries.
4. **clip02 / clip03:** M1 stays at two substantial clusters; it merges AHC 0.85’s extra 5.25 s id on clip02 into the pair. clip03 M1 equals AHC 0.85 (32.3 / 26.4). Second cluster is not swallowed.
5. **M2 block-hybrid is not usable** (8–31 ids on these short files; 28 labels on 5 min). Do not take it to HUMAN_GATE as a product candidate.
6. **Wall:** load ~2.1 s cold / 0.18 s repeat; 5 min embed ~11.6 s @ 2 threads; cluster ≪ 0.3 s. No reason to pick a clustering algorithm for speed.

## Recommendation (local HUMAN_GATE only)

| Knob | Action |
|---|---|
| Windows 1.5 / 0.75 | Keep (prior pack; not re-opened) |
| Clustering | **Listen to M1 spectral** vs current AHC 0.85, especially clip01 [42,45] and ninth’s 3.8 s id |
| AHC 0.80 | Still a fallback that splits clip01; crumbs remain unless a later rule is accepted (out of scope here) |
| M2 hybrid / M3 | **Do not ship** as implemented |
| K ∈ [2, 4] prior | **Do not add** — eigengap already picked 2–4 on this pack without it; ninth’s K=2 is the disagreement to review, not a reason to clamp |
| Crumb ≤3 s merge | Not used; logging only. Do not bring it back as the primary fix |
| Production PR | None from this run |

Listen pass (local gold, not done here): (1) is clip01’s M1 SPEAKER_01 (15.3 s) the greeter, a second man, or mixed? (2) is ninth’s 3.8 s AHC id a real speaker you still want after M1 glues it?

## VAD (once per file)

| clip | duration_s | speech_s | regions | islands | vad_s |
|---|---:|---:|---:|---:|---:|
| clip01 | 60.000 | 54.708 | 9 | 6 | 0.193 |
| clip02 | 60.000 | 46.432 | 13 | 11 | 0.146 |
| clip03 | 60.000 | 57.092 | 7 | 3 | 0.144 |
| concat_01_02_03 | 180.000 | 158.180 | 27 | 18 | 0.438 |
| test_apartments | 85.004 | 67.208 | 14 | 10 | 0.205 |
| test_ninth | 85.004 | 68.432 | 14 | 13 | 0.208 |
| timing_5min | 300.000 | 277.932 | 32 | 22 | 0.729 |

## Deviations and blockers

- Repeat process overwrote `results.json` after adding `M2_local`; cold `model_load_sec=2.089` is kept under `process_timing` and in `run_meta.json`.
- 5 min pass-2 embed on the first process was slower (16.7 s); repeat pair is flat ~11.6 s. Reported both.
- Concat embed jitter 6.4 s vs 11.7 s across processes. Same 201 windows.
- No gold, no listening pass, no invented roles.
- Gemini/ASR/Jina/second embedder/crumb-primary/K-prior: not run (stop-list).
- `nproc=2` in this cgroup; `taskset -c 0,1` matches.

## Files

| path | what |
|---|---|
| `cloud_out/results.json` | full quality + timing + greeting overlap |
| `cloud_out/timelines/` | per clip × method turns |
| `cloud_out/scratch/run_d5_diar_spectral.py` | runner |
| `cloud_out/scratch/run_stdout.txt` | first process (cold load) |
| `cloud_out/scratch/run_stdout_repeat.txt` | repeat process |
| `cloud_out/run_meta.json` | host / versions |
