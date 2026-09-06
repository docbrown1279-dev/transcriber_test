# Tester instructions — stage D4 (web demo, **local**)

Status precondition: `agent_docs/progress/stage_D4.md` contains `READY_FOR_TEST`.
Contracts: [`../contracts/quality_gates.md`](../contracts/quality_gates.md) (G4),
[`../plans/draft_D4_scope.md`](../plans/draft_D4_scope.md).
Coder spec: [`coder_D4.md`](coder_D4.md).

**Local gate only.** No Cloud Agent, no `cloud_out/gate_D4.md` requirement (optional local copy under `agent_docs/reports/D4/` is fine).

Write scope: `tests/` only. Do not edit `src/`, `config/`, contracts, manuals, or `docs/`.
Keep D0–D3 tests green.

## Explicitly out of test scope

- **No Playwright / browser E2E.** No Selenium.
- Human browser check is `HUMAN_GATE`, not automated UI.

## Test layout (add / extend)

```
tests/unit/test_web_limits.py          # loopback exempt; size reject; duration warn+trim helpers
tests/unit/test_url_stub.py            # youtube / yandex / unknown classification
tests/unit/test_jobs_ttl_queue.py      # if logic is pure enough
tests/contract/test_job_artifact.py    # if new fields
tests/integration/test_web_flow.py     # FastAPI TestClient: upload → events → result → chapter
tests/integration/test_pipeline_modules_smoke.py   # backend “truth-like” chain (see below)
```

Use short audio from `data/test_voice.m4a` or packed fixtures; mark heavy ASR with
`pytest.mark.slow` / skip if models missing (`HF_HUB_OFFLINE`, no wav). Prefer fixtures for CI-speed path.

## G4 mapping (local)

| id | How to verify |
|---|---|
| G4.1 | `pytest` green including integration web flow (**TestClient**, not Playwright) |
| G4.2 | `GET /healthz` → 200 + component map |
| G4.3 | Second request/day from **non-loopback** IP → 429; **loopback exempt** (many requests from 127.0.0.1 OK) |
| G4.4 | Second concurrent job rejected |
| G4.5 | Oversize → reject; over `max_minutes` → warning + trim behaviour |
| G4.6 | TTL removes job dir (unit/integration with fake clock or short ttl in test config) |
| G4.7 | Log scrub / no transcript dump in captured logs (best-effort assert) |
| G4.8 | Result response contains chapter links + action controls; chapter page has edit + player chrome |

## Backend E2E / module smoke — **current expectation**

### Soft regression (primary): `test_voice.m4a`

```
uv run pytest tests/regression/ -v -m regression
# optional hard fail:
REGRESSION_STRICT=1 uv run pytest tests/regression/ -v -m regression
```

Clip: `data/test_voice.m4a`. Reference: `tests/fixtures/regression/test_voice_ref.json`.

| id | Check | Soft on fail |
|---|---|---|
| REG.VAD.IoU | speech regions IoU vs gold union ≥ `min_iou` (0.70) | WARN + manual review |
| REG.DIAR.speakers | `speaker_count` in **2..4** (gold on clip = 2; ~3–4 with tolerance) | WARN + manual review |
| REG.ASR.ru_ratio | Russian word ratio ≥ 0.90 | WARN + manual review |
| REG.ASR.latin | Latin chars == 0 | WARN + manual review |

Report: `agent_docs/reports/regression_test_voice.md` (+ `.json`).  
**Not a merge blocker** unless `REGRESSION_STRICT=1`. Default `pytest tests/` still exits 0 on WARN (warning only).

### Broader module smoke (optional later)

| Step | Artifact | Minimal “truth-like” checks (v0) |
|---|---|---|
| normalize | `audio.json` | `duration_sec` > 0; wav exists |
| … | … | human may extend per module |

**Not required in v0:** Playwright, full voice_002, live Gemini.

## Unit / API cases

| ID | What |
|---|---|
| `[D4-LIM-01]` | loopback client not counted toward `requests_per_ip_per_day` |
| `[D4-LIM-02]` | non-loopback second daily upload → 429 |
| `[D4-LIM-03]` | oversize file rejected; over-duration yields warn+trim metadata |
| `[D4-URL-01]` | stub classifies youtube / yandex / unknown; does not fetch |
| `[D4-WEB-01]` | healthz 200 |
| `[D4-WEB-02]` | TestClient: create job → progress events → result has chapter links |
| `[D4-WEB-03]` | chapter page returns text + edit controls + player root |
| `[D4-WEB-04]` | concurrent second job rejected |
| `[D4-SMOKE-01]` | soft regression `tests/regression/` on test_voice (IoU / speakers / RU ASR); WARN≠fail unless STRICT |
| `[D4-IOU-01]` | unit: speech region IoU helper |

## Execution

```
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/
uv run bandit -r src/ -ll
# manual (human): uvicorn + browser on short clip / voice_002
```

## Report

`agent_docs/reports/test_D4.md` + optional `agent_docs/reports/D4/gate_D4.md`.
Append `TEST_PASS` / `TEST_FAIL` / `BLOCKED` to `stage_D4.md`.
No cloud push required; commit/PR only if the human asks.
