# Coder instructions — stage D4 (web demo, **local**)

Status precondition: `agent_docs/progress/stage_D4.md` contains `INSTRUCTIONS_READY`.
Contracts: [`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md),
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md),
[`../contracts/config_profiles.md`](../contracts/config_profiles.md),
[`../contracts/quality_gates.md`](../contracts/quality_gates.md) (G4).
Plan: [`../plans/draft_D4_scope.md`](../plans/draft_D4_scope.md).
UI stubs already present: `src/transcriber/web/static/stubs/` (keep as reference; replace with Jinja when wiring jobs).

**This stage runs on the developer machine.** No `cloud_in/` pack, no Cloud Agent handoff, no PR-from-cloud flow.

Goal: working demo UI — upload → progress → **chapter index** → **chapter page** — plus limits, worker, TTL, stub dictionary/summary actions, simple player + primitive edit. Wire to the existing pipeline on main.

Ambiguity → `agent_docs/reports/BLOCKED.md` (or `BLOCKED.md` under the working branch docs) and stop; do not invent contracts.

## Scope

Write / modify only (create missing files):

```
config/base.yaml                         # already: max_minutes=30, allow_editing/player true
config/profiles/{demo,dev,prod}.yaml     # overlays if needed
src/transcriber/web/app.py               # routes, static, templates mount
src/transcriber/web/routes.py            # upload, jobs, result, chapter, download, events
src/transcriber/web/limits.py            # IP/day, concurrent, size, duration warn+trim
src/transcriber/web/url_stub.py          # classify youtube/yandex/unknown; no download
src/transcriber/web/templates/           # Jinja: upload, progress, result, chapter, player partial
src/transcriber/web/static/              # css/js (may evolve from stubs/)
src/transcriber/jobs/store.py            # extend as needed
src/transcriber/jobs/queue.py            # single worker / max_concurrent
src/transcriber/jobs/ttl.py              # sweeper
src/transcriber/pipeline/...             # only if needed to emit progress / resume
src/transcriber/cli.py                   # optional: serve or run-job helpers
.manuals/manual_testing.md               # ONLY if user asks; prefer not
```

Do **not** edit: `docs/`, `agent_docs/contracts/` (unless Planner asked), `eval/`, `.env`, `.cursor/`.
Do **not** create `tests/` (Tester owns tests).
Do **not** add Playwright or a frontend bundler.
Do **not** rebuild `data/voice_002` chapters/insights/report.
Do **not** implement real YouTube/Yandex fetch.

## Approved dependencies

| Package | Note |
|---|---|
| FastAPI / Starlette / Jinja2 / python-multipart | use if already in lock; **ask before** `uv add` |

No Playwright, Selenium, Next, React.

## Behaviour rules

1. **Localhost IP limits.** `requests_per_ip_per_day` must **not** apply to loopback clients (`127.0.0.1`, `::1`, and Host that resolves to local). Concurrent job limit still applies (or document if also relaxed — default: **concurrent still enforced** everywhere).
2. **Duration.** `audio.max_minutes` from config (30). Longer → **warning** + truncate media to that length before pipeline; do not hard-reject.
3. **File size.** Over `max_file_size_mb` → reject before pipeline.
4. **UI flow.** Match plan §2: result = chapter list + dict/summary stubs + player; chapter = text + edit + player.
5. **URL field.** Stub parser only (type detection + message); processing still requires a file until a later stage.
6. **Secrets / logs.** Never log transcript text, API keys, or raw client IPs (hash non-loopback if stored). `JOB_IP_SALT` required when hashing.
7. **LLM.** Summary button may call existing report pipeline or stub until wired; stay within `llm.max_calls_per_job`. Prefer fixture/resume for repeated local runs.

## Algorithm (suggested order)

1. Limits module + unit-friendly helpers (loopback detect, trim warning payload).
2. Job create on upload → store file under `{storage_root}/jobs/{id}/` → background worker runs orchestrator; publish `StageEvent`s.
3. Progress page: polling `GET /jobs/{id}/events` (SSE optional later).
4. Result page from `chapters.json` (+ optional report when present).
5. Chapter page from transcript segments ∩ chapter `source_ids`; edit save = stub or write a local override file in the job dir.
6. Serve audio for player from job upload / normalized wav.
7. TTL sweeper.
8. Keep `/stubs/*` working or redirect to real routes once Jinja is ready.
9. Mark `READY_FOR_TEST` in `stage_D4.md` when smoke works locally (`uvicorn` + short clip or fixtures).

## Out of scope

Playwright E2E, cloud handoff, PDF, word-highlight player, real link download, D5 Docker, force-push `main`.

## Done when

- Manual: upload short clip (or fixture resume) → see progress → chapter index → open chapter → player chrome + edit UI.
- Loopback can submit more than once/day; a non-loopback second daily request gets 429 (testable with forged client IP in TestClient).
- Over-limit duration returns warning and truncated processing path.
- Coder notes any open wiring gaps in `agent_docs/progress/stage_D4.md`.
