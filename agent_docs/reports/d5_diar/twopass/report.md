# D5.diar-twopass — VAD units + WeSpeaker fine (overlap vs none vs one-embed)

Research-only run on packed clips. No production `src/` / `config/` edits, no ASR, no LLM, no `eval/` gold, no crumb-primary method, no K∈[2,4] prior, no second DNN. Cheap stage-1B/1C features are **MFCC + spectral flux + energy** (numpy/scipy), not WeSpeaker.

**Verdict:** Glue `<1 s` barely changes the VAD skeleton (`n_islands` → `n_units` drops by 1–4). **2C (one WeSpeaker per glued unit + frozen AHC 0.85) is not demo-quality:** it collapses clip01/02/03, concat, and ninth to **1 id**. The same unit vectors with **adjacent cosine 0.40/0.55 (1A)** keep clip01’s ~42–45 s greeting as a 7.2 s non-top1 block — AHC 0.85 merges it because the greeting-boundary cosine distance is ~0.81 `< 0.85`. **Cheap 1B/1C are not useful as a WeSpeaker stand-in:** unit-level cheap cosine sits at 0.91–0.97 even across speaker changes; change-point 1C oversplits (tens of ids); cheap spectral 1C partitions texture, not speakers. **Dropping overlap (2B) cuts `n_embed_calls` 366→193 on 5 min and isolates the clip01 greeting that 2A swallows**, but it adds crumbs and is messier on apartments/ninth. **Keep 2A overlap as the quality baseline** unless local gold prefers 2B’s greeting split. Do not ship 2C+AHC0.85 or cheap 1B/1C.

## Soft focus (not gold)

| clip | what to look at |
|---|---|
| clip01 | ~42–45 s short greeting — isolate from the main id? |
| ninth | short secondary (~3.8 s on 2A AHC 0.85) — survive or glue? |

No invented speaker names. Local humans score private gold after ingest.

## Shared preprocess

Silero (demo: thr 0.45, `min_silence_ms=350`) → islands with `vad_premerge_gap_sec=0.5` → **units** by gluing islands `< 1.0 s` (append to previous; leading shorts into next; a run of shorts with no large neighbor → one unit). Embed of a multi-island unit concatenates **speech only**.

| clip | n_regions | n_islands | n_units | islands `<1s` | speech_s | island duration hist (0.5–1 / 1–2 / 2–4 / 4–8 / 8–16 / 16+) |
|---|---:|---:|---:|---:|---:|---|
| clip01 | 9 | 6 | 5 | 1 | 56.0 | 1 / 0 / 1 / 2 / 1 / 1 |
| clip02 | 13 | 12 | 10 | 2 | 46.8 | 1 / 3 / 2 / 2 / 3 / 0 |
| clip03 | 7 | 3 | 3 | 0 | 58.7 | 0 / 0 / 0 / 1 / 1 / 1 |
| concat | 27 | 19 | 17 | 2 | 161.4 | 1 / 3 / 3 / 4 / 5 / 2 |
| apartments | 14 | 12 | 10 | 2 | 68.1 | 0 / 2 / 1 / 5 / 1 / 1 |
| ninth | 14 | 13 | 9 | 4 | 68.8 | 2 / 1 / 3 / 1 / 3 / 1 |
| timing_5min | 32 | 22 | 21 | 1 | 282.0 | 1 / 0 / 3 / 5 / 5 / 8 |

Glue is mild. clip01 greeting sits in **its own unit** `[42.25, 49.43]` (7.18 s, 1 island) — VAD already cut it; 1A/2C do not need a split inside that island. ninth glues four sub-1 s islands into neighbors (13→9 units); the 2.3 s unit at 51.4–53.7 s stays unglued.

Stage 2 **starts from production-like islands** (not 1A/1B merged labels). 2C clusters the glued units. Stage 1 timelines are sequential draft labels **without** absorb; stage 2 uses production absorb 1.0 s / same-speaker gap 0.3 s.

## Timing (`timing_5min.wav`, 300 s)

Pinned `OMP/MKL/ORT` to **2 threads**. WeSpeaker ResNet34 ONNX. This process `model_load_sec=0.191` (warm; a prior construct in the same VM was **2.345 s** cold with weights on disk). Cluster time is milliseconds. Embed dominates.

| method | n_embed_calls | embed_sec | cluster_sec | n_windows / n_units | ms/call |
|---|---:|---:|---:|---:|---:|
| 1A unit WeSpeaker | **21** | 3.033 | ~0 | 21 units | 144 |
| 1B cheap adjacent | **0** | 0 | — | 21 units | cheap 0.17 s |
| 1C cheap subwindows | **0** | 0 | — | 374 subwindows | cheap 0.17 s |
| **2A overlap 1.5/0.75** | **366** | **5.940** | 0.006 | 366 windows | 16.2 |
| **2B no-overlap 1.5** | **193** | **3.087** | 0.002 | 193 windows | 16.0 |
| **2C one embed / unit** | **21** | **3.033** | 0.000 AHC / 0.004 spectral | 21 units | 144 |

