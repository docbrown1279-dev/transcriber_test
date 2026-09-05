# Stage D0 — skeleton, stubs, cloud infra

## 2026-09-05 — Planner (Phase A)
- STATUS: PLAN_DRAFT
- Plans: agent_docs/plans/draft_demo_roadmap.md, draft_architecture.md, draft_cloud_workflow.md, draft_test_strategy.md
- Contracts: agent_docs/contracts/index.md, pipeline_artifacts.md, module_interfaces.md, config_profiles.md, quality_gates.md
- Frozen stack taken from docs/research_results (no re-evaluation): silero VAD, wespeaker ONNX diarization, GigaAM v3_rnnt, packing C + rubert-tiny2 0.70, LLM prompts P1/extract/report
- Open questions Q1–Q6 in draft_demo_roadmap.md §6 — Phase B blocked until answered
- Next: user approval, then instructions/coder_D0.md + tester_D0.md

## 2026-09-05 — Planner (Phase A, revision 2)
- STATUS: PLAN_DRAFT
- Q1–Q6 answered by user; decisions recorded in draft_demo_roadmap.md §6
- Exchange mechanism: cloud_in/ -> cloud_out/ (same flat exchange as research), agent role in cloud_in/agent/, inputs packed per stage, cloud agent runs a preflight check (G0.0)
- LLM split: gemini in cloud and demo, local llama.cpp Qwen3-8B for local gates; QWEN_API_KEY not provisioned in cloud
- local_llama promoted from stub to implemented component at stage D3
- Pre-handoff actions for the human: un-ignore cloud_in/ and cloud_out/ in .gitignore; git rm --cached eval/*.json
- Awaiting user approval to start Phase B

## 2026-09-05 — Planner (Phase B)
- STATUS: INSTRUCTIONS_READY
- Instructions: agent_docs/instructions/coder_D0.md, agent_docs/instructions/tester_D0.md
- Cloud role: cloud_in/agent/AGENTS.md, cloud_in/agent/rules.md (stable across stages)
- Handoff pack: cloud_in/HANDOFF.md, cloud_in/prompt.md, cloud_in/inputs/artifacts/baseline_{transformers,ninth}.json
- Pre-flight done: .gitignore now tracks cloud_in/ and cloud_out/ (prompts/ and var/ ignored); eval/*.json removed from the git index, files kept on disk
- Gate G0 extended: G0.5 plan command, G0.6 validate command, G0.7 healthz; D0 implements no model-backed stage
- D0 scope addition: models/legacy.py + `transcriber convert-legacy` — packed research transcripts use the research JSON shape
- Approved D0 dependencies: fastapi, uvicorn[standard], jinja2, python-multipart, pydantic, pydantic-settings, pyyaml, numpy, typer; dev: pytest, pytest-asyncio, httpx, ruff, mypy, bandit
- Next: user commits and pushes branch cursor/demo-d0-skeleton, then launches the cloud agent pointing at cloud_in/

## 2026-09-05 — Planner (pack hygiene)
- STATUS: INSTRUCTIONS_READY
- Cloud must not read docs/research_results/; local planner packs distilled STACK.md into cloud_in/inputs/
- Updated cloud_in/agent/AGENTS.md, prompt.md, HANDOFF.md; added cloud_in/inputs/STACK.md
- Product docs stay in git: agent_docs/instructions + contracts; long TЗ (docs/dev_specs.md) not required for D0

## 2026-09-05 — Planner (pack complete)
- STATUS: INSTRUCTIONS_READY
- Packed cloud_in/inputs/audio/test_voice.m4a (copy of data/test_voice.m4a, ~83 s)
- D0 uses audio for ffprobe/health smoke only; ASR still starts at D1
- Pack checklist: agent/, HANDOFF, prompt, STACK, audio, baseline artifacts ×2; product specs remain in agent_docs/
