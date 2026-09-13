# Bug-fixer / Coder instructions — D5.TTFT split (product)

Status precondition: user ✅ on this pack (or explicit “implement TTFT split”).  
Plan: [`../plans/draft_ttft_split_product.md`](../plans/draft_ttft_split_product.md).  
Contract: [`../contracts/ttft_split.md`](../contracts/ttft_split.md).  
Tester: [`tester_D5_ttft.md`](tester_D5_ttft.md).  
Predecessor: D5 Docker/G5 `TEST_PASS` (full 15′ wall ~785 s). Research branch `cursor/d5-ttft-split` is **reference only**.

**Local product work.** No new cloud research pack. No PR from a research prompt.  
Do **not** edit `tests/` (Tester). Do **not** edit `docs/`, `eval/`, `.env`, `.cursor/`.  
Do **not** install packages without approval. Reuse WeSpeaker / packing C / pipeline_b.

## Goal

Cut **TTFT** (time to first usable chapter list) to **≤ 5 minutes (300 s)** for the demo 15-minute file on **2 CPU / 8 GiB**.

Today the UI waits for full diarize+ASR+TOC (~10–13 min on this hardware: G5 diarize ~402 s + ASR ~370 s). Ship path: process **part1 (~4–5 min of audio)** after one file-level normalize+VAD, publish TOC, continue in the background, refine speakers at EOS.

## Frozen decisions (do not reopen)

| Topic | Ship this |
|---|---|
| VAD | **One** Silero pass on the full file; parts slice **regions** |
| File gain | **One** loudness; cap **`file_max_db: 2.0`**. Then slice `normalized.wav` |
| Per-turn ASR gain | keep `asr_per_turn_gain: true` (`max_db: 18`) |
| Cut | Silero pauses, target **~270 s**, **max 300 s** (not research 360 — that blows the TTFT wall) |
| Mid diar | Part1 **AHC**; part2+ **per-window nearest centroid** + absorb < 1 s (**method B**) |
| H1 / V2 / V3 / sticky | **out** |
| EOS | **V1**: one AHC on **saved** window embeddings; remap to shown ids |
| Titles | must not block part1 publish |
| Speaker UI | locked until EOS |

## Explicit non-goals

- Changing WeSpeaker windows (`1.5/0.75`) or AHC threshold (0.85).
- Independent AHC on every part (id drift).
- Re-embedding at EOS if windows were saved.
- Re-ASR / re-title after EOS (MVP).
- Using `eval/d5_diar/gold`.
- Copying `cloud_out/**/scripts/` into the runtime import path.
- Breaking `pipeline.ttft_split: false` (full job as today).

## Suggested layout (smallest correct diff)

```
config/base.yaml
config/profiles/demo.yaml
src/transcriber/config/schema.py
src/transcriber/audio/gain.py              # file_max_db + capped
src/transcriber/audio/normalize.py
src/transcriber/models/artifacts.py        # loudness.capped; job early_ready / speakers_finalized
src/transcriber/pipeline/pause_cut.py      # port scripts/plan_pause_cuts.py
src/transcriber/pipeline/ttft_split.py     # part loop + early publish + EOS hook
src/transcriber/pipeline/orchestrator.py   # branch on flag
src/transcriber/diarization/gallery.py     # SpeakerGallery + assign B (from centroid_assign.py)
src/transcriber/diarization/eos_refine.py  # V1 AHC + greedy remap
src/transcriber/diarization/wespeaker.py   # extract windows as a reusable function if needed
src/transcriber/chunking/packing_c.py      # hold-open tail across parts
src/transcriber/jobs/store.py              # persist new job fields
src/transcriber/jobs/queue.py              # events payload
src/transcriber/web/routes.py              # lock speaker POSTs; result while running
src/transcriber/web/templates/{result,chapter,progress}.html
src/transcriber/web/static/app.js          # redirect on early_ready
scripts/bench_d5.py                        # record ttft_first_chapter_sec
manuals/configuration_guide.md             # one row for ttft_split / file_max_db
```

Research to **read**, not import:

- `scripts/plan_pause_cuts.py`
- `cloud_out/artifacts/split3_unified_norm/scripts/centroid_assign.py`
- packing continuity notes in `cloud_out/artifacts/split3/gate_split3.md`

## Config (no magic numbers)

Add to `PipelineConfig` (names may match contract §2):

```yaml
pipeline:
  toc_mode: b
  ttft_split: false          # base; demo overlay true
  ttft:
    min_part_sec: 180
    max_part_sec: 300
    target_part_sec: 270
    min_pause_sec: 0.8
    search_half_width_sec: 90
```

`AudioGainConfig.file_max_db: 2.0`. When `ttft_split` is on, whole-file `calculate_gain(..., max_gain_db=file_max_db)`. Per-turn ASR still uses `max_db`.

`pydantic extra=forbid`: every new key in yaml **and** schema together.

## Algorithm

### 0. Orchestrator branch

`run_job`: if `cfg.pipeline.ttft_split` and duration ≥ `2 * min_part_sec` → `run_ttft_split(...)`. Else existing `PIPELINE_STEPS` / `pipeline_b`. Do not fork the registry or engines.

Keep `until` semantics: web still runs through titles; early TOC is a **side publish**, not a stop.

