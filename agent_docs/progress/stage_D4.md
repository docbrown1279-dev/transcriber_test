# Stage D4 — web demo (local)

## 2026-09-06 — Planner
- STATUS: INSTRUCTIONS_READY
- Plan: `agent_docs/plans/draft_D4_scope.md`
- Instructions: `agent_docs/instructions/coder_D4.md`, `tester_D4.md`
- Mode: **local only** (no cloud handoff)
- UI stubs: `src/transcriber/web/static/stubs/` (+ `/stubs/*` routes)
- Decisions: max_minutes=30 warn+trim; loopback exempt from IP/day limit; no Playwright; backend module smoke E2E v0
- Next: Coder implements on branch `cursor/demo-d4-web` (or local commits); then Tester; HUMAN_GATE in browser
