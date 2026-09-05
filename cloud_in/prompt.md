# Stage D1 — voice → full transcript

You are the product development cloud agent. Read `cloud_in/agent/AGENTS.md` and
`cloud_in/agent/rules.md` first, then this prompt. The run is unattended: do not ask for approval,
install what the stage needs, finish with a gate report, full-meeting artifacts, and a branch push
(no PR).

## Why this stage

D0 delivered the skeleton (ports, stubs, CLI, health). D1 implements the speech chain and must
return a **complete text transcript** of the packed full meeting (~24.5 min), plus automated
checks (no Latin in segments, Russian word ratio, schema). Human listening happens later, locally.

Roadmap stages are `D0 → D1 → D2 → …`. The name **G1** in contracts is only the auto-check list
*inside* D1 — not a separate stage.

## Task

1. Follow `agent_docs/instructions/coder_D1.md` step by step.
2. Follow `agent_docs/instructions/tester_D1.md` for tests and `[TEST-ID]`s.
3. Run the full pipeline on the packed full meeting (required).
4. Write `cloud_out/gate_D1.md` for checks G1.0–G1.7.

If instruction files and this prompt disagree, the instruction files win; note the discrepancy in
the gate report.

## Inputs

Packed for this stage (must pass preflight):

| Path | What |
|---|---|
| `cloud_in/inputs/STACK.md` | frozen demo stack — do not reopen bakeoffs |
| `cloud_in/inputs/audio/voice_002.m4a` | **primary** full meeting (~24.5 min, ~23 MiB) — required ASR run |
| `cloud_in/inputs/audio/test_voice.m4a` | ~83 s clip — optional fast smoke within ASR budget |
| `cloud_in/inputs/artifacts/baseline_transformers.json` | legacy fixture (keep working `convert-legacy`) |
| `cloud_in/inputs/artifacts/baseline_ninth.json` | legacy fixture |

Also in git:

| Path | What |
|---|---|
| `agent_docs/instructions/coder_D1.md`, `tester_D1.md` | implementation and test specs |
| `agent_docs/contracts/*.md` | schemas, ports, configs, gate G1 |
| `src/`, `config/`, `tests/` | D0 skeleton already on `main` — extend it |

Do **not** open `docs/research_results/`, `docs/dev_specs.md`, `eval/`, `data/`, or `.env`.

## Approved dependencies

`onnxruntime`, `soundfile`, `scikit-learn`, CPU `torch`, CPU `torchaudio`,
`gigaam` from `git+https://github.com/salute-developers/GigaAM.git`, `speakeronnx` (WeSpeaker).
Install only via `uv add` / documented extras. Anything else needs a written justification in the
gate report.

Secret: `HF_TOKEN` for Hub downloads. No Gemini on this stage.

## Gate D1 (must pass before push)

Checks G1.0–G1.7 from `agent_docs/contracts/quality_gates.md`, measured on the **full-meeting**
`transcript.json`:

- G1.0 preflight (pack + token)
- G1.1 Russian word ratio ≥ 0.90
- G1.2 Latin characters in segment text == 0
- G1.3 schemas valid
- G1.4 times monotonic / inside duration
- G1.5 holes and empty segments listed
- G1.6 wall time + peak RSS recorded
- G1.7 agent judgement: 3–5 coherent Russian fragments

Also: `uv run pytest tests/ -v`, `ruff`, `mypy`, `bandit` exit 0.

## Deliverables

1. Code under `src/` / `config/` / `pyproject.toml`; tests under `tests/`
2. `cloud_out/artifacts/voice_002/` — at least `transcript.json`, `quality.json`, plus
   `audio.json`, `speech.json`, `turns.json`, `suggestions.json`
3. `cloud_out/gate_D1.md` + `cloud_out/run_meta.json`
4. Progress lines in `agent_docs/progress/stage_D1.md`
5. Commit and **push** branch `cursor/demo-d1-speech`. Do **not** open a pull request.

## Stop-list

Do not: read `eval/` or `.env`; send audio to any API; implement chunking / LLM titles / insights /
web upload; use Whisper or pyannote; weaken gate thresholds; force-push; open a PR; process audio
from outside `cloud_in/inputs/`.
