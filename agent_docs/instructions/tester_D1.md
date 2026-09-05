# Tester instructions — stage D1 (voice → transcript)

Status precondition: `agent_docs/progress/stage_D1.md` contains `READY_FOR_TEST`.
Contracts: [`../contracts/quality_gates.md`](../contracts/quality_gates.md) (G1),
[`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md),
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md).
Coder spec: [`coder_D1.md`](coder_D1.md).

Write scope: `tests/` only. Never edit `src/`, `config/`, contracts, or `docs/`. A failing test is
a defect for @Coder — never weaken assertions.

Keep all D0 tests green. Add D1 coverage below.

## Test layout (add)

```
tests/unit/test_gain.py
tests/unit/test_turn_merge.py
tests/unit/test_segment_split.py
tests/unit/test_holes.py
tests/unit/test_dictionary_suggest.py
tests/unit/test_quality_g1.py
tests/contract/test_speech_chain_artifacts.py
tests/integration/test_run_short_clip.py          # requires_inputs, optional/slow
tests/integration/test_full_meeting_artifacts.py   # requires_inputs — validates cloud_out or job dir
```

## Test cases

| ID | File | What |
|---|---|---|
| `[D1-GAIN-01]` | `test_gain.py` | RMS at/above threshold → `gain_db=0`, `gain_applied=false` |
| `[D1-GAIN-02]` | | RMS below threshold → positive gain, clamped by `max_gain` and peak ceiling |
| `[D1-MRG-01]` | `test_turn_merge.py` | same-speaker gap ≤ config → merged; larger gap → kept separate |
| `[D1-MRG-02]` | | turn shorter than absorb threshold absorbed into neighbour (prefer same speaker) |
| `[D1-SPL-01]` | `test_segment_split.py` | interval > `max_segment_seconds` splits on time only into contiguous slices ≤ max |
| `[D1-HOL-01]` | `test_holes.py` | gaps ≥ `min_hole_sec` listed; shorter gaps ignored |
| `[D1-DIC-01]` | `test_dictionary_suggest.py` | empty dictionary → `suggestions=[]`, `applied=false`; transcript bytes unchanged |
| `[D1-Q-01]` | `test_quality_g1.py` | pure Cyrillic sample → ratio 1.0, latin 0 → pass G1.1/G1.2 |
| `[D1-Q-02]` | | planted Latin token → G1.2 fail; ratio below 0.90 → G1.1 fail |
| `[D1-Q-03]` | | empty segments excluded from ratio; no ZeroDivision |
| `[D1-ART-01]` | `test_speech_chain_artifacts.py` | minimal hand-built audio/speech/turns/transcript/quality/suggestions round-trip models |
| `[D1-REG-01]` | `test_registry.py` (extend) | under `demo`, `build("asr","gigaam_v3_rnnt")` returns a real engine object (or lazy wrapper), not `StageNotImplementedError`; `pyannote31` still unavailable |
| `[D1-PLN-01]` | `test_pipeline_plan.py` (extend) | after a successful short fixture chain (mocked engines OK), plan reports normalize…correction_suggest as `done` |
| `[D1-INT-01]` | `test_run_short_clip.py` (`requires_inputs`, `slow`) | if models+`test_voice.m4a` present: `transcriber run` produces valid transcript; latin_chars==0; skip if weights missing |
| `[D1-INT-02]` | `test_full_meeting_artifacts.py` (`requires_inputs`) | `cloud_out/artifacts/voice_002/transcript.json` exists after the gate run, validates, duration coverage within audio length, G1.2 latin==0; skip only when artifacts not yet produced **during unit-only CI** — on the cloud gate run this must execute and pass |

Unit tests for gain/merge/split/holes/quality must not need torch, onnx, audio files, or network.

## Execution

```
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/
uv run bandit -r src/ -ll
uv run python -m transcriber.quality check-transcript \
  cloud_out/artifacts/voice_002/transcript.json
```

Lint failures block the handoff.

## Gate mirror

Fill `cloud_out/gate_D1.md` checks G1.0–G1.7 (Coder may draft; Tester confirms). Verdict
`PASS` / `PASS_WITH_WARNINGS` / `FAIL`. Include agent judgement fragments for G1.7.

## Report

Write `agent_docs/reports/test_D1.md` (English body) with per `[TEST-ID]` results.
Append to `agent_docs/progress/stage_D1.md`:

```
## YYYY-MM-DD — Tester
- STATUS: TEST_PASS | TEST_FAIL | BLOCKED
- Tests: <paths>
- Executed: <commands and exit codes>
- Report: agent_docs/reports/test_D1.md
```

After `TEST_PASS`, ensure branch `cursor/demo-d1-speech` is committed and **pushed** (no PR).

Verdict to the user in Russian; test code in English.
