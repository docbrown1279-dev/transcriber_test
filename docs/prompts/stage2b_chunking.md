# Prompt — Stage 2b (chunking only; ASR is frozen)

Continue on **`cursor/stage1e-four-asr-be20`**. Do not rerun ASR, diarization, audio preprocessing, or any work already completed on this branch.

Read:

- `docs/research_plan.md` — Stage 2b plan;
- `AGENTS.md`;
- `docs/schemas/chunk_merge_log.schema.json`;
- `results/reports/2/notes.md` — completed Stage 2 record.

Do not read gold data under `eval/`.

Required immutable inputs:

- `results/asr/2/gigaam_v3_rnnt/meeting_sample.json`;
- `results/chunking/2/attempt_2_chunks_titled.json`.

If either input is missing, stop. Do not recreate it.

---

You are the Researcher agent. Run **Stage 2b only: chunking experiments over the existing transcript**.

## Hard boundaries

- Treat the existing transcript, timestamps, and speakers as immutable input.
- Do not open or process audio.
- Do not run pyannote, GigaAM, Whisper, Podlodka, gain, denoising, extraction, hole filling, or transcript correction.
- Do not generate a full-meeting summary. Full summaries and comparisons between different LLMs belong to Stage 3.
- The only LLM allowed in Stage 2b is the already selected local **Qwen3-8B Q5_K_M**, and only for pair classification or short chapter titles.
- Do not overwrite any artifact under `results/asr/2/`, `results/chunking/2/`, `results/llm/2/`, or `results/reports/2/`.

## Completed path — use as baseline, never repeat

The latest branch agent already completed:

1. full-file pyannote + GigaAM v3 ASR;
2. same-speaker adjacent tiny2 attempts:
   - 20–50 words / 0.80 → 95 chunks;
   - 40–80 words / 0.70 → 63 chunks;
   - 60–120 words / 0.65 → 48 chunks;
3. generation of the 63 Qwen titles;
4. one-shot merge of all 63 titles → 4 groups, with ids 19–62 collapsed into one ~16-minute tail;
5. refinement of those groups → 49 mostly single/pair groups.

Do not run:

- `scripts/run_stage2_asr.py`;
- `scripts/hf_gate_pyannote.py`;
- `scripts/chunk_stage2.py`;
- `scripts/title_stage2.py` for the same 63 chunks;
- `scripts/merge_titles_stage2.py`;
- `scripts/refine_title_merge_stage2.py`.

Do not add a fourth threshold to the old same-speaker packing recipe. Attempt 3 already produced an over-wide ~4-minute chunk.

## Target

Produce **8–20 chapters** for the ~24.5-minute meeting; prefer roughly **12–18**.

Every result must preserve:

- complete chronological coverage of source leaf ids;
- no missing, duplicated, or reordered leaf ids;
- original timestamps and text;
- explicit audit logs for every merge.
- timestamps copied only from source-segment boundaries.

## Timestamp policy

An LLM must never generate, adjust, round, or validate timestamps.

For every chapter:

- boundaries may occur only between source leaves;
- `start` must equal the first source leaf's `start`;
- `end` must equal the last source leaf's `end`;
- preserve `source_ids`, `start_source_id`, `end_source_id`;
- for A/B, source leaves and `timing_source` come from `results/chunking/2/attempt_2_chunks_titled.json`;
- for C/D, source leaves and `timing_source` come from `results/asr/2/gigaam_v3_rnnt/meeting_sample.json`;
- set `timing_method` to `source_boundaries`;
- never split a source leaf because word-level timestamps are unavailable;
- attach empty-text ASR segments to a neighbor deterministically and keep them in coverage.

Implement a deterministic validator. It must reject chapters if any timestamp differs from the source JSON, source ids are non-consecutive, coverage has gaps or duplicates, or chapter order changes. Run title generation only after this validation. A title response may not modify boundaries.

## Merge log

Each pass must write `results/chunking/2b/merge_log_passN.json` conforming to `docs/schemas/chunk_merge_log.schema.json`.

Each operation records:

```json
{
  "op": "merge",
  "source_ids": [12, 13],
  "start": 366.2,
  "end": 409.0,
  "old_titles": ["...", "..."],
  "new_title": "...",
  "reason": "same_topic"
}
```

After every pass, flatten all `source_ids` into `leaf_ids_covered`. It must exactly equal `leaf_ids_expected` (0 through 62 for the Stage 2 attempt-2 baseline). Reject the pass if there is any gap, duplicate, or reorder.

Never ask an LLM to regroup the complete list of 60+ ids. Enforce:

- for A/B, `max_ids_per_group = 8`;
- for every experiment, `max_duration_sec = 180`;
- do not cap the number of short ASR leaves in C/D; exact duration and coverage are the constraints.

## Experiments — run all four independently

Do not feed one experiment's chapters into another unless that experiment explicitly defines an internal second pass. Produce one candidate chapter list and one review sheet per hypothesis. Reaching 8–20 chapters does not skip Experiment D.

