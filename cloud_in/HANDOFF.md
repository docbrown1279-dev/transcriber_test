# HANDOFF — stage D3

| Field | Value |
|---|---|
| CURRENT stage | **D3 — insights + LLM report** |
| Branch | `cursor/demo-d3-insights` |
| Contract of the exchange | read **`cloud_in/`** + product paths in the prompt (`agent_docs/instructions/`, `agent_docs/contracts/`); write reports and insight artifacts to **`cloud_out/`**; code to `src/`, tests to `tests/`. Do **not** read `docs/research_results/` |
| Role | `cloud_in/agent/AGENTS.md` + `cloud_in/agent/rules.md` |
| Task | `cloud_in/prompt.md` → `agent_docs/instructions/coder_D3.md`, `tester_D3.md` |
| Gate | G3.0–G3.9 in `agent_docs/contracts/quality_gates.md` |
| Secrets needed | `GEMINI_API_KEY` (default backend). No `HF_TOKEN`. Do not open `.env` |
| Deliverables | `cloud_out/gate_D3.md`, `cloud_out/run_meta.json`, `cloud_out/artifacts/voice_002/{insights.json,report.json,report.md}`, code + tests, **push branch** (no PR) |

## Order of work

1. Preflight: role files, prompt, packed inputs (`STACK.md`, `transcript.json`, `chapters.json`)
2. Host inventory into `run_meta.json`
3. Install approved D3 dependency: `httpx` in extra `llm` (Gemini SDK already present)
4. Implement `coder_D3.md` (base_llm.yaml, extract, report, markdown, openai_compat, G3)
5. Tests per `tester_D3.md`
6. **Required:** extract + report on packed chapters+transcript → `cloud_out/artifacts/voice_002/`
7. Run gate G3.0–G3.9, write `cloud_out/gate_D3.md`
8. Append progress, commit, **push this branch**. Do **not** open a PR — local operator runs `./scripts/cloud_pr.sh` after pull/ingest.

## Forbidden in this handoff

`eval/`, `.env`, `data/` (use only packed `cloud_in/inputs/`), `.cursor/`, `docs/research_results/`,
`docs/` writes, audio processing, ASR/chunking re-runs, llama.cpp / GGUF, web-upload,
force-push, **opening a pull request**. A missing input or unmet gate → `BLOCKED.md` / `FAIL`
report, not a lowered threshold.

## Next stages (context only — do not start)

D4 web demo · D5 hardware.
