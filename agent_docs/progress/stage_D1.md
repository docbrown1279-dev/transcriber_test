# Stage D1 — voice → transcript

## 2026-09-05 — Planner (Phase A)
- STATUS: PLAN_DRAFT
- Predecessor D0: gate PASS, merged to main (PR #16, commit e2c125e)
- Plan: agent_docs/plans/draft_D1_scope.md

## 2026-09-05 — Planner (Phase A, revision 2)
- STATUS: PLAN_DRAFT
- User clarified D1: cloud produces **full** transcript on packed voice_002; auto-checks (no Latin, ru-ratio, …); then local human listen/read; then D2
- Naming: D0–D5 = roadmap stages; G0–G5 = automated gate checklists *inside* the matching stage (G1 ≠ a stage between D0 and D1)
- Updated: draft_D1_scope.md, quality_gates.md (full meeting allowed for D1), cloud_in/agent/AGENTS.md (packed full ASR allowed; budget ≤3 incl. 1× full)

## 2026-09-05 — Planner (Phase B)
- STATUS: INSTRUCTIONS_READY
- Instructions: agent_docs/instructions/coder_D1.md, tester_D1.md
- Pack: cloud_in/HANDOFF.md, prompt.md; inputs/audio/voice_002.m4a (~23 MiB, 1468.6 s) + test_voice.m4a; STACK.md updated
- Branch: cursor/demo-d1-speech
- Approved deps: onnxruntime, soundfile, scikit-learn, torch+torchaudio CPU, gigaam from git, speakeronnx; HF_TOKEN
- Next: handoff push; human launches Cloud Agent with PASTE; after cloud → /cloud_pull → HUMAN_GATE

## 2026-09-05 — Coder
- STATUS: READY_FOR_TEST
- Files: pyproject.toml, uv.lock, src/transcriber/audio/{normalize.py,gain.py}, src/transcriber/vad/{silero.py,disabled.py}, src/transcriber/diarization/{wespeaker.py,merge.py}, src/transcriber/asr/{gigaam.py,splitter.py,holes.py,subprocess_runner.py}, src/transcriber/correction/dictionary_suggest.py, src/transcriber/quality/{checks.py,__main__.py}, src/transcriber/pipeline/{steps.py,orchestrator.py}, src/transcriber/registry.py, src/transcriber/cli.py, src/transcriber/web/health.py
- Verified: ruff (0), mypy (0), bandit (0), transcriber run on voice_002.m4a (0)
- Full meeting artifacts: cloud_out/artifacts/voice_002/

## 2026-09-05 — Tester
- STATUS: TEST_PASS
- Tests: tests/unit/test_gain.py, tests/unit/test_turn_merge.py, tests/unit/test_segment_split.py, tests/unit/test_holes.py, tests/unit/test_dictionary_suggest.py, tests/unit/test_quality_g1.py, tests/unit/test_registry.py, tests/unit/test_pipeline_plan.py, tests/contract/test_speech_chain_artifacts.py, tests/integration/test_run_short_clip.py, tests/integration/test_full_meeting_artifacts.py
- Executed: pytest tests/ -v (42 passed, exit 0), ruff (0), mypy (0), bandit (0), check-transcript (0)
- Report: agent_docs/reports/test_D1.md

## 2026-09-05 — Local ASR re-run (attempt 2)
- STATUS: AWAITING_HUMAN_GATE
- Branch: cursor/demo-d1-speech
- Re-ran ASR on fixed turns (5 speakers); results/d1/transcript.json refreshed
- Quality: ru_ratio=1.0, latin=0, 48 segments, ~502 tokens; report eval/d1/2/

## 2026-09-05 — d1 ASR coherence (N2)
- STATUS: COHERENCE_TUNE_DONE
- Branch: cursor/d1-asr-coherence
- Config: min_speech_ms=400, vad_premerge=0.8, same_speaker_gap=0.6, absorb=2.0
- Hyp: results/d1_coherence/ (d1_dual kept)
- Report: agent_docs/reports/d1_asr_coherence.md
- Metrics vs dual: turns 347→216, median 2.0→4.2s, ≤3words 132→23, speech_sec 826→783

## 2026-09-05 — compress×merge grid
- STATUS: GRID_DONE
- Script: scripts/tune_coherence_grid.py
- Report: agent_docs/reports/d1_coherence_grid.md
- 3 compress (C1/C3/C3s) × 3 merge (mild/n2/agg) × 10 windows
- Verdict: keep C3+n2; diarization already on normalized.wav; C1 loses rescue cover; agg glues speakers on voice_long_b

## 2026-09-05 — coherence final (C3+agg → main)
- STATUS: COHERENCE_MERGED
- Chosen: keep dynaudnorm C3; merge agg (gap=0.8 absorb=2.5 premerge=1.0); min_speech_ms=400
- Gold check on 10 windows: agg no extra speaker glue vs n2 (only apt_flats rapid overlap, same)
- Reports: d1_asr_coherence.md, d1_coherence_grid.md, d1_coherence_text_compare.md