### Experiment A — adjacent title embeddings

Reuse the existing 63 titles. Embed titles, not raw transcript chunks, with the existing `cointegrated/rubert-tiny2`.

- Adjacent merges only.
- At most three thresholds: 0.85, 0.80, 0.75.
- Apply group-size and duration caps.
- Write a separate artifact and merge log for every threshold.
- Do not call an LLM during grouping.

Select the valid threshold closest to 12–18 chapters. Qwen may create one title per final group, using only member titles plus the first and last 40 words of the group.

### Experiment B — pairwise Qwen decisions

- Present exactly one adjacent pair per call.
- Ask whether both chapters belong to the same topic.
- Merge only on an explicit valid yes and only if both caps allow it.
- Generate the merged title from the two old titles.
- Move forward without skipping an item.
- Run at most two complete passes.
- If the model returns ids other than the exact presented pair, record `keep`.

Do not ask Qwen to segment or summarize the full meeting.

### Experiment C — cross-speaker packing

Build new units from the immutable ASR rows. A unit may include adjacent different speakers when the gap is at most 2 seconds, because a question and answer can be one topic.

- Do not split a turn unless it exceeds roughly 80 words.
- Run one adjacent tiny2 configuration: 40–80 words / 0.70.
- Do not lower the raw-text cosine threshold below 0.70.
- If the result has 8–40 chunks, Qwen may generate short titles of at most 10 Russian words.
- If it still has more than 20 chunks, apply one title-embedding merge pass using the Experiment A protocol.

### Experiment D — late chunking

Run this as an independent candidate directly over immutable ASR segments.

Primary model: `jinaai/jina-embeddings-v3` (multilingual, approximately 570M parameters, 8192-token context). Use one long-context model only. Do not run a model bakeoff. Do not install a missing package without explicit user approval; if the model cannot run with the existing environment, stop this experiment and report the missing dependency.

The alternatives to document, but not execute in this run, are:

- `Alibaba-NLP/gte-multilingual-base` — 305M, 8192 tokens;
- `BAAI/bge-m3` — 568M, 8192 tokens;
- `Qwen/Qwen3-Embedding-0.6B` — 0.6B, 32K tokens; long-context capable, but token-span pooling is less canonical for late chunking.

Algorithm:

1. Treat each source ASR segment as an indivisible timed atom.
2. Build **240-second** context windows with **60-second overlap**. Aim for roughly 300–600 words per window and never exceed the model token limit.
3. Run the transformer over the complete context window before pooling.
4. Mean-pool contextual token vectors for each atom's exact token span.
5. Compute cosine similarity between adjacent atom embeddings.
6. If a boundary appears in multiple overlapping windows, average its scores.
7. Select local cosine minima deterministically, subject to:
   - minimum chapter duration: 45 seconds;
   - preferred duration: 75–150 seconds;
   - hard maximum duration: 180 seconds.
8. If no strong boundary occurs before 180 seconds, select the deepest valid minimum in that interval.

The 240-second value is an embedding context window, not a chapter size. It should normally contain two or three final chapters. The expected output is 8–20 chapters, preferably 12–18.

Do not use Qwen to select boundaries. After source-boundary validation, Qwen may generate a short Russian title for each final chapter.

## Human review

For each experiment A–D, write a separate `review_sheet.json` containing only:

- `method`;
- `chapter_id`;
- exact `start` and `end`;
- `title`;
- `source_ids`;
- `timing_source`;
- `timing_method`.

Do not read or score anything under `eval/`. A human reviewer will keep private ratings in `eval/2b_chapter_review.json` using:

- `timing_exact` — automated source-boundary check;
- `boundary_quality`: 0 (inside one topic), 1 (debatable), 2 (clear topic change);
- `title_relevance`: 0 (wrong), 1 (partial), 2 (matches the interval);
- `too_short`, `too_broad`, and `missing_topic` flags.

Do not use Qwen or any other model as the quality judge.

## Outputs

- `results/chunking/2b/` — experiment artifacts, merge logs, timestamp validation, one candidate and review sheet per hypothesis, and final `chapters.json`;
- `results/llm/2b/` — only newly generated pair decisions or titles;
- `results/reports/2b/notes.md` in Russian;
- `results/reports/2b/research_report.json`.

`chapters.json` must include `id`, `start`, `end`, `title`, `leaf_ids`, `speakers`, `n_words`, and text. Do not paste the full transcript into the report.

After A–D, stop and preserve all artifacts. Do not select a winner without human review. Do not start Stage 3, another embedding model, another LLM, ASR, or denoising in the same run.

Commit and push only Stage 2b artifacts and supporting code to **`cursor/stage1e-four-asr-be20`**. Never force-push.

Start now: validate immutable inputs → run independent A, B, C, and D candidates → validate source ids and exact timestamps → write review sheets and Russian reports → commit and push.

---
