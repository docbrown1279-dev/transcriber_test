# Tester instructions — stage D2 (chunking + titles)

Status precondition: `agent_docs/progress/stage_D2.md` contains `READY_FOR_TEST`.
Contracts: [`../contracts/quality_gates.md`](../contracts/quality_gates.md) (G2),
[`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md) §7,
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md).
Coder spec: [`coder_D2.md`](coder_D2.md).

Write scope: `tests/` only. Never edit `src/`, `config/`, contracts, or `docs/`. A failing test is
a defect for @Coder — never weaken assertions.

Keep all D0/D1 tests green. Add D2 coverage below.

## Test layout (add)

```
tests/unit/test_packing_c.py
tests/unit/test_chapter_metrics.py
tests/unit/test_title_validation.py
tests/unit/test_quality_g2.py
tests/contract/test_chapters_artifact.py
tests/fixtures/llm/title_p1_sample.json          # cassette / recorded JSON shape
tests/unit/test_titles_from_cassette.py           # no live Gemini
tests/integration/test_chapters_from_packed_transcript.py  # requires_inputs
```

## Test cases

| ID | File | What |
|---|---|---|
| `[D2-PCK-01]` | `test_packing_c.py` | different speakers + gap ≤ config → packed into one unit |
| `[D2-PCK-02]` | | gap above config → not packed across speakers |
| `[D2-PCK-03]` | | empty segment attaches to neighbour; non-empty coverage still complete after chapters |
| `[D2-MRG-01]` | | adjacent cosine ≥ threshold and under duration cap → merged |
| `[D2-MRG-02]` | | cosine below threshold → boundary kept; duration cap blocks merge |
| `[D2-TIM-01]` | | chapter `start`/`end` equal first/last segment bounds (exact) |
| `[D2-Q-01]` | `test_chapter_metrics.py` / `test_quality_g2.py` | density inside [0.4, 0.8] → pass; outside [0.3, 1.0] → fail |
| `[D2-Q-02]` | | title >10 words → G2.4 fail; stamp prefix → G2.5 fail |
| `[D2-Q-03]` | | duplicate / empty titles → G2.6 fail |
| `[D2-Q-04]` | | gap or overlap in non-empty `source_ids` → G2.7 fail |
| `[D2-TTL-01]` | `test_titles_from_cassette.py` | cassette JSON with title applied; optional extra P1 fields ignored for artifact |
| `[D2-ART-01]` | `test_chapters_artifact.py` | minimal chapters.json round-trip pydantic model |
| `[D2-REG-01]` | extend `test_registry.py` | `demo` builds `packing_c`, `rubert_tiny2`, `gemini` without `StageNotImplementedError`; `late_chunking_jina` still unavailable / stub |
| `[D2-PLN-01]` | extend plan test | job with only transcript fixture: plan shows chunk+titles pending then done after mocked run |
| `[D2-INT-01]` | `test_chapters_from_packed_transcript.py` (`requires_inputs`) | after gate run, `cloud_out/artifacts/voice_002/chapters.json` validates vs packed transcript (G2.1, G2.7); skip only in unit-only CI when artifact absent — **must pass on cloud gate run** |

Unit tests must not need network, Gemini, or model weights. Embedding merge tests may use fake
vectors injected via a tiny fake `EmbeddingBackend`.

## Execution

```
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/
uv run bandit -r src/ -ll
uv run python -m transcriber.quality check-chapters \
  cloud_out/artifacts/voice_002/chapters.json \
  --transcript cloud_in/inputs/artifacts/voice_002/transcript.json
```

Lint failures block the handoff.

## Gate mirror

Fill / confirm `cloud_out/gate_D2.md` for G2.0–G2.8. Verdict
`PASS` / `PASS_WITH_WARNINGS` / `FAIL`. G2.8: per-chapter `hit` / `generic` / `miss` table;
`miss` count must meet the contract threshold.

## Report

Write `agent_docs/reports/test_D2.md` (English body) with per `[TEST-ID]` results.
Append to `agent_docs/progress/stage_D2.md`:

```
## YYYY-MM-DD — Tester
- STATUS: TEST_PASS | TEST_FAIL | BLOCKED
- Tests: <paths>
- Executed: <commands and exit codes>
- Report: agent_docs/reports/test_D2.md
```

After `TEST_PASS`, ensure branch `cursor/demo-d2-chapters` is committed and **pushed** (no PR).

Verdict to the user in Russian; test code in English.
