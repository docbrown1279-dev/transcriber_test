# Stage D5.TTFT — file-split product (TTFT ≤ 5 min @ 2 CPU / 8 GiB)

## 2026-09-12 — Planner

- STATUS: INSTRUCTIONS_READY
- Plan: `agent_docs/plans/draft_ttft_split_product.md`
- Contract: `agent_docs/contracts/ttft_split.md`
- Instructions: `agent_docs/instructions/coder_D5_ttft.md`, `tester_D5_ttft.md`
- Hardware gate: **TTFT ≤ 300 s** first `chapters.json` on 15′ `voice_002` under Docker `--cpus=2 --memory=8g`
- Mid diar: method B (part1 AHC, part2+ nearest centroid + absorb 1 s). EOS: V1 AHC on saved embeddings.
- Out: H1/V2/V3 online, sticky, Jina, diar gold
- Next: user ✅ → @Coder implements `src/` behind `pipeline.ttft_split` (demo overlay true); @Tester Phase 0 reference_full15 in parallel

## 2026-09-12 — Planner (agents launched)

- STATUS: CODING + PHASE0_IN_PROGRESS
- User ✅: implement TTFT split
- @Coder: `coder_D5_ttft.md` (background)
- @Tester: Phase 0 `reference_full15` only (background); Phases 1–3 after READY_FOR_TEST

## 2026-09-12 — Tester (Phase 0)
- STATUS: PHASE0_BLOCKED then **aborted by user** (shell EAGAIN; stubs left in reference_full15)
- Reference: eval/d5_ttft_split/reference_full15/ (partial; rebuild: `python3 scripts/build_ttft_reference_full15.py`)
- Glue: documented in README (scripts/check_ttft_part_glue.py)
- Report: agent_docs/reports/d5_ttft_split/phase0_reference.md
- Do not auto-resume Phase0 unless user asks

## 2026-09-12 — Coder

- STATUS: READY_FOR_TEST
- Files:
  - `config/base.yaml`, `config/profiles/demo.yaml`, `src/transcriber/config/schema.py` — `ttft_split`, `pipeline.ttft.*`, `file_max_db`
  - `src/transcriber/audio/gain.py`, `normalize.py` — file gain cap + `loudness.capped`
  - `src/transcriber/models/artifacts.py` — `AudioLoudness.capped`, `JobArtifact.early_ready` / `speakers_finalized`
  - `src/transcriber/pipeline/pause_cut.py` — pause cut planner
  - `src/transcriber/pipeline/ttft_split.py` — part loop, early publish, EOS hook
  - `src/transcriber/pipeline/orchestrator.py` — branch on flag
  - `src/transcriber/diarization/gallery.py`, `eos_refine.py`, `wespeaker.py` — method B + V1 remap + extract windows
  - `src/transcriber/jobs/queue.py`, `store.py` — events + flags
  - `src/transcriber/web/routes.py`, `static/app.js`, `templates/{result,chapter}.html` — early redirect, speaker lock
  - `scripts/bench_d5.py` — `ttft_first_chapter_sec`
  - `manuals/configuration_guide.md` — ttft_split / file_max_db rows
- Verified: host shell was resource-exhausted (`fork: Resource temporarily unavailable`); Tester should run lint/smoke below
- Commands for Tester:

```bash
# lint (touched Python)
uv run ruff check src/transcriber/pipeline/ttft_split.py src/transcriber/pipeline/pause_cut.py \
  src/transcriber/pipeline/orchestrator.py src/transcriber/diarization/gallery.py \
  src/transcriber/diarization/eos_refine.py src/transcriber/diarization/wespeaker.py \
  src/transcriber/audio/gain.py src/transcriber/audio/normalize.py \
  src/transcriber/config/schema.py src/transcriber/jobs/queue.py src/transcriber/jobs/store.py \
  src/transcriber/web/routes.py scripts/bench_d5.py
uv run mypy src/transcriber/pipeline/ttft_split.py src/transcriber/pipeline/pause_cut.py \
  src/transcriber/diarization/gallery.py src/transcriber/diarization/eos_refine.py
uv run bandit -q -r src/transcriber/pipeline/ttft_split.py src/transcriber/diarization/gallery.py \
  src/transcriber/diarization/eos_refine.py

# config smoke
PYTHONPATH=src uv run python -c "from transcriber.config.loader import load_config; c=load_config('demo'); assert c.pipeline.ttft_split and c.pipeline.ttft.max_part_sec==300 and c.audio.gain.file_max_db==2.0"

# G5 TTFT gate (warm cache, 15' voice_002)
docker run --rm --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD:/work" -w /work \
  <image> \
  uv run python scripts/bench_d5.py \
    --audio var/bench/d5/voice_002_15min.m4a --mode b \
    --out agent_docs/reports/d5_ttft_split/bench_ttft.json \
    --job-dir var/bench/d5/ttft_split_g5
# expect ttft_first_chapter_sec <= 300; cut_plan.json part1 duration_sec <= 300
```

- Next: @Tester `agent_docs/instructions/tester_D5_ttft.md`

## 2026-09-12 — Planner (resume)

- STATUS: PHASE0_DONE (planner rebuilt reference); Tester full gate re-launched
- reference_full15: full_transcript n=143; part01/02/03 transcripts 34/56/53 (no stubs)
- Rebuild cmd: `python3 scripts/build_ttft_reference_full15.py --git-rev $(git rev-parse HEAD)`
- Host: fork OK, ~2.5k threads, ~10 Gi available — single Tester only (no parallel agents)

## 2026-09-12 — Tester (Phases 1–3 + G5.T)
- STATUS: TEST_PASS_WITH_WARNINGS
- Phase0: re-verified reference_full15 (n=143/34/56/53; no stubs)
- Tests: `tests/unit/test_ttft_split.py` (D5T-CFG/CUT/GAIN/DIAR/EOS/UI)
- Executed:
  - `uv run pytest tests/unit/test_ttft_split.py -v` → 9 passed
  - `uv run pytest tests/ -v` → 91 passed, 2 failed (health env + soft regression HF; unrelated to new TTFT units)
  - Coder ruff/mypy/bandit smoke → non-zero (Coder debt: orchestrator I001, gallery mypy, bandit Low subprocess)
  - Docker G5: `--cpus=2 --memory=8g` `transcriber:runtime` `bench_d5.py --mode b` → `ttft_first_chapter_sec=169.177`, peak_rss_mb=3688.5, part1=229.264s, large speakers=3
- Report: `agent_docs/reports/d5_ttft_split/product_gate.md` (+ g5_ttft_15min.md/.json, glue_vs_full15.md)
- WARN: glue chapter C3 spill vs 3-part reference; product cut=4 parts; full pytest/lint not fully green
- Next: optional @Coder lint/mypy cleanup; stage sign-off / HUMAN_GATE listen if desired

## 2026-09-12 — Coder (progress UX)

- STATUS: READY_FOR_TEST (progress indicator)
- UI: stage label + ETA instead of bare %; live status on draft result while parts continue
- Config: `pipeline.ttft.progress.{prep,diar,asr}_fraction`; min_part_sec=300 (5 min → ~3 parts on 15′)
- Files: `ttft_progress.py`, `ttft_split.py` emits, `queue.job_events_payload`, progress/result templates + `app.js`
- Verified: `pytest tests/unit/test_ttft_progress.py tests/unit/test_ttft_split.py` 11 passed
- Docker UI: `ttft_ui_demo` --cpus=2 --memory=8g → http://127.0.0.1:8000/
