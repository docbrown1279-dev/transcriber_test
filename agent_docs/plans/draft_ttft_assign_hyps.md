# Draft — part2/3 cluster rebuild hypotheses

**Status:** PLAN_DRAFT — await ✅ → commit/push `cloud_in` on `cursor/d5-ttft-split`  
**Baseline:** `split3_unified_norm` (window nearest-centroid assign, thr=0.85)  
**Not in this pack:** sticky / switch penalty (breaks real short A↔B dialogue)

## How baseline actually works (reminder)

Part2 does **not** build its own clusters. Each window is painted with the nearest part1
centroid if `dist ≤ 0.85`, else leftover → new id. Flicker = consecutive windows of one
person alternating between two close gallery ids.

## Goal of this cloud run

Rebuild / rematch clusters after a new part so **part02 and part03** have fewer tiny
fragments (short turns, rapid id chatter). Cloud = coarse metrics; local = listen later.

## Three separate hypotheses

### H1 — Cluster part2, then match whole clusters to part1 (user model)

1. Part1: unchanged AHC → gallery centroids + ids.  
2. Part2: **own AHC** on part2 windows (same thr 0.85) → local clusters.  
3. For each local cluster, compute its centroid; find nearest **gallery** id.  
   - if `dist ≤ 0.85` → **all** windows of that local cluster inherit that gallery id  
   - else → mint **one** new global id for that whole cluster  
4. Merge turns as today (gap/absorb).  
5. Update gallery: blend matched clusters into existing centroids; append new ids.  
6. Part3: same as step 2–5 against updated gallery.

**Why it might help:** labeling is per **cluster**, not per window → no 00↔01 chatter inside one AHC blob.  
**Risk:** bad local AHC still glues two people, then whole blob maps to one gallery id.

### H2 — Baseline assign, then one refine pass (same K, new centroids)

1. Part2: **current** window assign to gallery (baseline).  
2. Recompute each existing speaker centroid from **part1 gallery prior + all part2 windows** now labeled with that id (duration- or count-weighted blend).  
3. **Re-assign every part2 window once** to the refreshed centroids (same thr; leftover → new id as today).  
4. Do **not** change part1 turns/ids.  
5. Part3: same pattern (assign → refresh → one re-assign).

**Why it might help:** centroids move toward part2 acoustics; second paint may be stabler.  
**Risk:** still window-level nearest neighbor → flicker can remain if two centroids stay close.

### H3 — Cluster part2, match by overlap in embedding space + merge same target

Like H1, but matching is stricter / clearer:

1. Part2 local AHC as in H1.  
2. Match local cluster → gallery by nearest centroid, but only if  
   `d_best ≤ 0.85` **and** `d_second − d_best ≥ 0.05` (clear winner).  
3. If ambiguous (no clear winner): map the **whole** local cluster to nearest anyway **or**
   spawn new id only if cluster speech ≥ 2.0 s; if cluster speech < 2.0 s, map to nearest
   gallery (no new micro-id). Pick one rule and document it in the run (prefer:
   ambiguous + short → nearest; ambiguous + long → new id).  
4. If several local clusters match the same gallery id → all keep that id (same person,
   multiple segments — OK).  
5. Gallery update + part3 as in H1.

**Why it might help:** H1 + fewer accidental new ids + less wrong merge when two gallery
speakers are equally close.  
**Risk:** margin may create extra new ids on long ambiguous clusters.

## Cloud metrics (coarse)

For baseline + each hyp, on **part02 and part03**:

- `n_turns`, `n_turns_lt_1s`, `n_turns_lt_2s`
- `n_speaker_switches`
- `n_speakers` / new ids vs part1
- Hotspot dump abs 365–375 (part02 only) — for local listen later

Primary cloud success signal: **fewer** `n_turns_lt_1s` and/or `n_speaker_switches` on part02+part03 without huge speaker-count explosion.

## Out of scope this pack

- Sticky previous-window / switch penalty as main fix  
- Dual anchor+live centroids  
- Re-ASR / gold / `src/` edits  
- Combining H1+H2+H3 in one assigner
