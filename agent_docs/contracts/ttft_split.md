# Contract: TTFT file-split (product)

Status: DONE (2026-09-13). Implements [`draft_ttft_split_product.md`](../plans/draft_ttft_split_product.md).  
Gate: [`../reports/d5_ttft_split/product_gate.md`](../reports/d5_ttft_split/product_gate.md) **PASS_WITH_WARNINGS** (`ttft_first_chapter_sec≈169` ≤ 300 @ 2 CPU / 8 GiB).

This is **local product work** (same class as D4 / D5). Not a research spike. Frozen stack stays: Silero VAD, WeSpeaker `1.5/0.75` + AHC cosine/average `0.85`, GigaAM v3 RNNT, packing C, `toc_mode=b`.

## 1. TTFT definition (gate)

**TTFT** = wall seconds from `run_job` / worker start until the first **schema-valid** `chapters.json` is on disk with at least one chapter whose `end` is inside part1.

- Titles are **optional** for this clock. Placeholder / empty title is allowed.
- LLM must **not** block the first write.
- The UI must navigate to `/result` on this artifact while the job is still `running`.
- Measuring only `state=done` is a defect: that is end-to-end wall, not TTFT.

| id | Check | Threshold |
|---|---|---|
| G5.T1 | 15′ slice, Docker `--cpus=2 --memory=8g`, **warm** model cache | TTFT ≤ **300 s** |
| G5.T2 | Same run completes (EOS + titles) | no OOM; peak RSS **< 7 GiB** (G5.4) |
| G5.T3 | `pipeline.ttft_split: false` | existing full path still works (no split, no early TOC from parts) |

Cold-cache first download is noted, not gated.

Budget reality from G5 full run (15′ @ 2 CPU): diarize ~402 s + ASR ~370 s. Part1 ≈ 291 s of media ⇒ expected diar+ASR ≈ 250 s + normalize/VAD ~6 s + packing. **Part1 media must stay ≤ ~300 s** or the 300 s TTFT wall is missed. LLM titles are outside the TTFT clock.

## 2. Flag and defaults

```yaml
# config/base.yaml — keep full path as the shared default
pipeline:
  toc_mode: b
  ttft_split: false

audio:
  gain:
    max_db: 18.0          # per-turn ASR still uses this
    file_max_db: 2.0      # whole-file normalize cap when ttft_split is on

# config/profiles/demo.yaml — ship path
pipeline:
  ttft_split: true
```

Cut knobs (all in yaml, no literals in `src/`):

| Key | Default | Role |
|---|---|---|
| `pipeline.ttft.min_part_sec` | 180 | skip split if duration < 2× this |
| `pipeline.ttft.max_part_sec` | 300 | hard cap; **300 not 360** so part1 fits the TTFT wall |
| `pipeline.ttft.target_part_sec` | 270 | ideal part length |
| `pipeline.ttft.min_pause_sec` | 0.8 | Silero gap eligible as a cut |
| `pipeline.ttft.search_half_width_sec` | 90 | pause search around ideal boundary |

Short files (`duration < 2 * min_part_sec`): run the existing full pipeline even if the flag is on. Log `ttft_split_skipped`.

## 3. Pipeline (when flag on and file long enough)

```
audio
  → normalize once (file gain ≤ file_max_db) + VAD once
  → pause-cut → parts[~4–5 min, max 300 s]
  → for each part:
        slice wav + speech regions (no new VAD, no new file gain)
        diarize (part1 AHC | else assign+absorb)
        ASR turns on that part
        packing C; hold open tail chapter until next part / EOS
        if part1 done → publish transcript.json + chapters.json (speakers read-only)
  → batch/async titles for closed chapters (do not block part1 publish)
  → EOS: AHC(all saved window embeddings) → remap speaker ids → rewrite labels
  → speakers_finalized = true
```

Shared artifacts stay job-level: one `normalized.wav`, one `speech.json`, one `audio.json`. Parts are time slices, not independent jobs.

## 4. Mid diarization = method B (not H1)

| | Method B (product) | H1 (research, **forbidden** here) |
|---|---|---|
| Part1 | AHC on part windows, thr=`cluster_distance_threshold` (0.85) | same |
| Part2+ | **per-window** nearest gallery centroid; `dist ≤ 0.85` → that id; else new id (leftover windows may AHC among themselves into new ids) | local AHC on the part, then match **whole clusters** to gallery |
| Merge | `absorb_turn_shorter_than_sec` (1.0 s) | n/a |

Do **not** port V2 constrained merge, V3, sticky-previous-window, dual centroids, or Jina.

Reference implementation (research only — copy the idea, not the path): `cloud_out/artifacts/split3_unified_norm/scripts/centroid_assign.py` (`SpeakerGallery.assign`). Runtime code lives under `src/`.

Persist per part under the job dir (names may vary, schema in code):

- gallery / `centroids.json`
- window embeddings + absolute times (needed for EOS; **do not re-embed** at EOS if present)

## 5. EOS = V1

1. Concatenate saved windows in absolute time order.
2. One AHC, same metric/linkage/threshold as product WeSpeaker.
3. Remap new labels → already published `SPEAKER_*` by **greedy duration overlap** (Hungarian optional). Unmapped mass → new compact ids.
4. Rewrite `speaker` on `turns.json` and `transcript.json` segments. Do **not** re-run ASR. MVP: do **not** re-title; only speaker fields / chapter `speakers` lists.
5. Set `speakers_finalized: true`. Unlock speaker UI.

Mid-run flicker on a third talker is allowed. EOS must not collapse the meeting to two large speakers (speech ≳ 30 s) on the 15′ `voice_002` slice.

## 6. Early publish + speaker lock

`job.json` (add fields with defaults so old jobs stay valid):

| Field | Default | Meaning |
|---|---|---|
| `speakers_finalized` | `true` | `false` after part1 publish until EOS |
| `early_ready` | `false` | `true` when first `chapters.json` is published |

Polling `GET /jobs/{id}/events` must include both flags. Progress JS redirects to `/result` when `early_ready` **or** `state=done`. Result/chapter pages stay reachable while `state=running`.

Speaker **id** and **alias** edits are locked while `speakers_finalized` is false. Transcript text edit may stay enabled. Show a Russian banner that the TOC is a draft and speakers will be refined.

## 7. Gain

- Whole-file linear gain uses `audio.gain.file_max_db` (2.0) when `ttft_split` is on.
- `audio.gain.max_db` (18) stays the cap for **per-turn** ASR gain (`asr_per_turn_gain: true`).
- Log `gain_db` and `capped=true` when the file cap binds. Optional artifact field `loudness.capped` default `false` (keep `extra=forbid` happy with a default).

## 8. Eval reference (not diar gold)

Do **not** use `eval/d5_diar/gold`. Reference = full15 turns/transcript/chapters sliced by the same cut plan:

`eval/d5_ttft_split/reference_full15/` (gitignored)

Glue helper: `scripts/check_ttft_part_glue.py`. EOS vs full: large-speaker count, text coverage, hotspot ~365–375 s (cable) after remap.

## 9. Out of scope

Online H1/V2/V3, sticky, Jina / packing D, live chapters without absorb, raising `file_max_db`, re-ASR after EOS, GitHub Actions, cloud research packs.
