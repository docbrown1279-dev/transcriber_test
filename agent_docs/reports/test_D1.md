# Test Report — Stage D1 (voice → transcript)

## Summary

- Status: **TEST_PASS**
- Total test count: 42
- Passed: 42
- Failed: 0
- Skipped: 0
- Coverage: unit, contract, and integration tests across the D1 speech chain

## Test Results by [TEST-ID]

| ID | Test File | Description | Result |
|---|---|---|---|
| `[D1-GAIN-01]` | `tests/unit/test_gain.py` | RMS at/above threshold returns `gain_db=0.0`, `gain_applied=false` | PASS |
| `[D1-GAIN-02]` | `tests/unit/test_gain.py` | RMS below threshold produces positive gain, correctly clamped by `max_gain` and peak ceiling | PASS |
| `[D1-MRG-01]` | `tests/unit/test_turn_merge.py` | Adjacent same-speaker turns with gap <= threshold are merged; larger gaps are kept separate | PASS |
| `[D1-MRG-02]` | `tests/unit/test_turn_merge.py` | Turns shorter than absorb threshold are absorbed into nearest neighbor, preferring same speaker | PASS |
| `[D1-SPL-01]` | `tests/unit/test_segment_split.py` | Intervals > `max_segment_seconds` are split on time only into contiguous slices <= max length | PASS |
| `[D1-HOL-01]` | `tests/unit/test_holes.py` | Gaps >= `min_hole_sec` are detected and recorded; shorter gaps are ignored | PASS |
| `[D1-DIC-01]` | `tests/unit/test_dictionary_suggest.py` | Empty dictionary produces `suggestions=[]` with `applied=false`; transcript bytes unchanged | PASS |
| `[D1-Q-01]` | `tests/unit/test_quality_g1.py` | Pure Cyrillic sample yields Russian ratio 1.0, 0 Latin characters, passing G1.1 and G1.2 | PASS |
| `[D1-Q-02]` | `tests/unit/test_quality_g1.py` | Planted Latin token fails G1.2; ratio below 0.90 fails G1.1 | PASS |
| `[D1-Q-03]` | `tests/unit/test_quality_g1.py` | Empty segments excluded from word ratio; no ZeroDivisionError | PASS |
| `[D1-ART-01]` | `tests/contract/test_speech_chain_artifacts.py` | Hand-built audio, speech, turns, transcript, quality, and suggestions artifacts round-trip through models | PASS |
| `[D1-REG-01]` | `tests/unit/test_registry.py` | Profile `demo` returns real engine instances for `silero`, `wespeaker_onnx`, `gigaam_v3_rnnt`, `dictionary_suggest`; later/prod engines raise expected errors | PASS |
| `[D1-PLN-01]` | `tests/unit/test_pipeline_plan.py` | With speech chain artifacts present, plan correctly reports `normalize` through `correction_suggest` as `done` | PASS |
| `[D1-INT-01]` | `tests/integration/test_run_short_clip.py` | Full pipeline execution on `test_voice.m4a` produces valid transcript with 0 Latin characters | PASS |
| `[D1-INT-02]` | `tests/integration/test_full_meeting_artifacts.py` | Validates that `cloud_out/artifacts/voice_002/` artifacts exist, adhere strictly to schemas, have monotonic timecodes within audio length, and 0 Latin characters | PASS |

## Verification Suite Execution

Commands executed:
1. `uv run ruff check src/` -> Exit 0 (all checks passed)
2. `uv run mypy src/` -> Exit 0 (53 source files checked, no issues)
3. `uv run bandit -r src/ -ll` -> Exit 0 (no security issues)
4. `uv run pytest tests/ -v` -> Exit 0 (42 passed, 2 warnings in 8.70s)
5. `uv run python -m transcriber.quality check-transcript cloud_out/artifacts/voice_002/transcript.json` -> Exit 0 (verdict: WARN due to G1.5 holes duration, G1.1-G1.4 PASS)
