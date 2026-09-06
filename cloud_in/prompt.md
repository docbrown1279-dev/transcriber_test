# Stage D2 — chunking + chapter titles

You are the product development cloud agent. Read `cloud_in/agent/AGENTS.md` and
`cloud_in/agent/rules.md` first, then this prompt. The run is unattended: do not ask for approval,
install what the stage needs, finish with a gate report, `chapters.json`, and a branch push
(no PR).

## Why this stage

D1 delivered a full-meeting transcript (Silero T2 hyp packed here). D2 must turn that transcript
into a **table of contents**: semantic chapters (packing C + `rubert-tiny2` 0.70) and LLM titles
(prompt P1 / `title_p1_v1` via Gemini 2.5 Flash).

**Replicate the closed research path first.** Do not bakeoff late chunking (D), pairwise LLM (B),
or prompt P2. Improvements are a later local ticket after the human gate — not this run.

Roadmap stages are `D0 → D1 → D2 → …`. The name **G2** is only the auto-check list *inside* D2.

## Task

1. Follow `agent_docs/instructions/coder_D2.md` step by step.
2. Follow `agent_docs/instructions/tester_D2.md` for tests and `[TEST-ID]`s.
3. Run chunking + titles on the packed transcript (required). **No ASR. No audio.**
4. Write `cloud_out/gate_D2.md` for checks G2.0–G2.8.

If instruction files and this prompt disagree, the instruction files win; note the discrepancy in
the gate report.

## Inputs

Packed for this stage (must pass preflight):

| Path | What |
|---|---|
| `cloud_in/inputs/STACK.md` | frozen demo stack — do not reopen bakeoffs |
| `cloud_in/inputs/artifacts/voice_002/transcript.json` | **primary** T2 full-meeting transcript (~24.5 min) |
| `cloud_in/inputs/artifacts/voice_002/transcript.md` | human-readable dump for G2.8 judgement only |

Also in git:

| Path | What |
|---|---|
| `agent_docs/instructions/coder_D2.md`, `tester_D2.md` | implementation and test specs |
| `agent_docs/contracts/*.md` | schemas, ports, configs, gate G2 |
| `src/`, `config/`, `tests/` | D0/D1 code on `main` — extend it |

Do **not** open `docs/research_results/`, `docs/dev_specs.md`, `eval/`, `data/`, or `.env`.

## Approved dependencies

`sentence-transformers` (model `cointegrated/rubert-tiny2`), CPU `torch` if required by the
embedder, and the official Gemini SDK (`google-genai` or the current Google GenAI package —
record the exact name in the gate). Install only via `uv add` / documented extras. Anything else
needs a written justification in the gate report.

Secrets: `GEMINI_API_KEY` (titles), `HF_TOKEN` (Hub download for tiny2). Never send audio to an API.

## Gate D2 (must pass before push)

Checks G2.0–G2.8 from `agent_docs/contracts/quality_gates.md`, measured on
`cloud_out/artifacts/voice_002/chapters.json` vs the packed transcript:

- G2.0 preflight (pack + secrets)
- G2.1 chapter times = segment bounds
- G2.2 chapters_per_minute band
- G2.3 short/long chapter WARN list
- G2.4 title ≤ 10 words
- G2.5 no stamp prefix
- G2.6 unique non-empty titles
- G2.7 non-empty `source_ids` cover exactly once
- G2.8 agent judgement hit/generic/miss

Also: `uv run pytest tests/ -v`, `ruff`, `mypy`, `bandit` exit 0.

## Deliverables

1. Code under `src/` / `config/` / `pyproject.toml`; tests under `tests/`
2. `cloud_out/artifacts/voice_002/chapters.json`
3. `cloud_out/gate_D2.md` + `cloud_out/run_meta.json`
4. Progress lines in `agent_docs/progress/stage_D2.md`
5. Commit and **push** branch `cursor/demo-d2-chapters`. Do **not** open a pull request.

## Stop-list

Do not: read `eval/` or `.env`; process or send audio; re-run ASR/VAD/diarization; implement
insights / report / web upload; bakeoff Jina late chunking or P2; weaken gate thresholds;
force-push; open a PR; read files outside `cloud_in/inputs/` for meeting text (use the packed
transcript only).