### 1. Normalize + VAD once

Same dual-path as now (`normalized.wav` + `vad_input.wav`). File gain cap as above. Write `audio.json` / `speech.json` for the **full** file. Log `gain_db` and whether `file_max_db` capped.

### 2. Cut plan

Port `plan_pause_cuts.plan` into `src`. `n_parts = ceil(duration / target_part_sec)` clipped by min/max part constraints (15′ → 3 parts; 30′ → more). Fallback: midpoint if no pause in window. Write `cut_plan.json` in the job dir.

Slice:

- wav: ffmpeg/sf time slice of **already normalized** wav (no second gain).
- speech: clip/shift regions to the part, then **shift back to absolute time** in turns/transcript (UI clock = file clock).

Do not run VAD per part.

### 3. Method B diarization

Part1: existing WeSpeaker AHC on that part’s windows → `turns` in **absolute** time → gallery centroids.

Part2+: embed windows on the part → `gallery.assign` (nearest cosine distance ≤ `cluster_distance_threshold`; unmatched leftover AHC → new `SPEAKER_*`) → `merge_turns` with absorb 1.0 s. **Do not** compact-renumber in a way that rewrites part1 ids.

Save embeddings + window `[abs_start, abs_end]` + labels after each part.

Smoke invariants: part1 ids ⊆ `{SPEAKER_00,…}`; part2 may add ids; absorb still applies.

### 4. ASR + packing + early publish

ASR each part’s turns (existing GigaAM path / pipeline_b slice helper). Append segments to the job-level transcript.

Packing C:

- After part N (not last): **do not close** the last chapter (hold tail). Research: prepend the previous part’s last-chapter segments when packing the next part.
- After last part / EOS: absorb short units as today.

When part1 packing has **at least one chapter** (tail may stay untitled/open):

1. Write `transcript.json` + `chapters.json` (atomic replace).
2. Set `job.early_ready=true`, `job.speakers_finalized=false`.
3. Emit `StageEvent(stage="chunk", status="done" or "partial", message="ttft_part1")`.
4. **Do not wait** for titles.

Closed chapters may get titles asynchronously (reuse pipeline_b “title when next chapter appears”). Part1 may ship with empty titles.

### 5. EOS V1 + unlock

After the last part:

1. AHC on **all saved** embeddings (thr 0.85).
2. Greedy remap by duration overlap onto ids already shown.
3. Rewrite speaker labels on turns + transcript (+ chapter `speakers` lists).
4. `speakers_finalized=true`. Job can then `done` after titles as today.

Do not re-embed. Do not re-ASR.

### 6. UI

Today `app.js` redirects to `/result` only when `state === "done"`. That hides the TTFT win.

- `job_events_payload`: add `early_ready`, `speakers_finalized`.
- Progress: redirect when `early_ready || state === "done"`.
- Result/chapter: render if `chapters.json` exists even if `state=running`; banner in Russian that processing continues / speakers are draft.
- Lock `POST .../actions/speakers` and per-segment speaker `<select>` while not finalized. Text edit may remain. 409/HTML message, not a silent no-op.
- While `state=running` and early TOC is shown, poll lightly and refresh chapter list / speaker labels when EOS lands (do not kick the user back to the progress page).

## Hardware constraints (do not ignore)

G5 15′ @ 2 CPU: ~0.86 s wall per 1 s of audio for diar+ASR. Part1 **must** be ≤ 300 s of media. If the cut planner wants 360 s, the gate fails — the yaml max is 300.

Do not add extra embed passes, extra VAD, or a second whole-file AHC before EOS. EOS AHC on stored vectors is cheap.

`OMP_NUM_THREADS` / onnx_threads stay 2.

## Tests you do not write

Tester owns `tests/`. Keep new helpers pure (pause cut, gallery assign, remap) so they can test without wav.

## Acceptance (Coder → READY_FOR_TEST)

- [ ] `ttft_split: false` — behaviour unchanged (smoke: existing CLI `run` on a short clip or fixture resume).
- [ ] `ttft_split: true` on demo — cut_plan written; one `normalized.wav`; one `speech.json`.
- [ ] File gain uses `file_max_db`; per-turn ASR still uses `max_db`.
- [ ] After part1, `chapters.json` exists while later parts still run; events expose `early_ready`.
- [ ] Mid = assign B, not per-part AHC / H1.
- [ ] Window embeddings persisted; EOS remaps labels; `speakers_finalized` flips true.
- [ ] Speaker POST locked until EOS.
- [ ] Progress JS can leave for `/result` before `done`.
- [ ] `bench_d5.py` (or successor) records `ttft_first_chapter_sec` from job start → first chapters write.
- [ ] `ruff` / `mypy` / `bandit` clean on **touched** Python.
- [ ] Append `READY_FOR_TEST` to `agent_docs/progress/stage_D5_ttft.md` with commands.

Do **not** claim the 300 s gate yourself unless you actually ran Docker `--cpus=2 --memory=8g` on the 15′ file. That is Tester G5.T1.

## Handoff

@Tester: [`tester_D5_ttft.md`](tester_D5_ttft.md) — unit tests, 15′ Docker TTFT ≤ 300 s, glue vs `reference_full15`, speaker lock.
