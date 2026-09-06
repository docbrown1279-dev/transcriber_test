# Stage D4 — web demo (local)

## 2026-09-06 — Planner
- STATUS: INSTRUCTIONS_READY
- Plan: `agent_docs/plans/draft_D4_scope.md`
- Instructions: `agent_docs/instructions/coder_D4.md`, `tester_D4.md`
- Mode: **local only** (no cloud handoff)
- UI stubs: `src/transcriber/web/static/stubs/` (+ `/stubs/*` routes)
- Decisions: max_minutes=30 warn+trim; loopback exempt from IP/day limit; no Playwright; backend module smoke E2E v0
- Next: Coder implements on branch `cursor/demo-d4-web` (or local commits); then Tester; HUMAN_GATE in browser

## 2026-09-06 — Coder
- STATUS: READY_FOR_TEST
- Lint: `ruff check src/` 0; `mypy src/` 0; `bandit -r src/ -ll` 0 (existing tests: unit+contract 82 passed)
- Smoke: TestClient upload (loopback 2× OK) → 409 concurrent → 429 non-loopback 2nd/day; fixture chapters → result index + chapter edit/player; TTL removes dir
- Wiring gaps:
  - Dictionary / summary buttons are stubs (no live LLM on summary; existing report.md is shown if present)
  - URL field classifies youtube/yandex/unknown only; processing still requires a file
  - Worker runs until `titles`; if titles fail but `chapters.json` exists, job is `done` with `titles:<Exc>`
  - Insights/report not auto-run (stay within `llm.max_calls_per_job`)
  - Chapter save writes `edits/{cid}.txt`, never mutates `transcript.json`
  - Starlette TestClient default peer is `testclient` (not loopback) — use `TestClient(app, client=("127.0.0.1", 50000))`
- Next: @Tester `agent_docs/instructions/tester_D4.md`; human browser gate after tests

## 2026-09-06 — Coder (edit → transcript.json)
- Chapter save now writes segment `text` into `transcript.json` (first save copies ASR to `transcript.asr.json`; drops stale insights/report). Dictionary still stub.
- Old `edits/{cid}.txt` overrides are unused.

## 2026-09-06 — Coder (stale summary, ASR restore)
- ASR original stays in `transcript.asr.json`; chapter and full-job restore copy texts back.
- Editing no longer deletes report/insights. If a report exists, `report.stale.json` lists edited chapters.

## 2026-09-06 — Coder (profile in yaml, not .env)
- `.env` is secrets-only; `APP_PROFILE` inside `.env` is ignored.
- Active profile: `config/base.yaml` `app.profile` (fallback **demo**, not prod). CLI `--profile` / process env still override for one-off/serve -p.

## 2026-09-06 — Coder (progress UI, media errors)
- Upload ffmpeg crash on `.bin` / unknown container: sniff format, never mux to `.bin`, catch trim/probe, strip leftover job.
- Progress page: bar + elapsed only. User-facing errors: limits as-is, else generic. Details in logs.
- Backlog: `agent_docs/plans/ticket_d4_audio_formats.md` (Python stdlib has no mp3; ffmpeg does).

## 2026-09-06 — Coder (live summary + chapter titles)
- Summary button calls Qwen report prompt (digest of chapter text, no per-chapter extract). Budget: `ui.summary_max_calls` (demo=2) in `summary_usage.json`.
- Result index: editable chapter titles (`POST /jobs/{id}/actions/titles`); title edits mark report stale.
- Next: @Tester `agent_docs/instructions/tester_D4.md`; human browser gate.
- Backlog (не в этой ветке): `agent_docs/plans/ticket_d2_short_chapters.md` — пол длительности главы; на 30-мин клипе есть ~6–11 с и главы из 1 реплики (`absorb_shorter_than_sec=5`).

## 2026-09-06 — Coder (player position, chapter nav)
- Player stores time (+ playing) in sessionStorage per job; result ↔ chapter keeps the same place.
- Chapter page: prev/next by `C00`… ids; index lists the same ids.
- Full ASR restore also deletes `speakers.json`. Index lists cluster id + speech duration; chapter labels keep `Имя · SPEAKER_00`.
- Backlog (не в этой ветке): `agent_docs/plans/ticket_d1_speaker_clusters.md` — 5 id vs 4 человека (SPEAKER_00 ≈ 87% + крошки); порог кластеризации, клипы с известным N, OTHER для 2–3 реплик.

