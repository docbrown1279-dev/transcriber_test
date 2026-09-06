# Tester instructions — stage D4.1 (perf A/B, **local**)

Status precondition: for **Phase 0** (baseline) — can start on current `main` even before Coder finishes A/B.
For **Phase 1** (A vs B) — `agent_docs/progress/stage_D4_1.md` contains `READY_FOR_TEST`.

Plan: [`../plans/draft_D4_1_scope.md`](../plans/draft_D4_1_scope.md).  
Coder: [`coder_D4_1.md`](coder_D4_1.md).

**Local only.** No cloud handoff. No Docker / `--cpus` / `--memory` in this stage (that is D5).

Write scope: `tests/` (only if adding light unit tests for incremental pack helpers) + **reports** under `agent_docs/reports/d4_1/`.  
Do not edit `src/` (Coder), `docs/`, or secrets.

## What we are deciding

| Mode | Question |
|---|---|
| **baseline** | Current pipeline wall/RSS by stage (unconstrained host) |
| **A** | Full ASR → chunk → **batch** titles — total wall + LLM call count |
| **B** | ASR slice → glue → async title ∥ next ASR — total wall + **time to first titled chapter** |

Insights + summary: measure **once** as a tail after titles (same for A and B), or skip live LLM extract if budget — note which. Streaming UI is **not** required to pass the gate.

## Audio

Prefer (pick one primary, note duration):

1. Short: `data/test_voice.m4a` (~85 s) — smoke + RSS sanity.
2. Main: 10–15 min trim of `data/voice_002` **or** full meeting if machine OK — same file for all modes.

Do not mutate originals; copy/trim into job dir or `/tmp`.

## Phase 0 — baseline (unconstrained), now

Even without new code: run existing CLI/pipeline to titles (or until `chapters`+titles if already wired).

Record manually or via whatever stage `runtime_sec` already exists:

| Field | Required |
|---|---|
| host CPU/RAM (free text) | yes |
| audio duration_sec | yes |
| wall per stage: normalize, vad, diarize, asr, chunk, titles | yes if available |
| peak RSS if easy (`/usr/bin/time -v`, `ps`, or Coder harness) | best-effort |
| titles: N chapters, N LLM calls, titles wall | yes |
| total wall end-to-end | yes |

Write: `agent_docs/reports/d4_1/baseline_unconstrained.md` (+ `.json` if harness exists).

Commands (adapt to repo; examples):

```bash
# example — use project’s real serve/pipeline entry from manuals
uv run python -m transcriber.pipeline --help   # find actual flags
# or web upload on short clip and copy stage timings from job status
```

Mark slow/model runs clearly. No cgroup.

## Phase 1 — A vs B (after READY_FOR_TEST)

Same audio, same LLM backend/key, same thread caps (=2). Cold vs warm: note model cache state; prefer one warm-up discarded run, then measured run.

| ID | Check |
|---|---|
| `[D41-BENCH-01]` | baseline JSON/md present |
| `[D41-BENCH-02]` | mode A report: `titles_llm_calls` ≪ chapter count (batch worked) |
| `[D41-BENCH-03]` | mode B report: `time_to_first_titled_chapter_sec` filled; chapters eventually all titled |
| `[D41-BENCH-04]` | B did not run heavy CPU beside ASR during slice forward (Coder note / single-threaded ASR) |
| `[D41-BENCH-05]` | Compare table: total_wall A vs B; TTFT B vs (A titles start); peak RSS A vs B |
| `[D41-BENCH-06]` | Quality spot-check: 3–5 titles readable; no stamp phrases; incremental B chapter boundaries not insane vs A (globe check, not WER) |
| `[D41-BENCH-07]` | pytest still green: `uv run pytest tests/ -v` (skip slow if env lacks models — document) |

### Comparison table (put in report)

| metric | baseline | A | B |
|---|---:|---:|---:|
| total_wall_sec | | | |
| asr_wall_sec | | | |
| chunk_wall_sec | | | |
| titles_wall_sec | | | |
| titles_llm_calls | | | |
| time_to_first_titled_chapter_sec | n/a | n/a or late | |
| peak_rss_mb | | | |

Verdict line: which mode for demo default and why (wall / TTFT / RSS / complexity).

## Out of scope for pass/fail

- Docker 2 CPU / 8 GB (schedule D5 on winner).
- Playwright / browser stream of chapters.
- Full insights bakeoff (optional single tail timing only).
- Switching rubert → bge unless RSS forces a note for backlog.

## Report layout

```
agent_docs/reports/d4_1/
  baseline_unconstrained.md
  baseline_unconstrained.json    # optional
  compare_a_b.md                 # Phase 1
  mode_a.json
  mode_b.json
  gate_D4_1.md                   # PASS / PASS_WITH_WARNINGS / FAIL + verdict
```

## Gate

- **PASS:** Phase 0 + Phase 1 reports exist; table filled; pytest green; clear recommendation A or B (or “B for UX, A for simplicity”).
- **PASS_WITH_WARNINGS:** B OOMs or flaky API but A works; documented.
- **FAIL:** cannot measure or titles quality broken on both.

Append result to `agent_docs/progress/stage_D4_1.md` and one line to `agent_docs/progress/log.md`.
