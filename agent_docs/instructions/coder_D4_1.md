# Coder instructions — stage D4.1 (perf / pipeline A|B)

Status precondition: user ✅ on D4.1 plan; then implement for Tester measurements.
Plan: [`../plans/draft_D4_1_scope.md`](../plans/draft_D4_1_scope.md).
Tester: [`tester_D4_1.md`](tester_D4_1.md).

Write scope: `src/`, stage-scoped `config/`, optional `scripts/` for local bench only.
Do **not** edit `tests/`, `docs/`, or Planner progress files (Tester/Planner own those).
Do **not** install new packages without user approval.
English comments; no secrets in logs.

## Goal

1. **Instrumentation** so Tester can record per-stage wall time + peak RSS (process or cgroup if available) without Docker limits yet.
2. Implement two runnable modes for fair A/B on the same audio:
   - **A — sequential + batch titles**
   - **B — ASR-slice pipeline** with incremental packing C and async title calls overlapping the *wait* for API (not overlapping ASR CPU)

Insights/report stay **after** titles path (separate timing section). Streaming UI is out of scope unless time remains after B works.

## Explicit non-goals

- Docker, `--cpus`/`--memory` (D5).
- Parallel ASR slices / multi-process GigaAM.
- Running rubert *during* GigaAM forward (between slices only).
- Changing VAD/diarization order (still full-file before ASR loop).
- New deps; Playwright.

## Files (expected touch set — adjust if structure differs)

```
src/transcriber/pipeline/…          # orchestrator / steps / optional pipeline_b
src/transcriber/asr/gigaam.py       # slice callback or iterator hook (keep model loaded)
src/transcriber/chunking/packing_c.py   # incremental helpers if needed (pure functions OK)
src/transcriber/llm/titles.py       # batch titles (A) + single-chapter title (B)
src/transcriber/config/schema.py    # flags: pipeline_mode a|b, thread caps
config/base.yaml / profiles/demo.yaml
scripts/bench_d4_1.py               # optional CLI: --mode a|b --audio PATH --out report.json
```

Prefer smallest diffs: reuse `PackingCChunker` logic; extract `pack_speaker_pieces` / merge online rather than rewrite.

## Variant A (batch)

After full `transcript.json` + `chapters.json` (current chunker):

- One (or few) LLM call(s): list of chapter texts → list of short titles.
- Validate uniqueness / max words / stamp ban; fallback per-chapter on partial failure.
- Record: `titles_llm_calls`, `titles_wall_sec`, stage RSS if possible.

## Variant B (slice pipeline)

Preconditions: `audio.json`, `speech.json`, `turns.json` already exist (normalize/VAD/diar done once).

Loop (single process or ASR worker that yields slices):

1. Transcribe **next** ASR slice only (GigaAM stays loaded; **no other heavy CPU** during this step; threads ≤2).
2. Append segment(s) to running transcript buffer.
3. Run **incremental** packing C:
   - speaker pack on buffer;
   - embed **new** pack unit(s) only when possible;
   - commit a chapter only when merge decides not to glue with the new neighbor (or duration cap); keep tail provisional.
4. If chapter committed and still untitled → **start async** title API request (do not block ASR on response body).
5. Immediately begin next ASR slice while title future(s) run.
6. EOS: flush provisional chapter(s); await outstanding title futures; write final `chapters.json` / `transcript.json`.

Rules:

- Glue always waits for the next piece before committing (except EOS).
- `absorb_shorter_than_sec` must not silently rewrite already-sent titled chapters; prefer absorb only on still-open tail, or document defer-to-EOS policy in the bench report.
- Peak RSS: log after diar, during ASR loop (with rubert loaded or not), after ASR unload if any.
- If RSS unsafe: document failure; do not silently disable titles mid-run without reporting.

## Thread / memory policy

- Wire `app.onnx_threads` into Silero ORT `SessionOptions` (currently unused).
- Cap torch/OMP/`intra_op` to **2** for demo-oriented runs (config, not hardcoded magic only).
- Do not load local GGUF Qwen in this stage.

## Bench CLI / report shape (for Tester)

Output JSON (path under `agent_docs/reports/` or job dir — Tester will copy to `agent_docs/reports/d4_1/`):

```json
{
  "mode": "a|b|baseline",
  "audio": "...",
  "duration_sec": 0,
  "host_note": "unconstrained | later cgroup",
  "stages": [{"name": "...", "wall_sec": 0, "peak_rss_mb": null}],
  "titles_llm_calls": 0,
  "time_to_first_titled_chapter_sec": null,
  "time_to_all_titles_sec": null,
  "total_wall_sec": 0,
  "notes": ""
}
```

## Acceptance (Coder → READY_FOR_TEST)

- [ ] Baseline path still works (current pipeline or mode A without batch if batch not ready — say which).
- [ ] Mode A: batch titles runnable; call count ≪ chapter count on multi-chapter fixture.
- [ ] Mode B: incremental commit + async titles; ASR not CPU-overlapped with rubert/LLM decode.
- [ ] Bench script or documented `uv run` commands produce the JSON above.
- [ ] `uv run ruff check src/` / `mypy src/` / `bandit -r src/ -ll` clean for touched code.
- [ ] Append `READY_FOR_TEST` to `agent_docs/progress/stage_D4_1.md` with commands run.

## Handoff

@Tester follows [`tester_D4_1.md`](tester_D4_1.md): unconstrained timings first, then A vs B.
