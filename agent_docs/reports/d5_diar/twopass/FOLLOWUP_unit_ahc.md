# Follow-up — tune 2C unit AHC / centroids / long-loud anchors

Research-only. Same packed clips and same glue `<1 s` VAD units as `cloud_out/report.md` @ `d951a08`. No cheap 1B/1C, no 3.0/1.5 windows, no AHC 0.85 redo, no eval/gold, no production `src/` edits.

**Verdict: REFUSED as a 2A substitute → next lever is file-split (or keep overlap 2A).** Tightening unit-level AHC **does** stop the 0.85 collapse and **does** isolate clip01’s ~42–45 s greeting as a single 7.18 s non-top1 id (T1 0.50–0.75). No operating point is ≈2A on the rest of the pack at once: thresholds that keep ninth’s third id and the greeting **undersplit clip02 (2 vs 2A’s 3)** and **merge apartments’ third substantial id** (0.65+). T2/T3 do not fix that. Embed count stays **21 vs 2A’s 366** on `timing_5min` (same as prior 2C). T3 is almost a no-op here: most units are already ≥3 s (5 min: 20/21 anchors).

## Timing (`timing_5min.wav`)

One WeSpeaker pass over glued units, then CPU clustering (≪1 ms). 2A window embeds were **not** re-run.

| method | n_embed_calls | embed_sec | cluster_sec | notes |
|---|---:|---:|---:|---|
| **2A prior** overlap 1.5/0.75 + AHC 0.85 | **366** | **5.940** | 0.006 | quality baseline |
| **2C prior** unit + AHC 0.85 | **21** | **3.033** | ~0 | collapsed many clips to 1 id |
| **T1/T2/T3 this run** (shared unit embeds) | **21** | **2.951** | ≤0.001 | same call count as 2C |

T3 still embeds short units so they can be compared to centroids (`new-speaker` thr). It does **not** reduce `n_embed_calls` below 2C.

`model_load_sec=0.222` (warm). Wall 10.3 s, peak RSS 533 MB. 2 ONNX threads.

## Soft-focus scorecard

| check | 2A prior | T1 0.50–0.55 | **T1 0.60** | T1 0.65–0.70 | T1 0.75–0.80 | T2 0.40 | T2 0.70 |
|---|---|---|---|---|---|---|---|
| clip01 greeting non-top1, one id | **no** (swallowed) | **yes** 7.18 s | **yes** 7.18 s | **yes** 7.18 s | 0.75 yes / **0.80 no** | **yes** | **yes** (plus extra split) |
| clip02 not 1 id | 3 ids | 5 / 4 (crumbs) | **2** | **2** | **1 — fail** | 4 crumbs | 8 oversplit |
| clip03 not 1 id | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| ninth short secondary | **3.82 s**, 3 ids | 4 ids, 4.71 s | 4 ids, 4.71 s | **3 ids, 4.71 s** | **2 ids — fail** | 3 ids, 4.71 s | 6 ids |

Least-bad **listen** candidate for local gold: **T1 AHC 0.60** (or 0.65 if ninth’s 3-id shape matters more than apartments). Not a ship.

## T1 — AHC grid on unit embeddings (skip 0.85)

Cosine **distance** threshold. Prior greeting-boundary distance was ~0.81, so 0.85 merged; **0.80 still merges clip01**; 0.75 keeps the greeting but already collapses clip02.

| clip | method | n_id | crumbs&lt;3s | top1 | speech_s per id |
|---|---|---:|---:|---:|---|
| clip01 | 2A prior | 3 | 2 | 0.960 | 54.31 / 1.50 / 0.75 |
| clip01 | T1 0.50–0.75 | **2** | 0 | 0.873 | 49.39 / **7.18** |
| clip01 | T1 0.80 | 1 | 0 | 1.000 | 56.56 |
| clip02 | 2A prior | 3 | 0 | 0.511 | 18.77 / 5.25 / 25.14 |
| clip02 | T1 0.50 | 5 | 3 | 0.588 | 28.89 / 2.18 / 1.26 / 15.42 / 1.42 |
| clip02 | T1 0.55 | 4 | 2 | 0.588 | 28.89 / 17.60 / 1.26 / 1.42 |
| clip02 | T1 0.60–0.70 | **2** | 0 | 0.588 | 28.89 / 20.27 |
| clip02 | T1 0.75–0.80 | **1** | 0 | 1.000 | 49.16 |
| clip03 | 2A prior | 2 | 0 | 0.550 | 32.25 / 26.41 |
| clip03 | T1 all 0.50–0.80 | **2** | 0 | 0.648 | 37.99 / 20.67 |
| apartments | 2A prior | 5 | 2 | 0.556 | 37.48 / 14.83 / 1.50 / **12.81** / 0.75 |
| apartments | T1 0.60 | 5 | 1 | 0.362 | 21.58 / 25.70 / 18.06 / 3.82 / 1.77 |
| apartments | T1 0.65 | 4 | 1 | 0.667 | **47.27** / 18.06 / 3.82 / 1.77 |
| apartments | T1 0.70–0.75 | 3 | 1 | 0.720 | 51.09 / 18.06 / 1.77 |
| apartments | T1 0.80 | 2 | 0 | 0.745 | 52.86 / 18.06 |
| ninth | 2A prior | 3 | 0 | 0.537 | 38.95 / 29.75 / **3.82** |
| ninth | T1 0.50–0.60 | 4 | 1 | 0.533 | 38.66 / 27.06 / 2.09 / **4.71** |
| ninth | T1 0.65–0.70 | **3** | 0 | 0.533 | 38.66 / 29.15 / **4.71** |
| ninth | T1 0.75–0.80 | 2 | 0 | 0.533 | 38.66 / 33.86 |
| concat | 2A prior | 6 | 2 | 0.369 | 60.4 / 21.0 / 1.5 / 33.8 / 46.4 / 0.75 |
| concat | T1 0.60–0.65 | 4 | 0 | 0.380 | 62.2 / 7.18 / 51.1 / 43.3 |
| concat | T1 0.80 | 1 | 0 | 1.000 | 163.8 |

