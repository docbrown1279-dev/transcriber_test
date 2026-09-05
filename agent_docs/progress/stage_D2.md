# Stage D2 — chunking + chapter titles

## 2026-09-06 — Planner (Phase A+B)
- STATUS: INSTRUCTIONS_READY
- Predecessor D1: T2 in base.yaml; publishable transcript `data/voice_002/`; human narrative OK → proceed (HUMAN_GATE recorded on stage_D1)
- Strategy: replicate research packing C + rubert-tiny2 0.70 + title_p1_v1 (Gemini); no C/D or P1/P2 bakeoff in cloud; improvements only after local human gate
- Plan: agent_docs/plans/draft_D2_scope.md
- Instructions: agent_docs/instructions/coder_D2.md, tester_D2.md
- Pack: cloud_in/HANDOFF.md, prompt.md; inputs/artifacts/voice_002/{transcript.json,transcript.md}; STACK.md updated; D1 audio/baselines moved to .trash
- Branch: cursor/demo-d2-chapters
- Approved deps: sentence-transformers (+ CPU torch if needed), google-genai; secrets GEMINI_API_KEY + HF_TOKEN
- Next: cloud_handoff push; human launches Cloud Agent with PASTE; after cloud → /cloud_pull → HUMAN_GATE