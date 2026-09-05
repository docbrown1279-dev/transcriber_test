# Stage D0 — application skeleton, ports and stubs

You are the product development cloud agent. Read `cloud_in/agent/AGENTS.md` and
`cloud_in/agent/rules.md` first, then this prompt. The run is unattended: do not ask for approval,
install what the stage needs, and finish with a report and a PR.

## Why this stage

The research phase is closed and the stack is frozen. Nothing of the application exists yet: no
`pyproject.toml`, no `src/`, no `tests/`. This stage builds the skeleton every later stage plugs
into — config profiles, artifact models, a component registry where later engines and `prod`-only
components are already declared, the pipeline stage graph, a `/healthz` self-check and a CLI.

**No model-backed stage is implemented here.** No ASR, no diarization, no embeddings, no LLM
calls. Do not install `torch`, `gigaam`, `onnxruntime`, `transformers` or `llama-cpp-python` in
this run.

## Task

Follow `agent_docs/instructions/coder_D0.md` step by step (it is the implementation spec: exact
file list, per-file requirements, acceptance criteria). Then follow
`agent_docs/instructions/tester_D0.md` for the test suite and its `[TEST-ID]` list.

If the two instruction files and this prompt disagree, the instruction files win; record the
discrepancy in the gate report.

## Inputs

Packed for this stage (must pass preflight):

| Path | What |
|---|---|
| `cloud_in/inputs/STACK.md` | frozen demo stack distilled by the local planner — do not reopen bakeoffs |
| `cloud_in/inputs/audio/test_voice.m4a` | ~83 s Russian clip; D0 uses it only for ffmpeg/ffprobe smoke — **no ASR** |
| `cloud_in/inputs/artifacts/baseline_transformers.json` | transcript of an 85 s clip (GigaAM v3, legacy research JSON shape) — converter + contract fixtures |
| `cloud_in/inputs/artifacts/baseline_ninth.json` | same, second clip |

Also in git (product docs, not research archive):

| Path | What |
|---|---|
| `agent_docs/instructions/coder_D0.md`, `tester_D0.md` | implementation and test specs |
| `agent_docs/contracts/*.md` | artifact schemas, ports, configs, gate G0 |

Do **not** open `docs/research_results/`, `docs/dev_specs.md`, `eval/`, `data/`, or `.env`.
For D0 the contracts already encode the demo profile; the long TЗ is not required.
Do not run ASR/VAD/diarization on the packed audio in this stage.

## Approved dependencies

Runtime: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `pydantic>=2`,
`pydantic-settings`, `pyyaml`, `numpy`, `typer`.
Dev: `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`, `bandit`.

Anything beyond this list needs a documented justification in the gate report — add it only if the
stage cannot be completed otherwise, and prefer the standard library.

## Gate D0 (must pass before the PR)

Checks G0.0–G0.7 from `agent_docs/contracts/quality_gates.md`:

- G0.0 preflight: this prompt, the agent role files, `STACK.md`, the packed audio, and both packed artifacts are present
- G0.1 `uv run pytest tests/ -v` exits 0
- G0.2 `ruff` / `mypy` / `bandit` exit 0
- G0.3 registry holds every key from the interface contract
- G0.4 prod-only keys raise `ComponentUnavailableError` under profile `demo`
- G0.5 `transcriber plan --job …` prints the nine stages in contract order with a status each
- G0.6 `transcriber validate` accepts the converted fixtures and rejects a corrupted copy
- G0.7 `GET /healthz` returns 200 when the environment is sane; self-check includes `ffprobe` on
  `cloud_in/inputs/audio/test_voice.m4a` (duration ~83 s). 503 naming the broken component otherwise.
  Still **no** ASR in D0.

## Deliverables

1. Code under `src/`, `config/`, `pyproject.toml`; tests under `tests/`
2. `cloud_out/gate_D0.md` — the check table plus deviations
3. `cloud_out/run_meta.json` — branch, commit, host inventory, package versions, wall time
4. Appended status lines in `agent_docs/progress/stage_D0.md`
5. Commit and open a PR from branch `cursor/demo-d0-skeleton`

## Stop-list

Do not: implement or install any ASR / VAD / diarization / embedding / LLM engine; call any API;
read `eval/`, `.env`, `data/`, or `docs/research_results/`; run recognition on the packed audio
(ffprobe/probe-audio only); touch `docs/`, `agent_docs/contracts/` or `.cursor/`; write fixture or
placeholder values into a production artifact path; re-evaluate the frozen stack; build the upload
UI, the job queue, per-IP limits or the TTL sweeper (those are stage D4); force-push any branch.
