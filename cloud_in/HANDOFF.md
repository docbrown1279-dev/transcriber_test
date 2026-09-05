# HANDOFF — stage D0

| Field | Value |
|---|---|
| CURRENT stage | **D0 — application skeleton, ports and stubs** |
| Branch | `cursor/demo-d0-skeleton` |
| Contract of the exchange | read **`cloud_in/`** + product paths listed in the prompt (`agent_docs/instructions/`, `agent_docs/contracts/`); write reports to **`cloud_out/`**; code to `src/`, tests to `tests/`. Do **not** read `docs/research_results/` |
| Role | `cloud_in/agent/AGENTS.md` + `cloud_in/agent/rules.md` |
| Task | `cloud_in/prompt.md` → `agent_docs/instructions/coder_D0.md`, `tester_D0.md` |
| Gate | G0.0–G0.7 in `agent_docs/contracts/quality_gates.md` |
| Secrets needed | none for D0 (`HF_TOKEN` / `GEMINI_API_KEY` start at D1 / D3) |
| Deliverables | `cloud_out/gate_D0.md`, `cloud_out/run_meta.json`, code + tests, PR |

## Order of work

1. Preflight: role files, prompt, packed inputs (`STACK.md`, `inputs/audio/test_voice.m4a`, `inputs/artifacts/baseline_*.json`)
2. Host inventory into `run_meta.json`
3. `uv` project + approved dependencies
4. Implement `coder_D0.md` steps 2–14
5. Tests per `tester_D0.md`
6. Run gate G0.0–G0.7, write `cloud_out/gate_D0.md`
7. Append progress, commit, open the PR

## Forbidden in this handoff

`eval/`, `.env`, `data/`, `.cursor/`, `docs/research_results/`, `docs/` writes, heavy model
packages, API calls, audio processing, force-push. A missing input or an unmet gate is a
`BLOCKED.md` / `FAIL` report — not a lowered threshold.

## Next stages (for context only, do not start them)

D1 speech → transcript (gate: Russian word ratio ≥ 0.90) · D2 chapters + titles · D3 insights and
report · D4 web demo · D5 hardware run at 2 vCPU / 8 GiB.
