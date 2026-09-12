# Stage D5.TTFT-split — FINAL A/B: EOS full-like AHC vs constrained merge vs H1-tune

You are the **research spike** cloud agent. This prompt overrides product defaults.
Do **not** edit `src/`, `config/`, `tests/`. No PR. `HF_HUB_OFFLINE=1`.
Push branch `cursor/d5-ttft-split`.

## Hard constraints (all variants)

- **One unified file gain** (same as `split3_unified_norm`): normalize once, slice wavs.
- **Shared VAD**: speech regions = slices of full-file/shared speech (not per-part VAD).
- Same WeSpeaker windows `1.5/0.75`, AHC metric cosine / linkage average / default thr **0.85**.
- Reuse embeddings under `cloud_out/artifacts/split3_cluster_rebuild/` if present
  (`part0{1,2,3}_embeddings.npy` + windows + offsets). Re-embed only if missing.
- No ASR / LLM / gold / sticky-previous-window as a main idea.
- Compare to: (a) `full15` turns, (b) **H1** under `split3_cluster_rebuild/H1_cluster_then_match/`.

## Why

Hundreds of windows; only a few differ near pause cuts vs a true full-file pass.
**V1** (one AHC at end on concatenated part embeddings) should be the closest offline
proxy to full — useful as quality ceiling for split *materials*, not as TTFT (waits for
all parts). **V2/V3** are online-ish paths that keep early part1 labels.

---

## V1 — Embed per part, cluster **once at EOS** (full-like)

1. Part1/2/3: extract windows + embeddings only (no per-part speaker commit required).
2. Concatenate all windows in absolute time order.
3. **Single** AHC on the full concatenation (thr=0.85).
4. Merge turns (same gap/absorb as config).
5. Report metrics on part02/part03 slices **and** on the whole 15′.
6. Remap speaker ids to maximize duration overlap with `full15` (greedy) for comparison
   only — do not use gold.

**Expectation:** closest to full15 among split-derived methods.

---

## V2 — Per-part clusters, constrained merge into previous (online)

Process parts in order. After each part, rebuild a **global** labeling such that
**all previous parts’ committed labels remain valid** (every earlier window keeps its
speaker id). Cap search at **20** attempts per part.

### Per part `p`

1. Local AHC on part `p` windows (thr=0.85) → local clusters.
2. Init global centroids = **center of mass** (mean embedding) of each existing global
   speaker from all windows already committed; for brand-new local mass use local means.
3. Try to assign each **local cluster** (whole cluster) to a global speaker:
   - Prefer nearest global centroid if `dist ≤ 0.85` **and** this does not violate the
     constraint that previously committed windows stay on their ids
     (i.e. you may only *add* windows to an existing id or create a new id;
     you must not recolor past windows).
   - If a local cluster does not fit: create a **new** global id (centroid = its mean).
4. If the merge is unstable / constraint fails / distances absurd: **nudge** the target
   centroid toward the mean of its **nearest member windows** (or toward the local
   cluster mean being absorbed), recompute, retry. Max **20** attempts, then accept
   best feasible (document failures).
5. Commit part `p` labels. Update centroids as centers of mass of all committed windows
   per id. Proceed to next part.

Part1 = plain AHC (commit). Part2/3 = constrained merge as above.

---

## V3 — H1 base + one light tune (hybrid)

Start from **H1** (local AHC per part → whole-cluster match to gallery / new id).
Add **exactly one** extra rule (document which you pick; prefer A unless blocked):

- **A (preferred):** after H1 match, any local cluster with `speech_union < 2.0 s`
  whose assigned id differs from the **previous local cluster in time** → reassign to
  that previous cluster’s id (glue micro-clusters only; not per-window sticky).
- **B:** clear-winner margin 0.05 on gallery match; long ambiguous → new id;
  short ambiguous → nearest (H3 rule), on top of H1.

Do not combine A and B. Do not reintroduce H2 window refine as the main path.

---

## Metrics (coarse only — no semantic / gold judgment)

There is **no `eval/` and no gold** in cloud. Do **not** claim a quality winner by meaning.
Human will listen locally later. Cloud only reports **structural proxies**:

| Proxy | Definition | Why we look |
|---|---|---|
| `n_turns_lt_1s` / `lt_2s` | turns shorter than 1s / 2s after merge | “fewer crumbs” |
| `n_speaker_switches` | consecutive turns with different speaker id | less id chatter |
| `n_speakers` / `new_ids` | speaker inventory | catch explode/collapse |
| hotspot list | turns overlapping abs `[365.0, 375.5]` | known flicker zone dump |
| V1 vs full15 | greedy duration remap → agreement % | “is EOS-on-parts near full?” — still not gold |

For V1/V2/V3 and refs (full15, H1), compute these on **part02 and part03** slices.
V1 also whole-file metrics + remap-vs-full15.

Write `cloud_out/artifacts/split3_final_ab/compare.md` with:
- tables of the proxies above (V1 / V2 / V3 / H1 / full15)
- **ranking by proxies only** (e.g. fewer lt1s + switches, without huge n_speakers swing)
- explicit note: `SEMANTIC_CHECK = local human; cloud did not judge meaning`
- optional one-line **candidate** for TTFT path (V2/V3/H1) and for ceiling (V1)—labeled
  `proxy_pick`, not PASS/FAIL

## Task order

1. `cloud_out/run_meta.json` — stage `D5.TTFT-final-ab`
2. Confirm unified gain + shared VAD + load/reuse embeddings
3. Run V1, V2, V3 separately (no combined frankenstein)
4. Metrics + `compare.md`
5. Commit `cloud_out/artifacts/split3_final_ab/` (+ scripts); push; no PR

## Deliverables

```
cloud_out/artifacts/split3_final_ab/
  V1_eos_ahc/
  V2_constrained_merge/
  V3_h1_tune/
  compare.md
  run notes / attempt logs for V2
  scripts/
```

Each variant: `turns_part02.json`, `turns_part03.json`, and for V1 also `turns_full.json`;
`metrics_*.json`.

## Stop-list

No `src/` edits, no gold/`eval/`, no unbounded search (>20 attempts), no PR.
