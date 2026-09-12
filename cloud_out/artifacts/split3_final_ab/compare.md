# Final A/B — V1 EOS AHC vs V2 constrained merge vs V3 H1-tune

**SEMANTIC_CHECK = local human; cloud did not judge meaning.**

Structural proxies only (crumbs, switches, speaker inventory, hotspot dump, V1 greedy duration remap vs full15). No gold / eval / ASR.

`proxy_pick` ceiling (offline, waits for all parts): **V1** (EOS AHC on concatenated part embeddings).
`proxy_pick` TTFT-path (online-ish, keeps part1 labels): **V2=V3=H1 (all |Δspk|>2 vs full15)** (ranked ['V2', 'V3', 'H1']; no method kept |Δspk|≤2 vs full15).

## Combined part02+part03 proxies

| method | n_turns | lt1s | lt2s | switches | n_speakers_max | Δlt1s vs full15 | Δsw vs full15 | Δspk vs full15 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full15 | 109 | 4 | 30 | 59 | 5 | +0 | +0 | +0 |
| V1 | 111 | 5 | 32 | 61 | 5 | +1 | +2 | +0 |
| V2 | 91 | 3 | 22 | 30 | 2 | -1 | -29 | -3 |
| V3 | 91 | 3 | 22 | 30 | 2 | -1 | -29 | -3 |
| H1 | 91 | 3 | 22 | 30 | 2 | -1 | -29 | -3 |

## Per part

| method | part | n_turns | lt1s | lt2s | switches | n_speakers | speaker_ids | new_ids_vs_part1 |
|---|---|---:|---:|---:|---:|---:|---|---|
| full15 | part02 | 56 | 3 | 15 | 37 | 5 | SPEAKER_00, SPEAKER_01, SPEAKER_02, SPEAKER_03, SPEAKER_04 | SPEAKER_02, SPEAKER_03, SPEAKER_04 |
| full15 | part03 | 53 | 1 | 15 | 22 | 4 | SPEAKER_00, SPEAKER_01, SPEAKER_02, SPEAKER_03 | SPEAKER_02, SPEAKER_03 |
| V1 | part02 | 58 | 3 | 18 | 40 | 5 | SPEAKER_00, SPEAKER_01, SPEAKER_02, SPEAKER_03, SPEAKER_04 | SPEAKER_04 |
| V1 | part03 | 53 | 2 | 14 | 21 | 4 | SPEAKER_00, SPEAKER_01, SPEAKER_02, SPEAKER_03 | — |
| V2 | part02 | 43 | 2 | 11 | 16 | 2 | SPEAKER_00, SPEAKER_01 | — |
| V2 | part03 | 48 | 1 | 11 | 14 | 2 | SPEAKER_00, SPEAKER_01 | — |
| V3 | part02 | 43 | 2 | 11 | 16 | 2 | SPEAKER_00, SPEAKER_01 | — |
| V3 | part03 | 48 | 1 | 11 | 14 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H1 | part02 | 43 | 2 | 11 | 16 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H1 | part03 | 48 | 1 | 11 | 14 | 2 | SPEAKER_00, SPEAKER_01 | — |

## V1 vs full15 (greedy duration remap, not gold)

- agreement % of full15 speech overlap: **98.521**
- dice %: **98.525**
- matched overlap sec: 762.46 / full15 773.904 / V1 773.852
- mapping V1→full15: `{'SPEAKER_00': 'SPEAKER_00', 'SPEAKER_02': 'SPEAKER_02', 'SPEAKER_01': 'SPEAKER_01', 'SPEAKER_03': 'SPEAKER_03', 'SPEAKER_04': 'SPEAKER_04'}`
- unmapped V1: []; unmapped full15: []
- V1 whole-file: n_turns=147 lt1s=7 switches=71 n_speakers=5
- full15 whole-file: n_turns=141 lt1s=4 switches=65 n_speakers=5

## part02 hotspot [365.0, 375.5] abs

- **full15** (2 turns): SPEAKER_03(0.75s @365.196) → SPEAKER_02(9.338s @365.946)
- **V1** (2 turns): SPEAKER_03(0.75s @365.196) → SPEAKER_02(9.338s @365.946)
- **V2** (1 turns): SPEAKER_00(10.088s @365.196)
- **V3** (1 turns): SPEAKER_00(10.088s @365.196)
- **H1** (1 turns): SPEAKER_00(10.088s @365.196)

## V2 attempt log (cap 20 / part)

- part02: attempts=1 success_before_cap=True fallback=False
- part03: attempts=2 success_before_cap=True fallback=False
- Constraint: never recolor committed windows; match whole local cluster if dist≤0.85 and old windows stay within 0.85 of the new center of mass; else new id. Nudge target centroid toward nearest member mean + cluster mean and retry.

## V3 tune

- Rule **A** (preferred): after H1 whole-cluster match, any local cluster with `speech_union < 2.0 s` whose id differs from the previous cluster in time is glued to that previous id. Not per-window sticky. Rule B (H3 margin) was not used.
- glued clusters: part02=0 part03=0

## Ranking note (proxies only)

All methods by (lt1s, switches, huge-speaker-swing vs full15): **V2 > V3 > H1 > full15 > V1**.
Huge swing = |n_speakers_max − full15| > 2. Online methods here share the same 2-speaker inventory (collapse vs full15 5) while cutting crumbs/switches; that is a proxy tradeoff, not a semantic win.
On this file V2 part02/part03 turns match H1 (and V3: rule A glued 0 clusters). V2 part03 needed 2 attempts (one inlier CoM nudge) then matched the same gallery ids.

## Environment

- embeddings reused from split3_cluster_rebuild ({'part01': 321, 'part02': 339, 'part03': 289}); unified-norm wav slices; shared VAD
- AHC cosine/average thr=0.85; windows 1.5/0.75; wall_sec=0.138
- host nproc=4; HF_HUB_OFFLINE=1; no src/config/tests edits; no PR; no LLM

## Deviations

None beyond V3 choosing rule A as specified-preferred.
