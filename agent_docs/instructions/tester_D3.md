# Tester instructions — stage D3 (insights + report)

Status precondition: `agent_docs/progress/stage_D3.md` contains `READY_FOR_TEST`.
Contracts: [`../contracts/quality_gates.md`](../contracts/quality_gates.md) (G3),
[`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md) §8–§9,
[`../contracts/llm/base_llm.yaml`](../contracts/llm/base_llm.yaml).
Coder spec: [`coder_D3.md`](coder_D3.md).

Write scope: `tests/` only. Never edit `src/`, `config/`, contracts, manuals, or `docs/`.
Keep D0–D2 tests green.

## Test layout (add)

```
tests/unit/test_llm_config.py
tests/unit/test_prompt_render.py
tests/unit/test_insight_hydration.py
tests/unit/test_clock_gate.py
tests/unit/test_quality_g3.py
tests/unit/test_extract_from_cassette.py
tests/unit/test_report_from_cassette.py
tests/contract/test_insights_artifact.py
tests/contract/test_report_artifact.py
tests/fixtures/llm/extract_v1_sample.json
tests/fixtures/llm/report_v1_sample.json
tests/integration/test_insights_from_packed_chapters.py   # requires_inputs
```

## Test cases

| ID | What |
|---|---|
| `[D3-CFG-01]` | demo loads `base_llm.yaml`; `backend=gemini`; `api_key_env` is a name, not a secret |
| `[D3-CFG-02]` | switching `backend` to `nvidia`/`qwen` selects `openai_compat` + that `base_url` |
| `[D3-CFG-03]` | task `max_tokens` overrides `base_llm.max_tokens`; no `extra_config` on tasks |
| `[D3-PRM-01]` | leftover `{{…}}` after render raises |
| `[D3-HYD-01]` | extract `segment_ids` hydrate to transcript start/end/speaker |
| `[D3-HYD-02]` | unknown `segment_id` does not write invented times |
| `[D3-CLK-01]` | clock-gate mismatch → fail; copied times → pass |
| `[D3-Q-01]` | key_point without src → G3.3 fail; invented digit group → G3.4 fail |
| `[D3-Q-02]` | stamp prefix on key_point/summary → G3.7 fail |
| `[D3-Q-03]` | `draft_warning` false under demo → G3.8 fail |
| `[D3-CAS-01]` | cassette extract applied; empty key_points allowed |
| `[D3-CAS-02]` | cassette report: 5–12 moments, speakers label null, md renderer no LLM |
| `[D3-REG-01]` | demo builds `gemini` and `openai_compat`; `local_llama` still unavailable / stub |
| `[D3-REG-02]` | extend D0-REG-04: `openai_compat` **in** `available("llm","demo")`; `local_llama` still out |
| `[D3-INT-01]` | packed run artifacts validate G3.1–G3.4, G3.6–G3.8 (`requires_inputs`); skip only if artifact absent in unit CI — **must pass on cloud gate** |

Unit tests: no network, no live Gemini. Cassettes only.

## Execution

```
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/
uv run bandit -r src/ -ll
uv run python -m transcriber.quality check-insights \
  cloud_out/artifacts/voice_002/insights.json \
  --chapters cloud_in/inputs/artifacts/voice_002/chapters.json \
  --transcript cloud_in/inputs/artifacts/voice_002/transcript.json
uv run python -m transcriber.quality check-report \
  cloud_out/artifacts/voice_002/report.json \
  --insights cloud_out/artifacts/voice_002/insights.json \
  --chapters cloud_in/inputs/artifacts/voice_002/chapters.json
```

## Gate mirror

`cloud_out/gate_D3.md` for G3.0–G3.9. G3.5 and G3.9 are agent judgement. Verdict
`PASS` / `PASS_WITH_WARNINGS` / `FAIL`. Empty key_points on short chapters are not G3.3 failures.

## Report

`agent_docs/reports/test_D3.md`. Append `TEST_PASS` / `TEST_FAIL` / `BLOCKED` to
`agent_docs/progress/stage_D3.md`. After `TEST_PASS`, push `cursor/demo-d3-insights` (no PR).
