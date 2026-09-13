# Cluster rebuild A/B — H1 / H2 / H3 vs unified_norm baseline

## Verdict: PASS

PASS — H1 (tied with H3) reduces crumbs and/or switches vs baseline without huge speaker growth.

Primary success: lower `n_turns_lt_1s` and/or `n_speaker_switches` on part02+part03 without huge `n_speakers` growth vs baseline. Hypotheses were replayed **separately** from the same part1 gallery. No sticky-previous-window. No ASR/packing.

## Combined part02+part03

| hyp | n_turns | n_turns_lt_1s | n_speaker_switches | n_speakers_max | Δlt1s vs baseline | Δswitches vs baseline | Δspeakers_max |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 126 | 19 | 73 | 3 | +0 | +0 | +0 |
| H1 | 91 | 3 | 30 | 2 | -16 | -43 | -1 |
| H2 | 123 | 18 | 66 | 2 | -1 | -7 | -1 |
| H3 | 91 | 3 | 30 | 2 | -16 | -43 | -1 |

## Per part

| hyp | part | n_turns | n_turns_lt_1s | n_turns_lt_2s | n_speaker_switches | n_speakers | speaker_ids | new_ids_vs_part1 |
|---|---|---:|---:|---:|---:|---:|---|---|
| baseline | part02 | 65 | 13 | 29 | 43 | 3 | SPEAKER_00, SPEAKER_01, SPEAKER_02 | SPEAKER_02 |
| baseline | part03 | 61 | 6 | 23 | 30 | 3 | SPEAKER_00, SPEAKER_01, SPEAKER_02 | SPEAKER_02 |
| H1 | part02 | 43 | 2 | 11 | 16 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H1 | part03 | 48 | 1 | 11 | 14 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H2 | part02 | 74 | 16 | 33 | 52 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H2 | part03 | 49 | 2 | 13 | 14 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H3 | part02 | 43 | 2 | 11 | 16 | 2 | SPEAKER_00, SPEAKER_01 | — |
| H3 | part03 | 48 | 1 | 11 | 14 | 2 | SPEAKER_00, SPEAKER_01 | — |

## part02 hotspot [365.0, 375.5] abs

Baseline unified_norm flickers 00↔01 here. Each row is overlapping turns.

- **baseline** (5 turns): SPEAKER_00(0.75s @365.196) → SPEAKER_01(1.5s @365.946) → SPEAKER_00(2.25s @367.446) → SPEAKER_01(0.75s @369.696) → SPEAKER_00(4.838s @370.446)
- **H1** (1 turns): SPEAKER_00(10.088s @365.196)
- **H2** (5 turns): SPEAKER_00(0.75s @365.196) → SPEAKER_01(2.25s @365.946) → SPEAKER_00(0.75s @368.196) → SPEAKER_01(3.0s @368.946) → SPEAKER_00(3.338s @371.946)
- **H3** (1 turns): SPEAKER_00(10.088s @365.196)

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| P0 | hyps run separately | H1, H2, H3 each clone part1 gallery | do not combine | PASS |
| P1 | sticky-previous-window | not implemented | forbidden | PASS |
| P2 | embeddings once | {'part01': 321, 'part02': 339, 'part03': 289} | part01–03 dumped | PASS |
| B0 | baseline part02 lt1s | 13 | record (unified_norm 13) | PASS (record) |
| C1 | best hyp vs baseline lt1s+switches | H1 (tied with H3) Δlt1s=-16 Δsw=-43 | lower at least one | PASS |
| C2 | speaker growth (best hyp) | -1 vs baseline max 3 | not huge (>2) | PASS |
| L1 | LLM / ASR | 0 / skipped | out of scope | PASS |

## Agent judgement

Rank by (lt1s, switches, n_speakers_max) on part02+part03: **H1 > H3 > H2**. Winner **H1 (tied with H3)**.

H1 maps a whole local AHC cluster to one gallery id (or one new id), which should stop single-talker flicker across ids inside a cluster. H2 keeps window assign but one centroid refine + re-assign. H3 is H1 plus a 0.05 clear-winner margin; clusters <2.0 s of union speech that are ambiguous map to the nearest gallery id (no new micro-id).

On this file H1 and H3 produced **identical** part02/part03 turns: part-local AHC made four clusters and every cluster already had d_best≤0.85 with margin≥0.05, so H3's extra rule never fired. Short 00↔01 dialogue still appears later in part02 (not a sticky-previous-window collapse). SPEAKER_02 from baseline (~4 s crumbs) is absorbed; some SPEAKER_01 mass moves into SPEAKER_00 (one large cluster at d_best≈0.57 to 00).

Prep: wav=unified_norm_slices; shared VAD from unified_norm/full15; wall_sec=40.221. Host nproc=4 (not a 2-vCPU TTFT demo). `cloud_in/inputs/artifacts/hypotheses.md` was absent; hyps taken from the agent prompt.

## Environment

- stage D5.TTFT-cluster-rebuild; onnx_threads=2; HF_HUB_OFFLINE=1
- helper: cloud_out/artifacts/split3_cluster_rebuild/scripts/
- baseline: cloud_out/artifacts/split3_unified_norm/ (not deleted)
- no src/ config/ tests/ edits; no PR; no LLM API

## Deviations and blockers

hypotheses.md missing from pack; otherwise none.
