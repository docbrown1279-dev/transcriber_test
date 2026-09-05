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