clip01 greeting `[42,45]`: T1 0.50–0.75 → only SPEAKER_01, global 7.18 s (the VAD unit `[42.25, 49.43]`). T1 0.80 swallows it like 2C+0.85.

## T2 — sequential nearest existing centroid (re-attach allowed)

Not adjacent-only (that was 1A). Each unit joins the **nearest of all centroids so far** if cosine ≥ thr, else a new centroid.

| clip | T2 0.40 n_id / speech | T2 0.55 | T2 0.70 |
|---|---|---|---|
| clip01 | 2 — 49.39 / **7.18** | same 2 | 3 — 42.15 / 7.24 / 7.18 |
| clip02 | 4 (2 crumbs) | 5 (3 crumbs) | **8** oversplit |
| clip03 | 2 — 37.99 / 20.67 | same | same |
| apartments | 3 — **64.15** / 5.0 / 1.77 (one dominant) | 7 | 10 |
| ninth | **3** — 38.66 / 29.15 / **4.71** | 4 | 6 |
| concat | 6 | 7 | 11 |

Greeting is clean at 0.40/0.55. clip02 never looks like 2A’s 3-id / 0-crumb shape. 0.70 oversplits. **T2 is not ≈2A.**

## T3 — long (≥3 s) or loud (RMS ≥ p75) anchors, then assign

Anchors are **not** high neighbor-cosine. Shorts assign to nearest centroid or spawn if cosine &lt; thr.

| clip | n_units | n_anchors (long / loud) |
|---|---:|---|
| clip01 | 5 | **5** (5 / 2) — T3 ≡ T2 |
| clip02 | 10 | 6 (5 / 3) |
| clip03 | 3 | **3** (3 / 1) — T3 ≡ T2 |
| apartments | 10 | 7 (7 / 3) |
| ninth | 9 | 7 (6 / 3) |
| timing_5min | 21 | **20** (19 / 6) |

Almost every speech island after glue is already ≥3 s, so T3 cannot drop embeds and barely changes labels vs T2.

| clip | T3 0.40 | T3 0.55 | T3 0.70 |
|---|---|---|---|
| clip01 | = T2 0.40 (greeting 7.18 s) | = T2 0.55 | = T2 0.70 |
| clip02 | **2** — 28.89 / 20.27 | 4 crumbs | 7 oversplit |
| clip03 | 2 | 2 | 2 |
| apartments | 3 — 64.15 / 5.0 / 1.77 | 7 | 10 |
| ninth | 3 — 4.71 s third | 4 | 6 |

T3 0.40 on clip02 matches T1 0.60’s 2-id split (better than T2 0.40’s crumbs) but still not 2A’s 3. Apartments still lose the third substantial speaker.

## Why not ≈2A

2A’s extra ids on clip02 / apartments come from **1.5 s overlapping windows** inside long islands. One vector per glued unit cannot recover a speaker change that VAD did not cut. clip01 works because VAD already isolated `[42.25, 49.43]`. Ninth’s ~3.8 s 2A third id is **not** a 3.8 s unit; unit-AHC 0.65–0.70 keeps a **4.71 s** leftover instead — similar spirit, not the same cut.

So: fewer embeds **yes**; greeting **yes** (unlike 2A); demo-quality substitute **no**.

**REFUSED** as a replacement for 2A. Keep overlap 2A for quality. If TTFT needs the 21-call budget, local gold can listen to **T1 AHC 0.60** as a degraded mode, then **file-split** rather than more unit-threshold search.

## Artifacts

- `cloud_out/FOLLOWUP_unit_ahc.json`
- `cloud_out/timelines/{clip}__T1_ahc*.json`, `__T2_cent*.json`, `__T3_anchor*.json`
- `cloud_out/scratch/run_d5_followup_unit_ahc.py`
