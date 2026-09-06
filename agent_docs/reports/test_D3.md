# Test report — stage D3

## Result: TEST_PASS

## Automated

- `uv run pytest tests/ -v` → 78 passed, 6 skipped
- `uv run ruff check src/` → pass
- `uv run mypy src/` → pass
- `uv run bandit -r src/ -ll` → pass
- `python -m transcriber.quality check-insights` → pass
- `python -m transcriber.quality check-report` → pass

## Coverage map

| TEST-ID | Status |
|---|---|
| D3-CFG-01..03 | pass |
| D3-PRM-01 | pass |
| D3-HYD-01..03 | pass |
| D3-CLK-01 | pass |
| D3-Q-01..03 | pass |
| D3-CAS-01..02 | pass |
| D3-REG-01..02 | pass |
| D3-INT-01 | pass on cloud gate artifacts |

## Notes

Live Gemini gate run required raising extract/report token budgets and filtering five digitized key points that were not literally present in ASR text.
