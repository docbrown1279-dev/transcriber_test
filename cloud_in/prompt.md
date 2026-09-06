# Stage D3 — insights + LLM report

You are the product development cloud agent. Read `cloud_in/agent/AGENTS.md` and
`cloud_in/agent/rules.md` first, then this prompt. The run is unattended: do not ask for approval,
install what the stage lists, finish with a gate report, insight artifacts, and a branch push
(no PR).

## Why this stage

D2 delivered `chapters.json` (packing C + P1 titles). D3 must produce **insights + a draft
report**: per-chapter extract, one report call, markdown render. LLM is **API-only**; default
backend Gemini 2.5 Flash. NVIDIA/Qwen are the same prompts via `openai_compat` + `base_url` in
`config/base_llm.yaml` — implement the client, do not live-call them in this gate.

Do not bakeoff extract filters or new prompt wording. Copy frozen files from
`agent_docs/contracts/llm/`. Human manual already exists: `manuals/llm.md` (do not rewrite).

Roadmap stages are `D0 → D1 → D2 → D3 → …`. **G3** is only the auto-check list inside D3.

## Task

1. Follow `agent_docs/instructions/coder_D3.md` step by step.
2. Follow `agent_docs/instructions/tester_D3.md` for tests and `[TEST-ID]`s.
3. Run extract + report on the packed transcript and chapters (required). **No ASR. No audio.**
4. Write `cloud_out/gate_D3.md` for checks G3.0–G3.9.

If instruction files and this prompt disagree, the instruction files win; note the discrepancy in
the gate report.

## Inputs

Packed for this stage (must pass preflight):

| Path | What |
|---|---|
| `cloud_in/inputs/STACK.md` | frozen demo stack — do not reopen bakeoffs |
| `cloud_in/inputs/artifacts/voice_002/transcript.json` | D1 T2 full-meeting transcript |
| `cloud_in/inputs/artifacts/voice_002/chapters.json` | D2 HUMAN_GATE PASS chapters (14) |
| `cloud_in/inputs/artifacts/voice_002/transcript.md` | human-readable dump for G3.5 / G3.9 only |

Also in git:

| Path | What |
|---|---|
| `agent_docs/instructions/coder_D3.md`, `tester_D3.md` | implementation and test specs |
| `agent_docs/contracts/*.md` and `agent_docs/contracts/llm/` | schemas, `base_llm.yaml`, prompts |
| `src/`, `config/`, `tests/` | D0–D2 code on the branch — extend it |

Do **not** open `docs/research_results/`, `docs/dev_specs.md`, `eval/`, `data/`, or `.env`.

## Approved dependencies

`httpx` in extra `llm` (OpenAI-compat). `google-genai` is already present. Install only via
`uv add` / documented extras. Do **not** add `openai`, `llama-cpp-python`, or GGUF downloads.

Secrets: `GEMINI_API_KEY` for the default backend. Never send audio to an API. Never print key
values.

## Gate D3 (must pass before push)

Checks G3.0–G3.9 from `agent_docs/contracts/quality_gates.md`, on
`cloud_out/artifacts/voice_002/{insights.json,report.json,report.md}` vs packed chapters +
transcript:

- G3.0 preflight (pack + `GEMINI_API_KEY`)
- G3.1 clock-gate after hydration
- G3.2 src segment belongs to the chapter
- G3.3 every key_point has src
- G3.4 digit groups occur in chapter text
- G3.5 agent: no invented owners/tasks
- G3.6 key_moments 5–12 (WARN outside)
- G3.7 no stamp prefixes
- G3.8 draft_warning true in demo
- G3.9 agent: ≥60% verifiable key_points

Also: `uv run pytest tests/ -v`, `ruff`, `mypy`, `bandit` exit 0.

## Deliverables

1. Code under `src/` / `config/` / `pyproject.toml`; tests under `tests/`
2. `cloud_out/artifacts/voice_002/{insights.json,report.json,report.md}`
3. `cloud_out/gate_D3.md` + `cloud_out/run_meta.json`
4. Progress lines in `agent_docs/progress/stage_D3.md`
5. Commit and **push** branch `cursor/demo-d3-insights`. Do **not** open a pull request.

## Stop-list

Do not: read `eval/` or `.env`; process or send audio; re-run ASR/VAD/chunking; implement
local llama.cpp; bakeoff prompts; weaken gate thresholds; force-push; open a PR; read meeting
text from `data/` (use the packed files only).