Hypothesis **holds on call count:** `2C (21) ≪ 2B (193) < 2A (366)`. Wall time does **not** drop 17×: 2C embeds long concatenated speech (~13 s mean) so ms/call is 9× 2A’s 1.5 s windows. **2C and 2B are ~3.0 s embed; 2A is ~5.9 s** (~1.9×). Coarse 3.0/1.5 windows were already rejected as a speed lever; this run does not repeat them.

2A window count **366** matches the previous D5.diar-spectral 5 min pass. Full research wall 36.4 s, peak RSS 544 MB (quality clips + 5 min, one process).

Host: 4-core Xeon, 16 GiB, not a G5 2vCPU VPS.

## Stage 1 — draft

Adjacent WeSpeaker cosine on units (clip01 min **0.189**, median 0.48). Cheap unit cosine is much higher (clip01 min 0.87, median 0.96) — **not the same scale, not WeSpeaker**.

| clip | method | n_id | crumbs&lt;3s | top1 | notes |
|---|---|---:|---:|---:|---|
| clip01 | **1A cos 0.40 / 0.55** | **3** | 0 | 0.70 | greeting = 7.18 s non-top1 |
| clip01 | 1A cos 0.70 | 4 | 0 | 0.57 | extra split before greeting |
| clip01 | 1B cheap 0.80 | 1 | 0 | 1.00 | all merged |
| clip01 | 1B cheap 0.90 | 2 | 0 | 0.83 | greeting still in top1 |
| clip01 | 1B cheap 0.96 | 3 | 0 | 0.52 | splits late, not a clean greeter |
| clip01 | 1C_cp 0.80–0.96 | 26–64 | 19–62 | ≤0.13 | oversplit |
| clip01 | 1C_spec cheap | 4 | 0 | 0.28 | greeting mixed across 3 of 4 ids |
| clip02 | 1A 0.40/0.55 | 6 | 3 | 0.45 | sequential ids; returning speaker ≠ reused |
| clip02 | 1B 0.80 | 2 | 0 | 0.53 | |
| clip03 | 1A all thr | 2 | 0 | 0.65 | only 3 units; WeSpeaker min cosine 0.13 |
| clip03 | 1B 0.80/0.90 | 1 | 0 | 1.00 | cheap cannot see the 0.13 WeSpeaker dip |
| apartments | 1A 0.40 | 6 | 3 | 0.75 | oversplit vs 2A’s 3 substantial ids |
| ninth | 1A 0.40/0.55 | 6 | 3 | 0.53 | sequential; shorts 1.4–2.8 s kept as own ids |
| ninth | 1B 0.80 | 1 | 0 | 1.00 | cheap glue |

**1A** is a useful **draft of change points**, not a diarizer: it never reattaches a returning speaker (clip02 6 ids vs 2A’s 3). Sensitivity is light: 0.40 and 0.55 agree on clip01/02/03/ninth; 0.70 only adds splits.

**1B** adjacent cheap cosine is the wrong signal for speaker identity on this pack.

**1C** change-point on 0.75 s cheap tiles fires inside a single talker (subwindow cosine min is **negative** on clip01/02/03). Cheap spectral eigengap (K not forced into 2–4) yields 2–4 global blobs that do not match 2A speaker structure.

## Stage 2 — WeSpeaker fine

2A = production windowing `1.5/0.75` + AHC 0.85. 2B = **strict non-overlap 1.5 s tiles** inside islands (island ≤1.5 s → one window; remainder ≥ `min_embed` 0.4 s kept). 2C = one embed per glued unit → AHC 0.85; optional spectral on the same vectors.

| clip | method | n_id | crumbs&lt;3s | top1 | speech_s per id (sorted by id) |
|---|---|---:|---:|---:|---|
| clip01 | 2A overlap | 3 | 2 | 0.960 | 54.31 / 1.50 / 0.75 |
| clip01 | **2B no-overlap** | **2** | **0** | 0.802 | 45.34 / **11.18** |
| clip01 | 2C unit AHC 0.85 | 1 | 0 | 1.000 | 56.56 |
| clip01 | 2C unit spectral | 1 | 0 | 1.000 | 56.56 |
| clip02 | 2A | 3 | 0 | 0.511 | 18.77 / 5.25 / 25.14 |
| clip02 | 2B | 3 | 0 | 0.452 | 14.84 / 12.12 / 22.20 |
| clip02 | 2C AHC / spectral | 1 | 0 | 1.000 | 49.16 |
| clip03 | 2A | 2 | 0 | 0.550 | 32.25 / 26.41 |
| clip03 | 2B | 3 | 1 | 0.537 | 31.50 / 1.50 / 25.66 |
| clip03 | 2C | 1 | 0 | 1.000 | 58.66 |
| apartments | 2A | 5 | 2 | 0.556 | 37.48 / 14.83 / 1.50 / 12.81 / 0.75 |
| apartments | 2B | 6 | 3 | 0.540 | 35.94 / 14.08 / 1.50 / 1.50 / 11.00 / 2.56 |
| apartments | **2C AHC** | **2** | **0** | 0.745 | **52.86 / 18.06** |
| apartments | 2C spectral | 1 | 0 | 1.000 | 70.92 |
| ninth | **2A** | **3** | **0** | 0.537 | 38.95 / 29.75 / **3.82** |
| ninth | 2B | 4 | 1 | 0.516 | 37.45 / 29.75 / **3.82** / 1.50 |
| ninth | 2C | 1 | 0 | 1.000 | 72.52 |

