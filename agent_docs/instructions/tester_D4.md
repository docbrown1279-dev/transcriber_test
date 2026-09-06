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

## Backend E2E / module smoke — **current expectation** (extend later)

Цель: один (или узкий набор) integration-тест(ов), где **бэкенд-модули** на коротком входе
возвращают артефакты «похоже на правду» по схеме и здравому смыслу — **без** браузера.

Пока закладываем такой каркас (человек дополнит пороги по модулям):

| Step | Artifact | Minimal “truth-like” checks (v0) |
|---|---|---|
| normalize | `audio.json` | `duration_sec` > 0; `normalized.path` exists |
| vad | `speech.json` | `regions` non-empty; `speech_sec` > 0; times within duration |
| diarize | `turns.json` | `speaker_count` ∈ **1..8** on short clip; turns non-overlapping / sorted |
| asr | `transcript.json` | nonempty segments; ru-ish text (reuse G1 ratio helper if cheap); times align to turns |
| chunk | `chapters.json` | ≥1 chapter; `source_ids` ⊆ transcript ids; chapter times coherent |
| titles | chapters with titles | title non-empty string per chapter (or skip if fixture titles) |
| insights/report | optional | skip live LLM in default smoke; cassette/fixture OK |

**Not required in v0:** full voice_002, live Gemini, Playwright, pixel UI.

If a module is too heavy for default `pytest`, gate it with `requires_models` / `slow` and document
in `agent_docs/reports/test_D4.md` what was skipped.

Human may append rows/thresholds per module in this table or in `test_D4.md` without changing
Coder scope.

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
| `[D4-SMOKE-01]` | pipeline module smoke table v0 (or skip with reason) |

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
