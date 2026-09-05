# HANDOFF — stage D2

| Field | Value |
|---|---|
| CURRENT stage | **D2 — chunking (packing C) + chapter titles (P1 / Gemini)** |
| Branch | `cursor/demo-d2-chapters` |
| Contract of the exchange | read **`cloud_in/`** + product paths in the prompt (`agent_docs/instructions/`, `agent_docs/contracts/`); write reports and chapter artifacts to **`cloud_out/`**; code to `src/`, tests to `tests/`. Do **not** read `docs/research_results/` |
| Role | `cloud_in/agent/AGENTS.md` + `cloud_in/agent/rules.md` |
| Task | `cloud_in/prompt.md` → `agent_docs/instructions/coder_D2.md`, `tester_D2.md` |
| Gate | G2.0–G2.8 in `agent_docs/contracts/quality_gates.md` |
| Secrets needed | `GEMINI_API_KEY`, `HF_TOKEN` |
| Deliverables | `cloud_out/gate_D2.md`, `cloud_out/run_meta.json`, `cloud_out/artifacts/voice_002/chapters.json`, code + tests, **push branch** (no PR) |

## Order of work

1. Preflight: role files, prompt, packed inputs (`STACK.md`, `artifacts/voice_002/transcript.json`)
2. Host inventory into `run_meta.json`
3. Install approved D2 dependencies (`uv add` / extras for embed + Gemini)
4. Implement `coder_D2.md` (replicate packing C + tiny2 0.70 + P1 — no bakeoffs)
5. Tests per `tester_D2.md`
6. **Required:** chunk + titles on packed transcript → `cloud_out/artifacts/voice_002/chapters.json`
7. Run gate G2.0–G2.8, write `cloud_out/gate_D2.md`
8. Append progress, commit, **push this branch**. Do **not** open a PR — local operator runs `./scripts/cloud_pr.sh` after pull/ingest.

## Forbidden in this handoff

`eval/`, `.env`, `data/` (use only packed `cloud_in/inputs/`), `.cursor/`, `docs/research_results/`,
`docs/` writes, audio processing, ASR re-runs, insights/report/web-upload, late-chunking bakeoff,
force-push, **opening a pull request**. A missing input or unmet gate → `BLOCKED.md` / `FAIL`
report, not a lowered threshold.

## Next stages (context only — do not start)

D3 insights/report · D4 web demo · D5 hardware.
