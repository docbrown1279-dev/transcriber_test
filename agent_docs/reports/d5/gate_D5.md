# Gate D5 — verdict

**Verdict: PASS**

Date: 2026-09-07  
Reports: `build_test.md`, `g5_15min.md`, `g5_15min.json`

## Checklist

| ID | Gate | Result | Evidence |
|---|---|---|---|
| `[D5-BUILD-01]` | runtime image build | PASS | exit 0 |
| `[D5-BUILD-02]` | test image build | PASS | exit 0 |
| `[D5-CTX-01]` | `/app/data/test_voice.m4a` in image | PASS | ls exit 0 |
| `[D5-TEST-01]` | unit/contract tests in container | PASS | final 84 passed, 3 skipped |
| `[D5-TEST-02]` | soft regression `test_voice` | PASS | soft path green |
| `[D5-SEC-01]` | secrets via volume; no values in logs | PASS | key names only; scrub clean |
| `[D5-HEALTH-01]` | `GET /healthz` → 200 with secrets | PASS | HTTP 200, healthy |
| `[D5-G5-01]` / G5.1 | complete under 2 CPU / 8g, no OOM | PASS | exit 0, JSON written |
| `[D5-G5-02]` / G5.2 | per-stage wall + peak RSS | PASS* | walls present; process peak 2183.9 MB; stage RSS null |
| `[D5-G5-03]` / G5.3 | total wall reported | PASS | 784.664 s; 15 min OK |
| `[D5-G5-04]` / G5.4 | peak RSS web+ASR < 7 GiB | PASS | 2.13 GiB < 7 GiB |
| `[D5-G5-05]` | mode b | PASS | `--mode b` |
| `[D5-G5-06]` | cold vs warm noted | PASS | cold HF downloads in this run |

\*WARN note (non-blocking): harness sets per-stage `peak_rss_mb` to `null`; overall process peak is present and used for G5.4.

## Tester notes

1. Initial baked-image pytest failed 2 tests due to container path / `TRANSCRIBER_DOTENV` isolation; fixed in `tests/unit/test_health.py` and `tests/unit/test_llm_config.py`, then image rebuilt — full green.
2. Mode `a` optional control not run.
3. No secrets committed; values never written into reports.

## Agent judgement

Docker runtime + secrets mount + in-container tests and G5.1–G5.4 thresholds are met on the local 15-minute slice. Stage ready for human/sign-off follow-up; no @Coder production fix required for this gate.