### clip01 greeting [42, 45]

2.748 s of speech in the 3 s window.

| method | distinct from top1? | id on [42,45] | that id’s global speech_s |
|---|---|---|---:|
| 1A cos 0.40/0.55 | **yes** | SPEAKER_01 | **7.18** (exactly the VAD unit) |
| 1B cheap 0.80/0.90 | no | SPEAKER_00 | 56 / 47 |
| 1C_spec cheap | yes (mixed) | 3 ids | not a single greeter |
| **2A overlap AHC 0.85** | **no (swallowed)** | SPEAKER_00 | 54.31 |
| **2B no-overlap** | **yes** | SPEAKER_01 | **11.18** (greeting + other 2B windows) |
| 2C unit AHC/spectral | no | SPEAKER_00 | 56.56 |

2A still labels [42.25, 45.25] as the main speaker (1.5 s crumb at 45.25–46.75 is not the greeting). 2B puts the whole `[42.25, 49.43]` unit on SPEAKER_01, then also assigns SPEAKER_01 to 38.9–40.4 and 57.5–60 — local gold should check whether that 11 s blob is one greeter or leakage.

2C merges the greeting unit because unit-adjacent cosine **0.189 ⇒ distance 0.811 &lt; 0.85**. Frozen demo AHC 0.85 is calibrated for **overlapping 1.5 s windows**, not 5–20 long unit vectors.

### ninth short secondary

2A keeps a **3.82 s** third id (same as the previous spectral-pack AHC 0.85 result). 2B keeps that 3.82 s and adds a **1.5 s crumb**. 2C glues everything to one id — the short secondary does **not** survive unit-level AHC 0.85. Glue itself did not delete a 3.8 s island; clustering did.

### concat 01|02|03 (offsets 0 / 60 / 120)

| method | n_id | crumbs | slice n_id (01 / 02 / 03) |
|---|---:|---:|---|
| 2A overlap | 6 | 2 | 4 / 4 / 4 |
| 2B no-overlap | 3 | 0 | 2 / 3 / 3 |
| 2C unit AHC | 1 | 0 | 1 / 1 / 1 |
| 1A cos 0.55 | 10 | 3 | 4 / 6 / 2 |

2C cannot keep clip identity across the concat. 2B is more collapsed than 2A (3 vs 6 global ids).

## Answers to the prompt

1. **Keep overlap?** For demo **quality**, yes as default (2A still the only method here that both matches prior 5 min window count and keeps ninth’s 3.8 s third id plus three substantial apartments ids). Overlap is **not** required for wall time: 2B is ~48% of 2A embed seconds. If local gold likes 2B’s clip01 greeting more than it dislikes extra crumbs, 2B is the speed/quality compromise — not 2C.
2. **Is cheap 1B/1C useful?** **No** as a speaker draft. Use 1A (WeSpeaker, one call per unit) if a cheap *structure* pass is needed. Do not call 1B/1C “spectral diarization.”
3. **Is 2C enough for demo quality?** **No** with AHC `distance_threshold=0.85`. Call count is excellent (21 vs 366); quality collapses. A tighter unit-level threshold or **1A adjacent keep** on the same embeds would be a different method, not this 2C.

## Artifacts

- `cloud_out/results.json` — preprocess, adjacent cosine stats, quality, `timing_5min`
- `cloud_out/run_meta.json` — host, wall, RSS, `n_embed` 2A/2B/2C
- `cloud_out/timelines/{clip}__{method}.json` — quality clips (not the 5 min file)
- `cloud_out/scratch/run_d5_diar_twopass.py` — throwaway runner

## Deviations

- 2B uses strict non-overlap tiles, not production’s `dur <= window+step` shortcut (that shortcut with step=1.5 would treat islands ≤3 s as a single embed).
- Nested `islands` lists inside each unit were stripped from `results.json` by the serializer (`islands` key); `n_islands` per unit and island duration lists remain.
- Concat was scored (cheap enough). No gold. Crumb counts are log-only.
