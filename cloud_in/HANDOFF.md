# HANDOFF — stage D1

| Field | Value |
|---|---|
| CURRENT stage | **D1 — voice → full transcript (normalize, VAD, diarization, ASR)** |
| Branch | `cursor/demo-d1-speech` |
| Contract of the exchange | read **`cloud_in/`** + product paths in the prompt (`agent_docs/instructions/`, `agent_docs/contracts/`); write reports and full-meeting artifacts to **`cloud_out/`**; code to `src/`, tests to `tests/`. Do **not** read `docs/research_results/` |
| Role | `cloud_in/agent/AGENTS.md` + `cloud_in/agent/rules.md` |
| Task | `cloud_in/prompt.md` → `agent_docs/instructions/coder_D1.md`, `tester_D1.md` |
| Gate | G1.0–G1.7 in `agent_docs/contracts/quality_gates.md` (auto-checks **of stage D1**, not a separate roadmap step) |
| Secrets needed | `HF_TOKEN` (model download). No `GEMINI_API_KEY` for D1 |
| Deliverables | `cloud_out/gate_D1.md`, `cloud_out/run_meta.json`, `cloud_out/artifacts/voice_002/{transcript,quality,…}.json`, code + tests, **push branch** (no PR) |

## Order of work

1. Preflight: role files, prompt, packed inputs (`STACK.md`, `voice_002.m4a`, `test_voice.m4a`)
2. Host inventory into `run_meta.json`
3. Install approved D1 dependencies (`uv add` / extras `asr` + `diarize`)
4. Implement `coder_D1.md`
5. Tests per `tester_D1.md`
6. **Required:** full ASR pipeline on `cloud_in/inputs/audio/voice_002.m4a` → copy artifacts to `cloud_out/artifacts/voice_002/`
7. Run gate G1.0–G1.7, write `cloud_out/gate_D1.md`
8. Append progress, commit, **push this branch**. Do **not** open a PR — local operator runs `./scripts/cloud_pr.sh` after pull/ingest.

## Forbidden in this handoff

`eval/`, `.env`, `data/` (use only packed `cloud_in/inputs/`), `.cursor/`, `docs/research_results/`,
`docs/` writes, Gemini/LLM calls, chunking/titles/insights/web-upload, force-push, **opening a
pull request**. A missing input or unmet gate → `BLOCKED.md` / `FAIL` report, not a lowered
threshold.

## Next stages (context only — do not start)

D2 chapters + titles · D3 insights/report · D4 web demo · D5 hardware.
