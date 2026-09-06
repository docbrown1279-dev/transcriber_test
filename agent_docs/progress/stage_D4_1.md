# Stage D4.1 — backend performance (pre-Docker)

## 2026-09-06 — Planner
- STATUS: PLAN_DRAFT
- Plan: `agent_docs/plans/draft_D4_1_scope.md`
- Roadmap: insert between D4 (UI) and D5 (Docker + cgroup limits)
- Focus: parallelize safe work; batch LLM titles; ONNX audit (`onnx_threads` wiring)
- Out of scope: Docker `--cpus`/`--memory` (D5)
- Next: user ✅ → Phase B instructions (`coder_D4_1.md`, `tester_D4_1.md`)

## 2026-09-06 — Planner (rev2)
- STATUS: PLAN_DRAFT
- Research: VAD/WeSpeaker cheap; GigaAM fast but ~1.6GiB peak; rubert C ~2s (not bottleneck); LLM titles/extract are wall
- Proposal: sequential heavy path; P0 batch titles; no ASR parallel; rubert keep unless RSS forces ONNX A/B
- Await ✅ → Phase B

## 2026-09-06 — Planner (rev3 / Phase B)
- STATUS: INSTRUCTIONS_READY
- User scheme B: ASR slice → incremental packing C → async title while next ASR; ASR exclusive on 2 cores
- Variant A: sequential + batch titles (kept)
- Instructions: `agent_docs/instructions/coder_D4_1.md`, `tester_D4_1.md`
- Tester may start Phase 0 baseline on current main before Coder A/B
- Next: @Tester Phase 0; @Coder harness + A/B; then Phase 1 compare

## 2026-09-06 — Phase 0 baseline
- Branch: `cursor/demo-d4-1-perf`
- Audio: 10 min trim `var/bench/d4_1/voice_002_10min.m4a`
- Job: `var/bench/d4_1/job_baseline_10min` (6 chapters, titles OK)
- Report: `agent_docs/reports/d4_1/baseline_unconstrained.md`
- Headline: diar~78s, asr~56s, titles 6× sequential ~15s, peak RSS ~1.65 GiB; chunk first pass polluted by HF DNS

## 2026-09-07 — Coder READY_FOR_TEST / Phase1 results
- STATUS: READY_FOR_TEST (harness landed); Phase1 compare done locally
- Mode A: `llm.titles_mode` batch via `apply_titles_batch`; bench `scripts/bench_d4_1.py --mode a`
- Mode B: `pipeline/pipeline_b.py` ASR slice → incremental pack → async titles
- Report: `agent_docs/reports/d4_1/compare_a_b.md`
- Lint: ruff clean on touched files

## 2026-09-07 — Close / merge
- STATUS: CLOSED
- Merged `cursor/demo-d4-1-perf` → `main` (`a857eef`)
- Default: `pipeline.toc_mode: b`; fallback `a` (batch titles)
- Final B bench: 6 LLM calls, TTFT ~20s, total ~119s from turns (ASR-dominated)
- Reports: `agent_docs/reports/d4_1/` (compare + gate updated)
- Next: D5 Docker + `--cpus=2 --memory=8g`
