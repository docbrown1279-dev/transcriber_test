# Stage D3 — insights + report

## 2026-09-06 — Planner (Phase A)
- STATUS: PLAN_DRAFT
- Predecessor D2: HUMAN_GATE PASS; 14 chapters packing C + P1; absorb <5 s
- Local data pack: `data/voice_002/{transcript.json,transcript.md,chapters.json}` (chapters copied from `results/d2_cloud/chapters.json`); source_ids cover 267 nonempty segments, missing/dup=0
- Plan: `agent_docs/plans/draft_D3_scope.md`
- LLM wrapper: `agent_docs/plans/draft_llm_wrapper.md` (prompt files + `config/llm/*.yaml` presets; thin LlmClient; hydrate times from segment_id)
- Frozen prompts: `agent_docs/contracts/prompts/{extract_v1,report_v1}.md` + schemas; `title_p1_v1.schema.json` extracted for D2 client cleanup
- Contracts updated: artifacts (hydration + requires transcript), G3.0, config load order, LlmClient.complete(+prompt_id, json_schema)
- Not packed: `cloud_in/` stays D2 until user ✅ Phase B
- Awaiting ✅: wrapper §7, llama-cpp-python extra llm-local (local only), call budget 40, no 3c filter bakeoff
- Next after ✅: `instructions/coder_D3.md`, `tester_D3.md`, pack chapters+transcript, branch `cursor/demo-d3-insights`

## 2026-09-06 — Planner (Phase A, revision 2)
- STATUS: PLAN_DRAFT
- LLM wrapper revised: API-only in cloud/demo; `llm.mode: local` reserved, no llama.cpp on D3
- One `config/base_llm.yaml` (example in `agent_docs/contracts/llm/base_llm.yaml`); backends gemini/nvidia/qwen via `api_key_env` names from `.env.example`
- Schemas in `llm/schemas/`; prompts in `llm/prompts/<purpose>/vN_*.md`; extra_config path or null
- openai_compat to be implemented for NVIDIA/Qwen; local_llama stays stub
- Q3 updated in draft_demo_roadmap.md
- Remaining: openai package vs httpx; confirm NVIDIA/Qwen model ids and Qwen base_url

## 2026-09-06 — Planner (Phase A, revision 3)
- STATUS: PLAN_DRAFT
- Backends now include `base_url` (Gemini null). extra_config backend-only, unique API keys
- Tasks renamed to folders: `chapter_titles`, `meeting_insights.{extract,report}`; no task extra_config
- Deleted extra/nvidia.yaml and extra/qwen.yaml (url moved onto backends)

## 2026-09-06 — Planner (Phase B)
- STATUS: INSTRUCTIONS_READY
- Manual: manuals/llm.md (backends, tasks, schemas, examples); configuration_guide + manual_testing D3
- Instructions: agent_docs/instructions/coder_D3.md, tester_D3.md
- Pack: cloud_in HANDOFF/prompt/STACK; inputs/artifacts/voice_002/{transcript.json,transcript.md,chapters.json}
- Approved dep: httpx in extra llm; no llama.cpp
- Branch: cursor/demo-d3-insights
- Next: /cloud_push (or cloud_handoff.sh); Cloud Agent on that branch

## 2026-09-06 — Cloud Agent
- STATUS: READY_FOR_TEST
- Implemented layered LLM configuration, Gemini and OpenAI-compatible transports, source-hydrated insights, report generation, Markdown export, pipeline stages, and G3 checks.
- Added offline unit, contract, cassette, registry, and packed-artifact integration coverage for D3.

## 2026-09-06 — Cloud Agent (gate complete)
- STATUS: TEST_PASS
- Live packed run: `cloud_out/artifacts/voice_002/{insights.json,report.json,report.md}`
- Gate: `cloud_out/gate_D3.md` verdict PASS (G3.0–G3.9)
- Adjustments: extract/report token budgets raised to 4096; five digitized key points filtered post-hydration
- Branch `cursor/demo-d3-insights` pushed (no PR)


