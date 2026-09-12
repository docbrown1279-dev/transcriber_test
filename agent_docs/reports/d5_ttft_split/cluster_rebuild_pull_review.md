# Pull review — cluster rebuild H1/H2/H3 (`16ecd95`)

**Pulled:** `origin/cursor/d5-ttft-split` @ `16ecd95`  
**Source compare:** `cloud_out/artifacts/split3_cluster_rebuild/compare_parts.md`

## Verdict (coarse)

**H1 ≈ H3 >> baseline >> H2** on crumb/switch metrics.  
Hotspot 365–375: baseline flicker gone under H1/H3 → one `SPEAKER_00` ~10 s turn.

| hyp | part02+03 turns | <1s | switches | speakers |
|---|---:|---:|---:|---:|
| baseline | 126 | 19 | 73 | 3 |
| **H1** | **91** | **3** | **30** | **2** |
| H2 | 123 | 18 | 66 | 2 |
| **H3** | **91** | **3** | **30** | **2** |

H1==H3 on this file (all local clusters already clear winners; margin/2s rules idle).  
H2 (refine+reassign) almost no help; part02 even slightly worse on switches.

## Caveat for stop-line

H1 may **oversmooth**: a large local AHC blob can map entirely to `SPEAKER_00` and eat some real `SPEAKER_01` (agent note: one big cluster at d≈0.57→00). Local listen still needed before baking into `src/`.

## TTFT stop-line proposal

1. **Ship path:** pause-cut + shared VAD + unified norm + **H1 cluster-then-match** for part2+.  
2. **Backlog:** H3 margin if oversmerge shows up; new-id min duration; true centroid refine.  
3. **Do not** chase more assign A/B on this file unless listen fails H1.
